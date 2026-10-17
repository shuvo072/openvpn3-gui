#!/usr/bin/python3
"""Opt-in real-service check using one temporary profile; never starts a tunnel."""

from pathlib import Path
import re
import sys
import tempfile
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from openvpn3_gui.backend import Backend

backend = Backend()
name = "OpenVPN3-GUI-test-" + uuid.uuid4().hex
created_path = None
try:
    with tempfile.TemporaryDirectory(prefix="openvpn3-gui-integration-") as temporary:
        profile = Path(temporary) / "test.ovpn"
        profile.write_text(
            "client\ndev tun\nproto udp\nremote 127.0.0.1 1194\nauth-user-pass\nnobind\n"
        )
        output = backend.read("config-import", "--config", str(profile), "--name", name)
        match = re.search(
            r"Configuration path:\s*(/net/openvpn/v3/configuration/\S+)", output
        )
        if not match:
            # Import may have succeeded even if CLI formatting changed. Recover
            # solely by the random name reserved for this test, never a user name.
            imported = [p for p in backend.profiles() if p["name"] == name]
            if len(imported) == 1:
                created_path = imported[0]["path"]
            raise RuntimeError("Could not parse import output")
        created_path = match[1]
        assert any(
            p["path"] == created_path and p["name"] == name for p in backend.profiles()
        )
        backend.read(
            "config-manage", "--path", created_path, "--rename", name + "-renamed"
        )
        backend.read(
            "config-manage", "--path", created_path, "--tag", "gui-integration"
        )
        assert any(
            p["path"] == created_path and p["name"] == name + "-renamed"
            for p in backend.profiles()
        )
        assert "127.0.0.1" in backend.dump_profile(created_path)
        backend.read("config-acl", "--path", created_path, "--show")
        backend.read(
            "config-manage", "--path", created_path, "--remove-tag", "gui-integration"
        )
finally:
    if created_path:
        backend.read("config-remove", "--path", created_path, "--force")
        assert all(p["path"] != created_path for p in backend.profiles())
print(
    "PASS: real-service temporary profile import, exact identity, rename, tags, export, ACL read, and cleanup. No VPN session was started."
)
