import json, os, subprocess, sys, unittest

from tests.helpers import ROOT

RENDER = os.path.join(ROOT, "tests", "kde", "render.py")


def evaluate(*exprs):
    p = subprocess.run([sys.executable, RENDER, *exprs], capture_output=True, text=True, cwd=ROOT)
    if p.returncode == 77:
        raise unittest.SkipTest("PySide6 (QtQml) is needed to load the plasmoid: " + p.stderr.strip())
    if p.returncode != 0:
        raise AssertionError(p.stderr)
    return json.loads(p.stdout)


class PlasmoidIcon(unittest.TestCase):
    """Breeze names its stepped battery glyphs battery-060 and
    battery-060-charging. Any other spelling misses, and Kirigami.Icon shows
    the generic 'battery' fallback, so the icon stops carrying the level."""

    def test_discharging_steps(self):
        self.assertEqual(evaluate("batteryIcon(0)", "batteryIcon(7)", "batteryIcon(60)",
                                  "batteryIcon(97)", "batteryIcon(100)"),
                         ["battery-000", "battery-010", "battery-060", "battery-100", "battery-100"])

    def test_charging_steps(self):
        self.assertEqual(evaluate('(state = "charging", batteryIcon(4))',
                                  '(state = "charging", batteryIcon(60))',
                                  '(state = "charging", batteryIcon(100))'),
                         ["battery-000-charging", "battery-060-charging", "battery-100-charging"])

    def test_no_reading(self):
        self.assertEqual(evaluate("batteryIcon(-1)"), ["battery-missing"])


if __name__ == "__main__":
    unittest.main()
