"""Safe defaults, persistence, and system appearance precedence."""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from openvpn3_gui.preferences import is_dark, preference_path, read_mode, write_mode


class AppearanceTests(unittest.TestCase):
    def test_explicit_and_system_choices(self):
        self.assertTrue(is_dark("dark", 2))
        self.assertFalse(is_dark("light", 1))
        self.assertTrue(is_dark("system", 1))
        self.assertFalse(is_dark("system", 2, "prefer-dark"))
        self.assertTrue(is_dark("system", 0, "prefer-dark"))
        self.assertFalse(is_dark("system", None, "prefer-light", True))
        self.assertTrue(is_dark("system", None, fallback=True))
        self.assertFalse(is_dark("system"))

    def test_preferences_roundtrip_and_corrupt_defaults(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "app/settings.json"
            self.assertEqual(read_mode(path), "system")
            for mode in ("dark", "light", "system"):
                write_mode(mode, path)
                self.assertEqual(read_mode(path), mode)
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            for data in ("[1]", "broken", '{"appearance": "unknown"}', "null"):
                path.write_text(data)
                self.assertEqual(read_mode(path), "system")
            with self.assertRaises(ValueError):
                write_mode("unknown", path)

    def test_xdg_path_and_relative_fallback(self):
        with patch.dict("os.environ", {"XDG_CONFIG_HOME": "/tmp/config-example"}):
            self.assertEqual(
                preference_path(),
                Path("/tmp/config-example/openvpn3-gui/preferences.json"),
            )
        with patch.dict("os.environ", {"XDG_CONFIG_HOME": "relative"}):
            self.assertEqual(
                preference_path(), Path.home() / ".config/openvpn3-gui/preferences.json"
            )
