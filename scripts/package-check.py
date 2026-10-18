#!/usr/bin/python3
"""Inspect and execute an extracted package, without installing system files."""

import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from openvpn3_gui import __version__

package = ROOT / "dist" / f"openvpn3-gui_{__version__}_all.deb"
assert (ROOT / "dist/install-openvpn3-gui.sh").read_bytes() == (
    ROOT / "scripts/install-deb.sh"
).read_bytes()
subprocess.run(["sha256sum", "--check", "SHA256SUMS"], cwd=ROOT / "dist", check=True)
tui_package = ROOT / "dist" / f"openvpn3-tui_{__version__}_all.deb"
first = hashlib.sha256(package.read_bytes()).hexdigest()
tui_first = hashlib.sha256(tui_package.read_bytes()).hexdigest()
subprocess.run([str(ROOT / "scripts" / "build-deb.sh")], check=True)
assert (
    hashlib.sha256(package.read_bytes()).hexdigest() == first
), "Package builds must be reproducible"

assert hashlib.sha256(tui_package.read_bytes()).hexdigest() == tui_first
with tempfile.TemporaryDirectory(prefix="openvpn3-package-check-") as temporary:
    stage = Path(temporary)
    # Inspect ownership separately before extracting the co-installable packages.
    tui_stage = stage / "tui"
    subprocess.run(["dpkg-deb", "-R", str(tui_package), str(tui_stage)], check=True)
    tui_control = (tui_stage / "DEBIAN/control").read_text()
    assert (
        "gir1.2-gtk" not in tui_control
        and "vte" not in tui_control
        and "cairo" not in tui_control
    )
    tui_files = {
        p.relative_to(tui_stage)
        for p in tui_stage.rglob("*")
        if p.is_file() and "DEBIAN" not in p.parts
    }
    subprocess.run(
        ["md5sum", "--quiet", "-c", "DEBIAN/md5sums"], cwd=tui_stage, check=True
    )
    subprocess.run(["dpkg-deb", "-R", str(package), str(stage)], check=True)
    gui_files = {
        p.relative_to(stage)
        for p in stage.rglob("*")
        if p.is_file() and "DEBIAN" not in p.parts and tui_stage not in p.parents
    }
    assert not tui_files & gui_files, "Packages must not own the same files"
    assert f"openvpn3-tui (= {__version__})" in (stage / "DEBIAN/control").read_text()
    subprocess.run(["dpkg-deb", "-x", str(tui_package), str(stage)], check=True)
    subprocess.run([str(stage / "usr/bin/openvpn3-tui"), "--version"], check=True)
    # Importing the TUI must not load GTK, even when it is installed.
    environment_tui = {
        **os.environ,
        "PYTHONPATH": str(tui_stage / "usr/share/openvpn3-gui"),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    subprocess.run(
        [
            "/usr/bin/python3",
            "-c",
            "import sys; from openvpn3_gui import tui; assert 'gi.repository.Gtk' not in sys.modules",
        ],
        cwd=tui_stage,
        env=environment_tui,
        check=True,
    )
    launcher = stage / "usr/bin/openvpn3-gui"
    assert os.access(launcher, os.X_OK)
    environment = dict(os.environ)
    environment.pop("PYTHONDONTWRITEBYTECODE", None)
    result = subprocess.run(
        [str(launcher), "--version"],
        capture_output=True,
        text=True,
        check=True,
        env=environment,
    )
    assert __version__ in result.stdout
    help_result = subprocess.run(
        [str(launcher), "--help"],
        capture_output=True,
        text=True,
        check=True,
        env=environment,
    )
    assert "--demo" in help_result.stdout
    for file in stage.rglob("*"):
        assert file.suffix not in {
            ".ovpn",
            ".key",
            ".pem",
            ".pyc",
        }, f"Unexpected private/build artifact: {file}"
        assert not file.stat().st_mode & 0o002, f"World-writable package member: {file}"
    license_file = stage / "usr/share/doc/openvpn3-gui/LICENSE"
    assert license_file.read_bytes() == (ROOT / "LICENSE").read_bytes()
    assert "hasanshuvo.dev@gmail.com" in (stage / "DEBIAN/control").read_text()
    data = stage / "usr/share/openvpn3-gui/openvpn3_gui/data/demo-capabilities.json"
    assert data.is_file()
    icon = stage / "usr/share/openvpn3-gui/openvpn3_gui/data/app-icon.svg"
    assert icon.read_bytes() == (ROOT / "packaging/openvpn3-gui.svg").read_bytes()
    subprocess.run(["md5sum", "--quiet", "-c", "DEBIAN/md5sums"], cwd=stage, check=True)
    environment["PYTHONPATH"] = str(stage / "usr/share/openvpn3-gui")
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    subprocess.run(
        [
            "/usr/bin/python3",
            "-c",
            "from openvpn3_gui.backend import demo_commands; assert len(demo_commands()) == 16",
        ],
        cwd=stage,
        env=environment,
        check=True,
    )
print(
    f"PASS: extracted launcher, version/help, offline data, MIT license, permissions, checksums, private-file exclusion, reproducible .deb ({first[:16]}…)."
)
