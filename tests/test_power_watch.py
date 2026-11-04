import json, os, sys, tempfile, time, unittest
from datetime import datetime
from unittest import mock

from tests.helpers import load_script

DEAD = {"volts": 0.0, "in_watts": 0.0, "out_watts": 300.0, "soc": 97, "dsg_min": 120}


class WatchCase(unittest.TestCase):
    def setUp(self):
        self.w = load_script("core/ecoflow-power-watch")
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.w.STATE = os.path.join(self.tmp.name, "state.json")
        self.w.LOG = os.path.join(self.tmp.name, "share", "outages.log")
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


if __name__ == "__main__":
    unittest.main()
