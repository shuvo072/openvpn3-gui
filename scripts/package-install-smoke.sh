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
MODE=${1:-headless}
case "$MODE" in headless|desktop|upgrade|split-upgrade) ;; *) exit 2 ;; esac
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
# Only the selected edition is available in the download directory at each step.
install_edition() {
    EDITION=$1
    rm -f "$TEST_STAGE/private/"*.deb
    cp "dist/openvpn3-${EDITION}_${VERSION}_all.deb" "$TEST_STAGE/private/"
    chmod 600 "$TEST_STAGE/private/"*.deb
    printf 'y\n' | ./scripts/install-deb.sh "$TEST_STAGE/private/openvpn3-${EDITION}_${VERSION}_all.deb" > "$TEST_STAGE/install.log" 2>&1 || { cat "$TEST_STAGE/install.log"; exit 1; }
    if grep -q 'unsandboxed' "$TEST_STAGE/install.log"; then
        cat "$TEST_STAGE/install.log"
        exit 1
    fi
    test "$(dpkg-query -S /usr/share/openvpn3-gui/openvpn3_gui/backend.py)" = "openvpn3-${EDITION}: /usr/share/openvpn3-gui/openvpn3_gui/backend.py"
    test "$(dpkg-query -S /usr/bin/openvpn3-tui)" = "openvpn3-${EDITION}: /usr/bin/openvpn3-tui"
    openvpn3-tui --version
    if [ "$EDITION" = gui ]; then
        openvpn3-gui --version
        test "$(dpkg-query -W -f='${Status}' openvpn3-tui 2>/dev/null || true)" != 'install ok installed'
    else
        test ! -e /usr/bin/openvpn3-gui
    fi
}
case "$MODE" in
    upgrade)
        test -n "${OLD_GUI_DEB:-}"
        apt-get install -y "$OLD_GUI_DEB" > "$TEST_STAGE/old-install.log" 2>&1
        install_edition gui
        ;;
    split-upgrade)
        test -n "${OLD_GUI_DEB:-}" && test -n "${OLD_TUI_DEB:-}"
        apt-get install -y "$OLD_GUI_DEB" "$OLD_TUI_DEB" > "$TEST_STAGE/old-install.log" 2>&1
        install_edition gui
        ;;
    desktop) install_edition gui ;;
    headless)
        install_edition tui
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
        ;;
esac
TUI_TEST_LAUNCHER=/usr/bin/openvpn3-tui /usr/bin/python3 scripts/tui-smoke.py
if [ "$MODE" != headless ]; then
    # Exercise both directions and ensure removal does not delete the new owner.
    install_edition tui
    TUI_TEST_LAUNCHER=/usr/bin/openvpn3-tui /usr/bin/python3 scripts/tui-smoke.py
    install_edition gui
    TUI_TEST_LAUNCHER=/usr/bin/openvpn3-tui /usr/bin/python3 scripts/tui-smoke.py
fi
apt-get remove -y "openvpn3-$EDITION" > "$TEST_STAGE/remove.log" 2>&1 || { cat "$TEST_STAGE/remove.log"; exit 1; }
test ! -e /usr/bin/openvpn3-tui
test ! -e /usr/bin/openvpn3-gui
test ! -e /usr/share/openvpn3-gui/openvpn3_gui/backend.py
printf '%s\n' "PASS: real APT $MODE install from one file, installed terminal client, private-path staging, ownership and removal (empty OpenVPN dependency fixture)."
