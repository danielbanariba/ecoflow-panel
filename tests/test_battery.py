import io, json, os, sys, tempfile, time, unittest, urllib.error
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


class DiscoverStoresSerial(BatteryCase):
    DEVICES = {"code": "0", "data": [{"sn": "R331ZEB4ZE123456", "online": 1}]}

    def discover(self):
        with mock.patch.object(self.b, "call", return_value=self.DEVICES):
            return self.run_main("--discover")

    def test_file_without_a_device_sn_line(self):
        # A hand-written file with only the two keys, last line unterminated.
        self.write_conf("ACCESS_KEY=a\nSECRET_KEY=b")
        rc, out = self.discover()
        self.assertEqual(rc, 0)
        self.assertIn("stored DEVICE_SN=R331ZEB4ZE123456", out)
        self.assertEqual(self.b.conf(), {"ACCESS_KEY": "a", "SECRET_KEY": "b",
                                         "DEVICE_SN": "R331ZEB4ZE123456"})

    def test_template_line_is_filled_in_place(self):
        self.write_conf("ACCESS_KEY=a\nSECRET_KEY=b\nDEVICE_SN=\n")
        self.discover()
        with open(self.b.CONF) as fh:
            self.assertEqual(fh.read(), "ACCESS_KEY=a\nSECRET_KEY=b\nDEVICE_SN=R331ZEB4ZE123456\n")


class PickSocNonNumeric(BatteryCase):
    """The fallback scan took the first key ending in 'soc' and called
    float() on whatever it held, so a null in the payload was a traceback."""

    def test_null_primary_falls_through_to_a_numeric_soc(self):
        self.assertEqual(self.b.pick_soc({"ems.lcdShowSoc": None,
                                          "bmsMaster.f32ShowSoc": 96.7}), 97)

    def test_panel_with_only_a_null_soc_reports_none(self):
        with open(self.b.CACHE, "w") as fh:
            json.dump({"at": time.time(), "data": {"ems.lcdShowSoc": None}}, fh)
        rc, out = self.run_main("--panel")
        self.assertEqual(rc, 0)
        self.assertIsNone(json.loads(out)["soc"])


class CacheShape(BatteryCase):
    """Valid JSON is not necessarily our JSON: a cache of the wrong shape must
    be ignored and refetched, not crash the client."""

    def check(self, cached):
        with open(self.b.CACHE, "w") as fh:
            json.dump(cached, fh)
        api = {"code": "0", "data": {"ems.lcdShowSoc": 97}}
        with mock.patch.object(self.b, "call", return_value=api):
            rc, out = self.run_main()
        self.assertEqual((rc, out.strip()), (0, "97%"))

    def test_top_level_list(self):
        self.check([1, 2, 3])

    def test_no_data_key(self):
        self.check({"at": time.time()})

    def test_data_not_an_object(self):
        self.check({"at": time.time(), "data": [97]})

    def test_stamp_not_a_number(self):
        self.check({"at": "yesterday", "data": {"ems.lcdShowSoc": 40}})


class StaleFallback(BatteryCase):
    """docs/API.md: the client 'treats a stale reading as better than a
    rejected one'. An expired cache is still the answer when the API fails."""

    def setUp(self):
        super().setUp()
        with open(self.b.CACHE, "w") as fh:
            json.dump({"at": time.time() - 600, "data": {"ems.lcdShowSoc": 40}}, fh)

    def test_rejected_request_serves_the_old_reading(self):
        api = {"code": "1006", "message": "too many requests"}
        with mock.patch.object(self.b, "call", return_value=api):
            rc, out = self.run_main()
        self.assertEqual((rc, out.strip()), (0, "40%"))

    def test_network_failure_serves_the_old_reading(self):
        err = urllib.error.URLError("Temporary failure in name resolution")
        with mock.patch.object(self.b, "call", side_effect=err):
            rc, out = self.run_main("--panel")
        self.assertEqual((rc, json.loads(out)["soc"]), (0, 40))

    def test_force_still_reports_the_failure(self):
        # The outage watcher asks for --force: it needs a reading of now, and
        # judging the grid on a ten-minute-old one would hide an outage.
        api = {"code": "1006", "message": "too many requests"}
        with mock.patch.object(self.b, "call", return_value=api):
            rc, out = self.run_main("--json", "--force")
        self.assertEqual((rc, out), (2, ""))

    def test_no_cache_still_reports_the_failure(self):
        os.remove(self.b.CACHE)
        api = {"code": "1006", "message": "too many requests"}
        with mock.patch.object(self.b, "call", return_value=api):
            rc, out = self.run_main()
        self.assertEqual((rc, out), (2, ""))


if __name__ == "__main__":
    unittest.main()
