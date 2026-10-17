#!/bin/sh
# Stage local packages outside private home directories for APT's _apt user.
set -eu

if [ "$#" -gt 1 ]; then
    echo "Usage: $0 [path/to/openvpn3-gui.deb]" >&2
    exit 2
fi
PROJECT_DIR=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
if [ "$#" -eq 1 ]; then
    PACKAGE_FILE=$1
else
    if [ ! -f "$PROJECT_DIR/openvpn3_gui/__init__.py" ]; then
        echo "Usage: $0 path/to/openvpn3-gui.deb" >&2
        exit 2
    fi
    PACKAGE_VERSION=$(PYTHONPATH="$PROJECT_DIR" /usr/bin/python3 -c 'from openvpn3_gui import __version__; print(__version__)')
    PACKAGE_FILE="$PROJECT_DIR/dist/openvpn3-gui_${PACKAGE_VERSION}_all.deb"
fi
if [ ! -f "$PACKAGE_FILE" ] || [ ! -r "$PACKAGE_FILE" ]; then
    echo "Package not readable: $PACKAGE_FILE. Run 'make deb' first." >&2
    exit 1
fi
if [ "$(dpkg-deb --field "$PACKAGE_FILE" Package)" != openvpn3-gui ]; then
    echo "Expected an openvpn3-gui Debian package." >&2
    exit 1
fi

# Use /tmp explicitly: TMPDIR can itself be inside a private home directory.
# Only this uniquely named directory and the package copy are made readable.
INSTALL_STAGE=$(mktemp -d /tmp/openvpn3-gui-install.XXXXXXXXXX)
trap 'rm -rf -- "$INSTALL_STAGE"' EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM
install -m 644 -- "$PACKAGE_FILE" "$INSTALL_STAGE/openvpn3-gui.deb"
chmod 755 "$INSTALL_STAGE"
cd /tmp
if [ "$(id -u)" -eq 0 ]; then
    apt-get install "$INSTALL_STAGE/openvpn3-gui.deb"
else
    sudo apt-get install "$INSTALL_STAGE/openvpn3-gui.deb"
fi
