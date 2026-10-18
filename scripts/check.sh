#!/bin/sh
# Run in a graphical session, or through dbus-run-session + xvfb-run in CI.
set -eu
PROJECT_DIR=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
cd "$PROJECT_DIR"
/usr/bin/python3 -m unittest discover -s tests -v
/usr/bin/python3 -m compileall -q openvpn3_gui scripts tests
/usr/bin/python3 scripts/tui-smoke.py
/usr/bin/python3 scripts/tray-smoke.py
/usr/bin/python3 scripts/gui-smoke.py
/usr/bin/python3 scripts/ux-smoke.py
/usr/bin/python3 scripts/resilience-smoke.py
/usr/bin/python3 scripts/layout-smoke.py
/usr/bin/python3 scripts/appearance-traffic-smoke.py
desktop-file-validate packaging/openvpn3-gui.desktop
shellcheck scripts/build-deb.sh scripts/install-deb.sh scripts/check.sh scripts/package-install-smoke.sh
./scripts/build-deb.sh
/usr/bin/python3 scripts/installer-check.py
/usr/bin/python3 scripts/package-check.py
