"""Protect release publishing from mismatched or malformed version tags."""

from pathlib import Path
import runpy
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent
validate = runpy.run_path(str(ROOT / "scripts/release-check.py"))["validate"]


class ReleaseMetadataTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.files = {
            "openvpn3_gui/__init__.py": '__version__ = "1.2.3"\n',
            "packaging/control": "Package: openvpn3-gui\nVersion: 1.2.3\nProvides: openvpn3-tui (= 1.2.3)\nConflicts: openvpn3-tui\nReplaces: openvpn3-tui\n",
            "packaging/changelog": "openvpn3-gui (1.2.3) unstable; urgency=medium\n",
            "packaging/openvpn3-gui.1": '.TH OPENVPN3-GUI 1 "OpenVPN 3 GUI 1.2.3"\n',
            "packaging/control-tui": "Package: openvpn3-tui\nVersion: 1.2.3\nConflicts: openvpn3-gui\nReplaces: openvpn3-gui\n",
            "packaging/openvpn3-tui.1": '.TH OPENVPN3-TUI 1 "OpenVPN 3 TUI 1.2.3"\n',
            "README.md": "Install openvpn3-gui_1.2.3_all.deb and openvpn3-tui_1.2.3_all.deb\n",
        }
        for name, contents in self.files.items():
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(contents)

    def test_matching_release(self):
        self.assertEqual(validate(self.root, "v1.2.3"), "1.2.3")

    def test_rejects_unsafe_or_nonrelease_tags(self):
        for tag in ["1.2.3", "v1.2", "v01.2.3", "v1.2.3-beta", "v1.2.3\n", "v$(id)"]:
            with self.subTest(tag=tag), self.assertRaises(ValueError):
                validate(self.root, tag)

    def test_rejects_each_stale_metadata_file(self):
        for name, contents in self.files.items():
            with self.subTest(file=name):
                path = self.root / name
                path.write_text(contents.replace("1.2.3", "1.2.2"))
                with self.assertRaises(ValueError):
                    validate(self.root, "v1.2.3")
                path.write_text(contents)

    def test_rejects_separate_tui_dependency(self):
        path = self.root / "packaging/control"
        path.write_text(path.read_text() + "Depends: python3, openvpn3-tui (= 1.2.3)\n")
        with self.assertRaisesRegex(ValueError, "without a separate TUI"):
            validate(self.root, "v1.2.3")

    def test_rejects_version_only_in_old_changelog_entry(self):
        path = self.root / "packaging/changelog"
        path.write_text(
            "openvpn3-gui (1.2.4) unstable; urgency=medium\n" + path.read_text()
        )
        with self.assertRaises(ValueError):
            validate(self.root, "v1.2.3")


if __name__ == "__main__":
    unittest.main()
