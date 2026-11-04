import io, json, os, sys, tempfile, time, unittest
from contextlib import redirect_stdout
from unittest import mock

from tests.helpers import load_script


class BatteryCase(unittest.TestCase):
    def setUp(self):
        self.b = load_script("core/ecoflow-battery")
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.b.CONF = os.path.join(self.tmp.name, "credentials")
        self.b.CACHE = os.path.join(self.tmp.name, "cache.json")
        self.write_conf("ACCESS_KEY=a\nSECRET_KEY=b\nDEVICE_SN=SN1\n")

    def write_conf(self, text):
        with open(self.b.CONF, "w") as fh:
            fh.write(text)

    def run_main(self, *args):
        out = io.StringIO()
        with mock.patch.object(sys, "argv", ["ecoflow-battery", *args]), redirect_stdout(out):
            rc = self.b.main()
        return rc, out.getvalue()


class CacheClock(BatteryCase):
    def test_cache_stamped_in_the_future_is_not_fresh(self):
        # The clock was stepped back an hour after this cache was written
        # (NTP correction, a wrong RTC at boot). now - at is negative, which
        # must not read as "younger than a minute" for the next hour.
        with open(self.b.CACHE, "w") as fh:
            json.dump({"at": time.time() + 3600, "data": {"ems.lcdShowSoc": 40}}, fh)
        api = {"code": "0", "data": {"ems.lcdShowSoc": 97}}
        with mock.patch.object(self.b, "call", return_value=api) as call:
            rc, out = self.run_main()
        self.assertEqual((rc, out.strip()), (0, "97%"))
        call.assert_called_once()

    def test_recent_cache_still_served(self):
        with open(self.b.CACHE, "w") as fh:
            json.dump({"at": time.time() - 5, "data": {"ems.lcdShowSoc": 40}}, fh)
        with mock.patch.object(self.b, "call") as call:
            rc, out = self.run_main()
        self.assertEqual(out.strip(), "40%")
        call.assert_not_called()


if __name__ == "__main__":
    unittest.main()
