import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from digimon.__main__ import default_home
from digimon.config import DEFAULT, read, write_json


class SettingsLocationTests(unittest.TestCase):
    def test_new_and_existing_settings_on_each_platform(self):
        for platform in ("win32", "darwin", "linux"):
            with self.subTest(platform=platform), tempfile.TemporaryDirectory() as folder:
                home = Path(folder)
                parent = home / "Library" / "Application Support" if platform == "darwin" else home
                current = parent / ("digimon" if platform == "linux" else "DigiMon")
                legacy = parent / ("aprs-watch" if platform == "linux" else "APRSWatch")
                with patch("digimon.__main__.sys.platform", platform), \
                     patch("digimon.__main__.Path.home", return_value=home), \
                     patch.dict(os.environ, LOCALAPPDATA=folder, XDG_CONFIG_HOME=folder):
                    self.assertEqual(default_home(), current)
                    write_json(legacy / "config.json", {
                        "callsign": "G0ABC-1", "login": "G0ABC-W",
                        "email": {"password_env": "APRS_WATCH_SMTP_PASSWORD"},
                    })
                    write_json(legacy / "data" / "status.json", {"missing": True})
                    current.mkdir(parents=True, exist_ok=True)
                    self.assertEqual(default_home(), legacy)
                    self.assertTrue((default_home() / "data" / "status.json").is_file())
                    cfg = read(default_home() / "config.json")
                    self.assertEqual(cfg["callsign"], "G0ABC-1")
                    self.assertEqual(cfg["email"]["password_env"], "APRS_WATCH_SMTP_PASSWORD")
                    write_json(current / "config.json", cfg)
                    self.assertEqual(default_home(), current)

    def test_new_settings_require_station_and_use_digimon_password_variable(self):
        self.assertEqual(DEFAULT["callsign"], "")
        self.assertEqual(DEFAULT["login"], "")
        self.assertEqual(DEFAULT["email"]["password_env"], "DIGIMON_SMTP_PASSWORD")


if __name__ == "__main__":
    unittest.main()
