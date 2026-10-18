#!/bin/sh
# Stage packages outside private home directories for APT's _apt user.
set -eu
if [ "$#" -gt 2 ]; then
    echo "Usage: $0 [openvpn3-gui.deb | openvpn3-tui.deb] [companion.deb]" >&2
    exit 2
fi
PROJECT_DIR=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
if [ "$#" -eq 0 ]; then
    if [ ! -f "$PROJECT_DIR/openvpn3_gui/__init__.py" ]; then
        echo "Usage: $0 path/to/openvpn3-gui.deb [path/to/openvpn3-tui.deb]" >&2
        exit 2
    fi
    PACKAGE_VERSION=$(PYTHONPATH="$PROJECT_DIR" /usr/bin/python3 -c 'from openvpn3_gui import __version__; print(__version__)')
    set -- "$PROJECT_DIR/dist/openvpn3-gui_${PACKAGE_VERSION}_all.deb"
fi
# The GUI's matching TUI dependency may be downloaded alongside it. Explicit
# two-file arguments also support renamed files and different directories.
if [ "$#" -eq 1 ] && [ -r "$1" ] && [ "$(dpkg-deb --field "$1" Package)" = openvpn3-gui ]; then
    if dpkg-deb --field "$1" Depends | grep -q 'openvpn3-tui'; then
        PACKAGE_VERSION=$(dpkg-deb --field "$1" Version)
        COMPANION="$(dirname -- "$1")/openvpn3-tui_${PACKAGE_VERSION}_all.deb"
        if [ -r "$COMPANION" ]; then
            set -- "$1" "$COMPANION"
        fi
    fi
fi
INSTALL_STAGE=$(mktemp -d /tmp/openvpn3-gui-install.XXXXXXXXXX)
trap 'rm -rf -- "$INSTALL_STAGE"' EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM
SEEN_GUI='' SEEN_TUI='' GUI_VERSION='' TUI_VERSION='' GUI_NEEDS_TUI=''
for PACKAGE_FILE in "$@"; do
    if [ ! -f "$PACKAGE_FILE" ] || [ ! -r "$PACKAGE_FILE" ]; then
        echo "Package not readable: $PACKAGE_FILE. Run 'make deb' first." >&2
        exit 1
    fi
    PACKAGE_NAME=$(dpkg-deb --field "$PACKAGE_FILE" Package)
    PACKAGE_VERSION=$(dpkg-deb --field "$PACKAGE_FILE" Version)
    case "$PACKAGE_NAME" in
        openvpn3-gui)
            [ -z "$SEEN_GUI" ] || { echo 'Duplicate GUI package.' >&2; exit 1; }
            SEEN_GUI=1 GUI_VERSION=$PACKAGE_VERSION
            GUI_NEEDS_TUI=$(dpkg-deb --field "$PACKAGE_FILE" Depends | grep -o 'openvpn3-tui' || true)
            ;;
        openvpn3-tui)
            [ -z "$SEEN_TUI" ] || { echo 'Duplicate TUI package.' >&2; exit 1; }
            SEEN_TUI=1 TUI_VERSION=$PACKAGE_VERSION
            ;;
        *) echo 'Expected an openvpn3-gui or openvpn3-tui Debian package.' >&2; exit 1 ;;
    esac
    install -m 644 -- "$PACKAGE_FILE" "$INSTALL_STAGE/$PACKAGE_NAME.deb"
done
if [ -n "$GUI_NEEDS_TUI" ]; then
    if [ -z "$SEEN_TUI" ]; then
        INSTALLED_TUI=$(dpkg-query -W -f='${Status} ${Version}' openvpn3-tui 2>/dev/null || true)
        if [ "$INSTALLED_TUI" != "install ok installed $GUI_VERSION" ]; then
            echo "Download openvpn3-tui_${GUI_VERSION}_all.deb beside the GUI package, or pass both files to this helper." >&2
            exit 1
        fi
    elif [ "$GUI_VERSION" != "$TUI_VERSION" ]; then
        echo 'GUI and TUI packages must have matching versions.' >&2
        exit 1
    fi
fi
chmod 755 "$INSTALL_STAGE"
cd /tmp
if [ "$(id -u)" -eq 0 ]; then
    apt-get install "$INSTALL_STAGE"/*.deb
else
    sudo apt-get install "$INSTALL_STAGE"/*.deb
fi
