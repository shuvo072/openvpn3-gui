#!/bin/sh
set -eu
umask 022
PROJECT_DIR=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
PACKAGE_VERSION=$(PYTHONPATH="$PROJECT_DIR" /usr/bin/python3 -c 'from openvpn3_gui import __version__; print(__version__)')
SOURCE_DATE_EPOCH=${SOURCE_DATE_EPOCH:-1792044000}
export SOURCE_DATE_EPOCH
BUILD_STAGE=$(mktemp -d)
trap 'rm -rf "$BUILD_STAGE"' EXIT HUP INT TERM
install -d "$PROJECT_DIR/dist"
for KIND in tui gui; do
    STAGE_DIR="$BUILD_STAGE/$KIND"
    DOC_DIR="$STAGE_DIR/usr/share/doc/openvpn3-$KIND"
    MODULE_DIR="$STAGE_DIR/usr/share/openvpn3-gui/openvpn3_gui"
    install -d "$STAGE_DIR/DEBIAN" "$STAGE_DIR/usr/bin" "$MODULE_DIR/data" "$DOC_DIR" "$STAGE_DIR/usr/share/man/man1"
    MODULES='__init__ backend traffic tui demo_cli'
    install -m 644 "$PROJECT_DIR"/openvpn3_gui/data/*.json "$MODULE_DIR/data/"
    install -m 755 "$PROJECT_DIR/openvpn3-tui" "$STAGE_DIR/usr/bin/"
    gzip -n -9 -c "$PROJECT_DIR/packaging/openvpn3-tui.1" > "$STAGE_DIR/usr/share/man/man1/openvpn3-tui.1.gz"
    if [ "$KIND" = tui ]; then
        CONTROL_FILE=control-tui
    else
        CONTROL_FILE=control
        MODULES="$MODULES __main__ app appearance preferences theme traffic_widget tray widgets"
        install -d "$STAGE_DIR/usr/share/applications" "$STAGE_DIR/usr/share/icons/hicolor/scalable/apps" "$DOC_DIR/packaging"
        install -m 644 "$PROJECT_DIR/packaging/openvpn3-gui.desktop" "$STAGE_DIR/usr/share/applications/"
        install -m 644 "$PROJECT_DIR/packaging/openvpn3-gui.svg" "$STAGE_DIR/usr/share/icons/hicolor/scalable/apps/"
        install -m 644 "$PROJECT_DIR/packaging/openvpn3-gui.svg" "$MODULE_DIR/data/app-icon.svg"
        install -m 644 "$PROJECT_DIR/packaging/openvpn3-gui.svg" "$DOC_DIR/packaging/"
        cp -R "$PROJECT_DIR/openvpn3_gui/data/tray" "$MODULE_DIR/data/tray"
        cp -R "$PROJECT_DIR/docs" "$DOC_DIR/docs"
    fi
    sed "s/^Version:.*/Version: $PACKAGE_VERSION/;s/openvpn3-tui (= [^)]*)/openvpn3-tui (= $PACKAGE_VERSION)/" "$PROJECT_DIR/packaging/$CONTROL_FILE" > "$STAGE_DIR/DEBIAN/control"
    install -m 755 "$PROJECT_DIR/openvpn3-$KIND" "$STAGE_DIR/usr/bin/"
    for MODULE in $MODULES; do
        install -m 644 "$PROJECT_DIR/openvpn3_gui/$MODULE.py" "$MODULE_DIR/"
    done
    install -m 644 "$PROJECT_DIR/README.md" "$PROJECT_DIR/LICENSE" "$PROJECT_DIR/CONTRIBUTING.md" "$PROJECT_DIR/SECURITY.md" "$DOC_DIR/"
    install -m 644 "$PROJECT_DIR/packaging/copyright" "$DOC_DIR/"
    gzip -n -9 -c "$PROJECT_DIR/packaging/changelog" > "$DOC_DIR/changelog.gz"
    gzip -n -9 -c "$PROJECT_DIR/packaging/openvpn3-$KIND.1" > "$STAGE_DIR/usr/share/man/man1/openvpn3-$KIND.1.gz"
    chmod 755 "$STAGE_DIR"
    find "$STAGE_DIR" -type d -exec chmod 755 {} +
    find "$STAGE_DIR" -type f -exec chmod 644 {} +
    chmod 755 "$STAGE_DIR/usr/bin/"*
    (cd "$STAGE_DIR" && find usr -type f -print0 | LC_ALL=C sort -z | xargs -0 md5sum > DEBIAN/md5sums)
    find "$STAGE_DIR" -exec touch -h -d "@$SOURCE_DATE_EPOCH" {} +
    dpkg-deb --root-owner-group --build "$STAGE_DIR" "$PROJECT_DIR/dist/openvpn3-${KIND}_${PACKAGE_VERSION}_all.deb"
done
install -m 755 "$PROJECT_DIR/scripts/install-deb.sh" "$PROJECT_DIR/dist/install-openvpn3-gui.sh"
(cd "$PROJECT_DIR/dist" && sha256sum "openvpn3-gui_${PACKAGE_VERSION}_all.deb" "openvpn3-tui_${PACKAGE_VERSION}_all.deb" install-openvpn3-gui.sh > SHA256SUMS)
