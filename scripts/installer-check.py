#!/usr/bin/python3
"""Exercise staging and failure handling without privilege or system changes."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from openvpn3_gui import __version__

installer = ROOT / "scripts/install-deb.sh"
package = ROOT / "dist" / f"openvpn3-gui_{__version__}_all.deb"

with tempfile.TemporaryDirectory(prefix="openvpn3-installer-check-") as temporary:
    private = Path(temporary)
    source = private / "package with spaces.deb"
    source.write_bytes(package.read_bytes())
    source.chmod(0o600)
    server_package = private / f"openvpn3-tui_{__version__}_all.deb"
    server_package.write_bytes((ROOT / "dist" / server_package.name).read_bytes())
    server_package.chmod(0o600)
    binaries = private / "bin"
    binaries.mkdir()
    observation = private / "observation.json"
    sudo_marker = private / "sudo-used"
    standalone = private / "downloaded files" / "install-openvpn3-gui.sh"
    standalone.parent.mkdir()
    standalone.write_bytes((ROOT / "dist/install-openvpn3-gui.sh").read_bytes())
    standalone.chmod(0o755)
    stubs = {
        "id": '#!/bin/sh\nprintf "%s\\n" "$TEST_UID"\n',
        "sudo": '#!/bin/sh\ntouch "$TEST_SUDO_MARKER"\nexec "$@"\n',
        "apt-get": """#!/usr/bin/python3
import hashlib, json, os, pathlib, sys
assert len(sys.argv) == 3 and sys.argv[1] == "install", sys.argv
for argument in sys.argv[2:]:
    item = pathlib.Path(argument)
    assert item.stat().st_mode & 0o777 == 0o644
    assert item.parent.stat().st_mode & 0o777 == 0o755
package = pathlib.Path(sys.argv[2])
assert package.is_absolute() and package.parent.parent == pathlib.Path("/tmp")
assert package.parent.stat().st_mode & 0o777 == 0o755
assert package.stat().st_mode & 0o777 == 0o644
assert pathlib.Path.cwd() == pathlib.Path("/tmp")
pathlib.Path(os.environ["TEST_OBSERVATION"]).write_text(json.dumps({
    "path": str(package), "digest": hashlib.sha256(package.read_bytes()).hexdigest()
}))
sys.exit(int(os.environ["TEST_APT_STATUS"]))
""",
    }
    for name, contents in stubs.items():
        executable = binaries / name
        executable.write_text(contents)
        executable.chmod(0o755)
    environment = {
        **os.environ,
        "PATH": f"{binaries}:{os.environ['PATH']}",
        "TMPDIR": str(private),
        "TEST_OBSERVATION": str(observation),
        "TEST_SUDO_MARKER": str(sudo_marker),
    }
    for helper, uid, status in [
        (installer, "1000", 0),
        (installer, "1000", 100),
        (installer, "1000", 130),
        (installer, "0", 0),
        (standalone, "1000", 0),
        (standalone, "1000", 100),
    ]:
        sudo_marker.unlink(missing_ok=True)
        result = subprocess.run(
            [str(helper), str(source)],
            env={**environment, "TEST_UID": uid, "TEST_APT_STATUS": str(status)},
            capture_output=True,
            text=True,
        )
        assert result.returncode == status, result.stderr
        record = json.loads(observation.read_text())
        assert record["digest"] == hashlib.sha256(source.read_bytes()).hexdigest()
        assert not Path(record["path"]).parent.exists(), "Staging directory leaked"
        assert sudo_marker.exists() == (uid != "0")
        assert private.stat().st_mode & 0o777 == 0o700
        assert source.stat().st_mode & 0o777 == 0o600

    # The server package installs on its own; no GUI dependency is staged.
    result = subprocess.run(
        [str(standalone), str(server_package)],
        env={**environment, "TEST_UID": "1000", "TEST_APT_STATUS": "0"},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    record = json.loads(observation.read_text())
    assert record["digest"] == hashlib.sha256(server_package.read_bytes()).hexdigest()
    assert not Path(record["path"]).parent.exists()
    observation.unlink()
    missing_argument = subprocess.run(
        [str(standalone)], env=environment, capture_output=True, text=True
    )
    assert missing_argument.returncode == 2 and "Usage:" in missing_argument.stderr
    assert not observation.exists()
    invalid = private / "invalid.deb"
    invalid.write_text("not a Debian package")
    for arguments in [
        [str(private / "missing.deb")],
        [str(invalid)],
        ["a", "b"],
        [str(source), str(source)],
        [str(source), str(server_package)],
    ]:
        result = subprocess.run(
            [str(installer), *arguments], env=environment, capture_output=True
        )
        assert result.returncode != 0
        assert not observation.exists(), "Invalid input reached APT"

print(
    "PASS: installer staging permissions, private paths with spaces, TMPDIR isolation, "
    "sudo/root paths, standalone helper, failure/cancellation exit status, cleanup, invalid input."
)
