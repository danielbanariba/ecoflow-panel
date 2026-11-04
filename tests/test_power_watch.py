import fcntl, json, os, subprocess, sys, tempfile, time, unittest
from datetime import datetime
from unittest import mock

from tests.helpers import ROOT, load_script

DEAD = {"volts": 0.0, "in_watts": 0.0, "out_watts": 300.0, "soc": 97, "dsg_min": 120}
DEAD_PAYLOAD = {"inv.acInVol": 0, "inv.inputWatts": 0, "inv.outputWatts": 300,
                "ems.lcdShowSoc": 97, "ems.dsgRemainTime": 120}


class WatchCase(unittest.TestCase):
    def setUp(self):
        self.w = load_script("core/ecoflow-power-watch")
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.w.STATE = os.path.join(self.tmp.name, "state.json")
        self.w.LOG = os.path.join(self.tmp.name, "share", "outages.log")
        self.w.LOCK = os.path.join(self.tmp.name, "watch.lock")
        self.w.SAMPLES_DB = os.path.join(self.tmp.name, "share", "samples.db")
        # main() fetches before it judges: stub the fetch with the payload
        # behind DEAD, and point HELPER nowhere, so no test can ever run the
        # real ~/.local/bin/ecoflow-battery (and through it the live API).
        self.w.HELPER = os.path.join(self.tmp.name, "no-such-helper")
        p = mock.patch.object(self.w, "fetch_payload", return_value=dict(DEAD_PAYLOAD))
        p.start()
        self.addCleanup(p.stop)
        # A PATH with nothing on it: no notify-send, no dconf.
        empty = os.path.join(self.tmp.name, "bin")
        os.mkdir(empty)
        p = mock.patch.dict(os.environ, {"PATH": empty})
        p.start()
        self.addCleanup(p.stop)

    def run_main(self, *args):
        with mock.patch.object(sys, "argv", ["ecoflow-power-watch", *args]):
            return self.w.main()


class NotifySendMissing(WatchCase):
    """The installer only warns when notify-send is absent ("desktop alerts
    will be silent"). The watcher must still record the transition, or the
    next tick sees the same transition again and re-sends the phone push."""

    def test_outage_is_announced_once_without_notify_send(self):
        with open(self.w.STATE, "w") as fh:
            json.dump({"live": True}, fh)
        with mock.patch.object(self.w, "reading", return_value=dict(DEAD)), \
             mock.patch.object(self.w, "ntfy_topic", return_value="topic"), \
             mock.patch("urllib.request.urlopen") as urlopen:
            self.assertEqual(self.run_main(), 0)
            self.assertEqual(self.run_main(), 0)
        self.assertEqual(urlopen.call_count, 1)
        with open(self.w.LOG) as fh:
            self.assertEqual(sum("\tcorte\t" in l for l in fh), 1)
        with open(self.w.STATE) as fh:
            self.assertEqual(json.load(fh), {"live": False})


class OutageAcrossDst(WatchCase):
    """The log holds naive local wall-clock stamps. Subtracting two of them
    across a DST change is off by the shift: an hour lost or gained."""

    def setUp(self):
        super().setUp()
        p = mock.patch.dict(os.environ, {"TZ": "America/Chicago"})
        p.start()
        self.addCleanup(p.stop)
        self.addCleanup(time.tzset)
        time.tzset()
        os.makedirs(os.path.dirname(self.w.LOG))

    def minutes(self, started, ended_epoch):
        with open(self.w.LOG, "w") as fh:
            fh.write(f"{started}\tcorte\t97\t\n")
        return self.w.outage_minutes(datetime.fromtimestamp(ended_epoch))

    def test_fall_back(self):
        # 00:50 CDT, then the clocks go 02:00 CDT -> 01:00 CST; 80 min later
        # the wall reads 01:10 CST.
        start = datetime(2026, 11, 1, 0, 50).timestamp()
        self.assertEqual(self.minutes("2026-11-01 00:50:00", start + 80 * 60), 80)

    def test_spring_forward(self):
        # 01:50 CST, then the clocks go 02:00 CST -> 03:00 CDT; 20 min later
        # the wall reads 03:10 CDT.
        start = datetime(2026, 3, 8, 1, 50).timestamp()
        self.assertEqual(self.minutes("2026-03-08 01:50:00", start + 20 * 60), 20)


class StateShape(WatchCase):
    """A state file holding valid JSON of the wrong shape counts as no state:
    the run stays silent, as a first run does, and rewrites it."""

    def check(self, state):
        with open(self.w.STATE, "w") as fh:
            json.dump(state, fh)
        with mock.patch.object(self.w, "reading", return_value=dict(DEAD)), \
             mock.patch.object(self.w, "ntfy_topic", return_value="topic"), \
             mock.patch("urllib.request.urlopen") as urlopen:
            self.assertEqual(self.run_main(), 0)
        urlopen.assert_not_called()
        with open(self.w.STATE) as fh:
            self.assertEqual(json.load(fh), {"live": False})

    def test_top_level_bool(self):
        self.check(True)

    def test_top_level_list(self):
        self.check([{"live": True}])

    def test_live_not_a_bool(self):
        self.check({"live": "yes"})


class OverlappingRuns(WatchCase):
    """The timer's run and one started by hand can overlap. Both would read
    the old state, both see the transition, and both send it."""

    def test_second_run_stands_down_while_the_first_holds_the_lock(self):
        with open(self.w.STATE, "w") as fh:
            json.dump({"live": True}, fh)
        with mock.patch.object(self.w, "reading", return_value=dict(DEAD)), \
             mock.patch.object(self.w, "ntfy_topic", return_value="topic"), \
             mock.patch("urllib.request.urlopen") as urlopen:
            # Another run is mid-flight: it holds the lock.
            with open(self.w.LOCK, "w") as other:
                fcntl.flock(other, fcntl.LOCK_EX)
                self.assertEqual(self.run_main(), 0)
                urlopen.assert_not_called()
                self.assertFalse(os.path.exists(self.w.LOG))
                with open(self.w.STATE) as fh:
                    self.assertEqual(json.load(fh), {"live": True})
            # Once it is gone, the next run proceeds as usual.
            self.assertEqual(self.run_main(), 0)
            self.assertEqual(urlopen.call_count, 1)

    def test_run_that_stands_down_still_records_its_sample(self):
        import sqlite3
        with open(self.w.LOCK, "w") as other:
            fcntl.flock(other, fcntl.LOCK_EX)
            self.assertEqual(self.run_main(), 0)
        conn = sqlite3.connect(self.w.SAMPLES_DB)
        try:
            self.assertEqual(conn.execute("SELECT grid_v, soc FROM samples").fetchall(), [(0.0, 97)])
        finally:
            conn.close()

    def test_lock_is_released_between_runs(self):
        with mock.patch.object(self.w, "reading", return_value=dict(DEAD)):
            self.run_main()
        with open(self.w.LOCK, "w") as fh:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)   # raises if still held


class OverlappingProcesses(unittest.TestCase):
    """The same race with two real processes: a slow helper keeps both inside
    the window between reading the state and writing it."""

    def test_two_concurrent_runs_alert_once(self):
        with tempfile.TemporaryDirectory() as home:
            bin_ = os.path.join(home, ".local", "bin")
            stubs = os.path.join(home, "stubs")
            for d in (bin_, stubs, os.path.join(home, ".cache")):
                os.makedirs(d)
            sent = os.path.join(home, "sent")
            for path, body in (
                (os.path.join(bin_, "ecoflow-battery"),
                 'sleep 1; echo \'{"inv.acInVol": 0, "ems.lcdShowSoc": 97}\''),
                (os.path.join(stubs, "notify-send"), f'echo x >> "{sent}"'),
            ):
                with open(path, "w") as fh:
                    fh.write("#!/bin/sh\n" + body + "\n")
                os.chmod(path, 0o755)
            with open(os.path.join(home, ".cache", "ecoflow-power-watch.json"), "w") as fh:
                json.dump({"live": True}, fh)
            env = dict(os.environ, HOME=home, PATH=stubs + ":/usr/bin:/bin")
            cmd = [sys.executable, os.path.join(ROOT, "core", "ecoflow-power-watch")]
            procs = [subprocess.Popen(cmd, env=env, stdout=subprocess.DEVNULL,
                                      stderr=subprocess.DEVNULL) for _ in range(2)]
            for p in procs:
                self.assertEqual(p.wait(timeout=30), 0)
            with open(sent) as fh:
                self.assertEqual(len(fh.readlines()), 1)
            with open(os.path.join(home, ".local", "share", "ecoflow", "outages.log")) as fh:
                self.assertEqual(sum("\tcorte\t" in l for l in fh), 1)


if __name__ == "__main__":
    unittest.main()
