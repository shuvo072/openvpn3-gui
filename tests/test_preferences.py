"""Safe defaults, persistence, and system appearance precedence."""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from openvpn3_gui.preferences import (
    is_dark,
    preference_path,
    read_mode,
    write_mode,
    read_keep_running,
    write_keep_running,
)


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


class TrayPreferenceTests(unittest.TestCase):
    def test_defaults_validation_and_independent_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            self.assertTrue(read_keep_running(path))
            write_mode("dark", path)
            write_keep_running(False, path)
            self.assertEqual(read_mode(path), "dark")
            self.assertFalse(read_keep_running(path))
            write_mode("light", path)
            self.assertFalse(read_keep_running(path))
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            for value in ('"false"', "0", "null"):
                path.write_text('{"keep_running": ' + value + "}")
                self.assertTrue(read_keep_running(path))
            with self.assertRaises(ValueError):
                write_keep_running("false", path)
