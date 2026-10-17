#!/usr/bin/python3
"""Reject release tags that do not match the source and package metadata."""

import argparse
import os
from pathlib import Path
import re


def validate(root, tag):
    match = re.fullmatch(r"v(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)", tag)
    if not match:
        raise ValueError("Use a stable version tag such as v0.3.1")
    version = tag[1:]
    source = (root / "openvpn3_gui/__init__.py").read_text()
    declared = re.search(r'^__version__ = "([^"]+)"$', source, re.MULTILINE)
    if not declared or declared[1] != version:
        raise ValueError("Tag does not match openvpn3_gui/__init__.py")
    control = (root / "packaging/control").read_text()
    if not re.search(rf"^Version: {re.escape(version)}$", control, re.MULTILINE):
        raise ValueError("Tag does not match packaging/control")
    if (
        not (root / "packaging/changelog")
        .read_text()
        .startswith(f"openvpn3-gui ({version}) ")
    ):
        raise ValueError("Tag does not match the newest changelog entry")
    if (
        f'"OpenVPN 3 GUI {version}"'
        not in (root / "packaging/openvpn3-gui.1").read_text()
    ):
        raise ValueError("Tag does not match the manual version")
    if f"openvpn3-gui_{version}_all.deb" not in (root / "README.md").read_text():
        raise ValueError("README must document the current package filename")
    return version


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tag")
    args = parser.parse_args()
    try:
        version = validate(Path(__file__).resolve().parent.parent, args.tag)
    except ValueError as error:
        parser.error(str(error))
    if output := os.environ.get("GITHUB_OUTPUT"):
        with open(output, "a") as stream:
            stream.write(f"version={version}\n")
    print(f"Release metadata matches v{version}")


if __name__ == "__main__":
    main()
