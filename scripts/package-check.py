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
first = hashlib.sha256(package.read_bytes()).hexdigest()
subprocess.run([str(ROOT / "scripts" / "build-deb.sh")], check=True)
assert (
    hashlib.sha256(package.read_bytes()).hexdigest() == first
), "Package builds must be reproducible"

with tempfile.TemporaryDirectory(prefix="openvpn3-package-check-") as temporary:
    stage = Path(temporary)
    subprocess.run(["dpkg-deb", "-R", str(package), str(stage)], check=True)
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
