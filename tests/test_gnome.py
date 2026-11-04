import json, os, shutil, subprocess, unittest

from tests.helpers import ROOT

NODE = shutil.which("node")
RENDER = os.path.join(ROOT, "tests", "gnome", "render.mjs")


@unittest.skipUnless(NODE, "node is needed to load the GNOME extension")
class GnomeRender(unittest.TestCase):
    def render(self, line):
        p = subprocess.run([NODE, RENDER, line], capture_output=True, text=True, cwd=ROOT)
        self.assertEqual(p.returncode, 0, p.stderr)
        return json.loads(p.stdout)

    def test_normal_reading(self):
        d = self.render('{"soc":97,"state":"discharging","watts":300,"minutes":75}')
        self.assertEqual(d["label"], "97%")
        self.assertEqual(d["detail"], "97% · Descargando 300 W · 1 h 15 min restantes")

    def test_missing_soc_is_no_reading(self):
        # --panel prints soc: null when the payload has no charge field; the
        # top bar must not read "null%" with an empty-battery glyph.
        d = self.render('{"soc":null,"state":"idle","watts":0,"minutes":null}')
        self.assertEqual((d["label"], d["detail"]), ("--", "Sin lectura"))


if __name__ == "__main__":
    unittest.main()
