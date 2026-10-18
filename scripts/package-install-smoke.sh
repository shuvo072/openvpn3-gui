#!/bin/sh
# Opt-in real APT checks in disposable containers only. Never run on the host.
set -eu
if [ ! -f /.dockerenv ] || [ "${OPENVPN3_PACKAGE_TEST_CONTAINER:-}" != 1 ] || [ "$(id -u)" != 0 ]; then
    echo 'Run only in a disposable Docker container with OPENVPN3_PACKAGE_TEST_CONTAINER=1.' >&2
    exit 2
fi
PROJECT_DIR=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
cd "$PROJECT_DIR"
VERSION=$(/usr/bin/python3 -c 'from openvpn3_gui import __version__; print(__version__)')
TEST_STAGE=$(mktemp -d)
trap 'rm -rf "$TEST_STAGE"' EXIT HUP INT TERM
mkdir -p "$TEST_STAGE/fixture/DEBIAN" "$TEST_STAGE/private"
chmod 700 "$TEST_STAGE/private"
cat > "$TEST_STAGE/fixture/DEBIAN/control" <<'CONTROL'
Package: openvpn3
Version: 0.0.0-test
Architecture: all
Maintainer: Test Fixture <fixture@example.invalid>
Description: Empty dependency fixture for isolated package tests
CONTROL
dpkg-deb --root-owner-group --build "$TEST_STAGE/fixture" "$TEST_STAGE/openvpn3.deb" > /dev/null
dpkg -i "$TEST_STAGE/openvpn3.deb" > /dev/null
cp "dist/openvpn3-tui_${VERSION}_all.deb" "dist/openvpn3-gui_${VERSION}_all.deb" "$TEST_STAGE/private/"
chmod 600 "$TEST_STAGE/private/"*.deb
if [ "${1:-headless}" = upgrade ]; then
    test -n "${OLD_GUI_DEB:-}"
    apt-get install -y "$OLD_GUI_DEB" > "$TEST_STAGE/old-install.log" 2>&1
    printf 'y\n' | ./scripts/install-deb.sh "$TEST_STAGE/private/openvpn3-gui_${VERSION}_all.deb" > "$TEST_STAGE/install.log" 2>&1 || { cat "$TEST_STAGE/install.log"; exit 1; }
    openvpn3-gui --version
    test "$(dpkg-query -S /usr/share/openvpn3-gui/openvpn3_gui/backend.py)" = 'openvpn3-tui: /usr/share/openvpn3-gui/openvpn3_gui/backend.py'
else
    printf 'y\n' | ./scripts/install-deb.sh "$TEST_STAGE/private/openvpn3-tui_${VERSION}_all.deb" > "$TEST_STAGE/install.log" 2>&1 || { cat "$TEST_STAGE/install.log"; exit 1; }
    /usr/bin/python3 - <<'PY'
import importlib.util
assert importlib.util.find_spec('cairo') is None, 'Cairo unexpectedly installed'
import gi
try:
    gi.require_version('Gtk', '3.0')
except ValueError:
    pass
else:
    raise AssertionError('GTK unexpectedly installed')
PY
fi
if grep -q 'unsandboxed' "$TEST_STAGE/install.log"; then
    cat "$TEST_STAGE/install.log"
    exit 1
fi
TUI_TEST_LAUNCHER=/usr/bin/openvpn3-tui /usr/bin/python3 scripts/tui-smoke.py
openvpn3-tui --version
REMOVE_PACKAGES='openvpn3-tui'
if [ "${1:-headless}" = upgrade ]; then
    REMOVE_PACKAGES='openvpn3-gui openvpn3-tui'
fi
# Intentional splitting of these fixed package names.
# shellcheck disable=SC2086
apt-get remove -y $REMOVE_PACKAGES > "$TEST_STAGE/remove.log" 2>&1 || { cat "$TEST_STAGE/remove.log"; exit 1; }
test ! -e /usr/bin/openvpn3-tui
test ! -e /usr/bin/openvpn3-gui
test ! -e /usr/share/openvpn3-gui/openvpn3_gui/backend.py
printf '%s\n' 'PASS: real APT install, installed terminal client, private-path staging, ownership and removal (empty OpenVPN dependency fixture).'
