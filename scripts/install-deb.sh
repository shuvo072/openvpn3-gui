#!/bin/sh
# Stage packages outside private home directories for APT's _apt user.
set -eu
if [ "$#" -gt 1 ]; then
    echo "Usage: $0 [openvpn3-gui.deb | openvpn3-tui.deb]" >&2
    exit 2
fi
PROJECT_DIR=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
if [ "$#" -eq 0 ]; then
    if [ ! -f "$PROJECT_DIR/openvpn3_gui/__init__.py" ]; then
        echo "Usage: $0 path/to/openvpn3-gui.deb" >&2
        exit 2
    fi
    PACKAGE_VERSION=$(PYTHONPATH="$PROJECT_DIR" /usr/bin/python3 -c 'from openvpn3_gui import __version__; print(__version__)')
    set -- "$PROJECT_DIR/dist/openvpn3-gui_${PACKAGE_VERSION}_all.deb"
fi
INSTALL_STAGE=$(mktemp -d /tmp/openvpn3-gui-install.XXXXXXXXXX)
trap 'rm -rf -- "$INSTALL_STAGE"' EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM
PACKAGE_FILE=$1
if [ ! -f "$PACKAGE_FILE" ] || [ ! -r "$PACKAGE_FILE" ]; then
    echo "Package not readable: $PACKAGE_FILE. Run 'make deb' first." >&2
    exit 1
fi
PACKAGE_NAME=$(dpkg-deb --field "$PACKAGE_FILE" Package)
case "$PACKAGE_NAME" in
    openvpn3-gui|openvpn3-tui) ;;
    *) echo 'Expected an openvpn3-gui or openvpn3-tui Debian package.' >&2; exit 1 ;;
esac
install -m 644 -- "$PACKAGE_FILE" "$INSTALL_STAGE/$PACKAGE_NAME.deb"
chmod 755 "$INSTALL_STAGE"
cd /tmp
if [ "$(id -u)" -eq 0 ]; then
    apt-get install "$INSTALL_STAGE"/*.deb
else
    sudo apt-get install "$INSTALL_STAGE"/*.deb
fi
