"""Tests for the per-minute sample recorder in core/ecoflow-power-watch.

The script has no .py extension (it is a direct systemd-timer entry point),
so it is loaded as a module with importlib's source loader. Every persisted
path (samples database, STATE, LOG) is redirected under tmp_path, the helper
call is stubbed with a synthetic payload so no real API is ever hit, and
push() -- which is also how notify-send gets called -- is stubbed so no real
notification is ever sent.

Fixtures are synthetic throughout: no real payload is pasted here, and no
serial numbers appear anywhere.
"""
import importlib.machinery
import importlib.util
import json
import os
import sqlite3
import sys

import pytest

SCRIPT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "core", "ecoflow-power-watch",
)


def load_module():
    loader = importlib.machinery.SourceFileLoader("ecoflow_power_watch", SCRIPT_PATH)
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def make_payload(overrides=None):
    """A synthetic flattened payload covering every schema-v1 source key,
    with clearly fake numbers -- never a real device reading."""
    payload = {
        "inv.acInVol": 121074,
        "inv.acInFreq": 60,
        "inv.inputWatts": 42,
        "inv.outputWatts": 7,
        "pd.wattsInSum": 50,
        "pd.wattsOutSum": 13,
        "mppt.inWatts": 0,
        "bmsMaster.inputWatts": 5,
        "bmsMaster.outputWatts": 3,
        "bmsMaster.temp": 28,
        "pd.chgPowerAc": 1000,
        "pd.chgPowerDc": 200,
        "pd.chgSunPower": 50,
        "pd.dsgPowerAc": 450000,
        "pd.dsgPowerDc": 90000,
        "bmsMaster.cycles": 37,
        "bmsMaster.soh": 98,
        "ems.chgRemainTime": 0,
        "ems.dsgRemainTime": 326,
        "ems.lcdShowSoc": 97,
    }
    if overrides:
        payload.update(overrides)
    return payload


def all_rows(db_path):
    conn = sqlite3.connect(db_path)
    try:
        conn.row_factory = sqlite3.Row
        return [dict(r) for r in conn.execute("SELECT * FROM samples ORDER BY ts")]
    finally:
        conn.close()


@pytest.fixture
def mod(monkeypatch, tmp_path):
    """A freshly loaded copy of the script, with every persisted path
    redirected under tmp_path and push() (which is also how notify-send gets
    invoked) replaced by a stub that records its calls instead of sending
    anything real."""
    m = load_module()
    monkeypatch.setattr(m, "SAMPLES_DB", str(tmp_path / "samples.db"))
    monkeypatch.setattr(m, "STATE", str(tmp_path / "state.json"))
    monkeypatch.setattr(m, "LOG", str(tmp_path / "outages.log"))
    m.push_calls = []
    monkeypatch.setattr(m, "push", lambda *a, **k: m.push_calls.append(a))
    return m


def test_full_payload_maps_every_column(mod, monkeypatch):
    """Catches a wrong source key or unit mapping (for example grid_v not
    divided by 1000, or dsg_ac_wh read from the wrong pd.* field) that would
    otherwise go unnoticed because the row is still written, just with the
    wrong number in it."""
    payload = make_payload()
    monkeypatch.setattr(mod, "fetch_payload", lambda: payload)
    monkeypatch.setattr(sys, "argv", ["ecoflow-power-watch"])

    mod.main()

    rows = all_rows(mod.SAMPLES_DB)
    assert len(rows) == 1
    row = rows[0]
    assert row["grid_v"] == pytest.approx(121.074)
    assert row["grid_hz"] == 60
    assert row["ac_in_w"] == 42
    assert row["ac_out_w"] == 7
    assert row["in_w"] == 50
    assert row["out_w"] == 13
    assert row["solar_in_w"] == 0
    assert row["batt_in_w"] == 5
    assert row["batt_out_w"] == 3
    assert row["soc"] == 97
    assert row["batt_temp_c"] == 28
    assert row["chg_ac_wh"] == 1000
    assert row["chg_dc_wh"] == 200
    assert row["chg_solar_wh"] == 50
    assert row["dsg_ac_wh"] == 450000
    assert row["dsg_dc_wh"] == 90000
    assert row["cycles"] == 37
    assert row["soh"] == 98
    assert row["chg_remain_min"] == 0
    assert row["dsg_remain_min"] == 326


def test_missing_grid_and_soc_keys_store_null_not_zero(mod, monkeypatch):
    """Catches an `or 0` regression in the recorder that would write a
    phantom 0 V / 0% reading into the history instead of leaving it NULL --
    the exact bug behind the 2026-09-05 phantom outage in outages.log."""
    payload = make_payload()
    for key in ("inv.acInVol", "ems.lcdShowSoc", "bmsMaster.soc",
                "bms_bmsStatus.soc", "pd.soc", "soc"):
        payload.pop(key, None)
    monkeypatch.setattr(mod, "fetch_payload", lambda: payload)
    monkeypatch.setattr(sys, "argv", ["ecoflow-power-watch"])

    mod.main()

    row = all_rows(mod.SAMPLES_DB)[0]
    assert row["grid_v"] is None
    assert row["soc"] is None
    assert row["ac_in_w"] == 42
    assert row["chg_ac_wh"] == 1000


def test_recording_failure_does_not_block_outage_alert(mod, monkeypatch, capsys, tmp_path):
    """Catches a recording failure (here: a database directory that cannot
    be created) silencing the outage alert or skipping the STATE update --
    recording must stay fully isolated from the existing logic."""
    blocked = tmp_path / "blocked"
    blocked.write_text("not a directory")
    monkeypatch.setattr(mod, "SAMPLES_DB", str(blocked / "samples.db"))

    with open(mod.STATE, "w") as fh:
        json.dump({"live": True}, fh)

    payload = make_payload({"inv.acInVol": 0})
    monkeypatch.setattr(mod, "fetch_payload", lambda: payload)
    monkeypatch.setattr(sys, "argv", ["ecoflow-power-watch"])

    mod.main()

    assert len(mod.push_calls) == 1
    with open(mod.STATE) as fh:
        assert json.load(fh)["live"] is False
    assert capsys.readouterr().err.strip() != ""


def test_dry_run_creates_no_database(mod, monkeypatch):
    """Catches dry-run side effects: --dry-run must evaluate and report
    without ever touching disk for the sample history."""
    payload = make_payload()
    monkeypatch.setattr(mod, "fetch_payload", lambda: payload)
    monkeypatch.setattr(sys, "argv", ["ecoflow-power-watch", "--dry-run"])

    mod.main()

    assert not os.path.exists(mod.SAMPLES_DB)


def test_two_runs_at_different_times_produce_two_rows(mod, monkeypatch):
    """Catches a non-idempotent schema or insert path that would raise on
    the second run -- an error that recording's own isolation would then
    swallow as a silently dropped row instead of a visible crash."""
    payload = make_payload()
    monkeypatch.setattr(mod, "fetch_payload", lambda: payload)
    monkeypatch.setattr(sys, "argv", ["ecoflow-power-watch"])

    clock = iter([1_700_000_000.0, 1_700_000_070.0])
    monkeypatch.setattr(mod.time, "time", lambda: next(clock))

    mod.main()
    mod.main()

    rows = all_rows(mod.SAMPLES_DB)
    assert len(rows) == 2
