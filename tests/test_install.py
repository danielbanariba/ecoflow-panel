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


if __name__ == "__main__":
    unittest.main()
