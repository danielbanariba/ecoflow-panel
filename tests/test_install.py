import json, os, subprocess, tempfile, time, unittest

from tests.helpers import ROOT

INSTALL = os.path.join(ROOT, "install.sh")


class InstallCase(unittest.TestCase):
    """install.sh against a throwaway HOME. curl and systemctl are stubs, and
    the proxy points at a closed port, so nothing leaves the machine."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = os.path.join(self.tmp.name, "home")
        self.stubs = os.path.join(self.tmp.name, "stubs")
        os.makedirs(self.home)
        os.makedirs(self.stubs)
        self.stub("systemctl", "exit 0")
        self.stub("notify-send", "exit 0")
        self.stub("curl", "exit 22")
        dead = "http://127.0.0.1:9"
        self.env = {
            "HOME": self.home,
            "PATH": self.stubs + ":" + os.environ["PATH"],
            "XDG_CURRENT_DESKTOP": "",
            "https_proxy": dead, "HTTPS_PROXY": dead, "http_proxy": dead, "HTTP_PROXY": dead,
        }
        # A fresh cache so the closing 'Reading right now' needs no request.
        cache = os.path.join(self.home, ".cache")
        os.makedirs(cache)
        with open(os.path.join(cache, "ecoflow-battery.json"), "w") as fh:
            json.dump({"at": time.time() + 30, "data": {"ems.lcdShowSoc": 88}}, fh)

    def stub(self, name, body):
        path = os.path.join(self.stubs, name)
        with open(path, "w") as fh:
            fh.write("#!/bin/sh\n" + body + "\n")
        os.chmod(path, 0o755)

    def install(self, *args, cwd=None):
        return subprocess.run(["bash", INSTALL, *args], env=self.env, cwd=cwd or self.home,
                              capture_output=True, text=True, timeout=60)


class CredentialsKept(InstallCase):
    def test_keys_written_with_spaces_are_not_overwritten(self):
        # ecoflow-battery's conf() strips around '=', so this file works.
        text = "ACCESS_KEY = abc\nSECRET_KEY = def\nDEVICE_SN = SN1\n"
        conf = os.path.join(self.home, ".config", "ecoflow")
        os.makedirs(conf)
        path = os.path.join(conf, "credentials")
        with open(path, "w") as fh:
            fh.write(text)
        os.chmod(path, 0o600)

        p = self.install("--frontend", "none", "--no-watch")
        with open(path) as fh:
            self.assertEqual(fh.read(), text, p.stdout)
        self.assertIn("already present", p.stdout)
        self.assertIn("device serial already stored", p.stdout)


class UnknownFrontend(InstallCase):
    def test_unknown_value_fails_before_installing_anything(self):
        p = self.install("--frontend", "xfce", "--no-watch")
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("xfce", p.stderr)
        self.assertIn("kde | gnome | waybar | none", p.stderr)
        self.assertFalse(os.path.exists(os.path.join(self.home, ".local", "bin", "ecoflow-battery")))

    def test_missing_value_fails(self):
        p = self.install("--no-watch", "--frontend")
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("kde | gnome | waybar | none", p.stderr)

    def test_known_value_still_installs(self):
        p = self.install("--frontend", "none", "--no-watch")
        self.assertEqual(p.returncode, 0, p.stderr)


CURL_FROM_REPO = r'''out=""; url=""
while [ $# -gt 0 ]; do
  case "$1" in -o) out="$2"; shift ;; -*) ;; *) url="$1" ;; esac
  shift
done
cp "@ROOT@/${url#@RAW@/}" "$out"'''


class PipedFromCurl(InstallCase):
    RAW = "https://raw.githubusercontent.com/danielbanariba/ecoflow-panel/main"

    def setUp(self):
        super().setUp()
        # curl serves the repo's own files, as raw.githubusercontent.com would.
        self.stub("curl", CURL_FROM_REPO.replace("@RAW@", self.RAW).replace("@ROOT@", ROOT))

    def test_waybar_snippet_hint_points_somewhere_real(self):
        with open(INSTALL) as fh:
            p = subprocess.run(["bash", "-s", "--", "--frontend", "waybar", "--no-watch"],
                               stdin=fh, env=self.env, cwd=self.home,
                               capture_output=True, text=True, timeout=60)
        self.assertTrue(os.path.exists(os.path.join(self.home, ".local", "bin", "ecoflow-waybar")),
                        p.stdout + p.stderr)
        hint = next(l for l in p.stdout.splitlines() if "snippet to paste" in l)
        # Piped there is no checkout: './waybar/config.jsonc' names a file
        # in whatever directory the user happened to be standing in.
        self.assertIn(f"{self.RAW}/waybar/config.jsonc", hint)


if __name__ == "__main__":
    unittest.main()
