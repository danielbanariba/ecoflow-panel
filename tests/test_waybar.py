import json, os, subprocess, tempfile, unittest

from tests.helpers import ROOT

SCRIPT = os.path.join(ROOT, "waybar", "ecoflow-waybar")


class Waybar(unittest.TestCase):
    def run_with(self, panel_line):
        with tempfile.TemporaryDirectory() as home:
            bin_ = os.path.join(home, ".local", "bin")
            os.makedirs(bin_)
            fake = os.path.join(bin_, "ecoflow-battery")
            with open(fake, "w") as fh:
                fh.write(f"#!/bin/sh\ncat <<'J'\n{panel_line}\nJ\n")
            os.chmod(fake, 0o755)
            env = dict(os.environ, HOME=home)
            p = subprocess.run(["bash", SCRIPT], env=env, capture_output=True, text=True)
        return p

    def test_normal_reading(self):
        p = self.run_with('{"soc": 97, "state": "charging", "watts": 300, "minutes": 75}')
        d = json.loads(p.stdout)
        self.assertEqual((d["text"], d["class"], d["percentage"]), ("97%", "normal charging", 97))
        self.assertIn("1 h 15 min restantes", d["tooltip"])

    def test_missing_soc_renders_as_no_reading(self):
        # ecoflow-battery --panel prints soc: null when the payload carries no
        # charge field. waybar must get a JSON line, not a traceback.
        p = self.run_with('{"soc": null, "state": "idle", "watts": 0, "minutes": null}')
        self.assertEqual(p.returncode, 0, p.stderr)
        d = json.loads(p.stdout)
        self.assertEqual((d["text"], d["class"]), ("--", "error"))


if __name__ == "__main__":
    unittest.main()
