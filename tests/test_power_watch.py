import json, os, sys, tempfile, unittest
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


if __name__ == "__main__":
    unittest.main()
