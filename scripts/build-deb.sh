#!/bin/sh
set -eu
umask 022
PROJECT_DIR=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
PACKAGE_VERSION=$(PYTHONPATH="$PROJECT_DIR" /usr/bin/python3 -c 'from openvpn3_gui import __version__; print(__version__)')
# Fixed release time unless the builder supplies a source timestamp.
SOURCE_DATE_EPOCH=${SOURCE_DATE_EPOCH:-1792044000}
export SOURCE_DATE_EPOCH
STAGE_DIR=$(mktemp -d)
trap 'rm -rf "$STAGE_DIR"' EXIT HUP INT TERM
install -d "$STAGE_DIR/DEBIAN" "$STAGE_DIR/usr/bin" "$STAGE_DIR/usr/share/openvpn3-gui/openvpn3_gui" \
    "$STAGE_DIR/usr/share/applications" "$STAGE_DIR/usr/share/icons/hicolor/scalable/apps" \
    "$STAGE_DIR/usr/share/doc/openvpn3-gui" "$STAGE_DIR/usr/share/man/man1" \
    "$STAGE_DIR/usr/share/openvpn3-gui/openvpn3_gui/data" "$PROJECT_DIR/dist"
sed "s/^Version:.*/Version: $PACKAGE_VERSION/" "$PROJECT_DIR/packaging/control" > "$STAGE_DIR/DEBIAN/control"
install -m 755 "$PROJECT_DIR/openvpn3-gui" "$STAGE_DIR/usr/bin/openvpn3-gui"
install -m 644 "$PROJECT_DIR"/openvpn3_gui/*.py "$STAGE_DIR/usr/share/openvpn3-gui/openvpn3_gui/"
install -m 644 "$PROJECT_DIR"/openvpn3_gui/data/*.json "$STAGE_DIR/usr/share/openvpn3-gui/openvpn3_gui/data/"
install -m 644 "$PROJECT_DIR/packaging/openvpn3-gui.desktop" "$STAGE_DIR/usr/share/applications/"
install -m 644 "$PROJECT_DIR/packaging/openvpn3-gui.svg" "$STAGE_DIR/usr/share/icons/hicolor/scalable/apps/"
install -m 644 "$PROJECT_DIR/README.md" "$STAGE_DIR/usr/share/doc/openvpn3-gui/"
install -m 644 "$PROJECT_DIR/LICENSE" "$STAGE_DIR/usr/share/doc/openvpn3-gui/"
install -m 644 "$PROJECT_DIR/CONTRIBUTING.md" "$PROJECT_DIR/SECURITY.md" "$STAGE_DIR/usr/share/doc/openvpn3-gui/"
install -d "$STAGE_DIR/usr/share/doc/openvpn3-gui/packaging"
install -m 644 "$PROJECT_DIR/packaging/openvpn3-gui.svg" "$STAGE_DIR/usr/share/doc/openvpn3-gui/packaging/"
if [ -d "$PROJECT_DIR/docs" ]; then
    cp -R "$PROJECT_DIR/docs" "$STAGE_DIR/usr/share/doc/openvpn3-gui/docs"
fi
install -m 644 "$PROJECT_DIR/packaging/copyright" "$STAGE_DIR/usr/share/doc/openvpn3-gui/"
gzip -n -9 -c "$PROJECT_DIR/packaging/changelog" > "$STAGE_DIR/usr/share/doc/openvpn3-gui/changelog.gz"
gzip -n -9 -c "$PROJECT_DIR/packaging/openvpn3-gui.1" > "$STAGE_DIR/usr/share/man/man1/openvpn3-gui.1.gz"
chmod 755 "$STAGE_DIR"
find "$STAGE_DIR" -type d -exec chmod 755 {} +
find "$STAGE_DIR" -type f -exec chmod 644 {} +
chmod 755 "$STAGE_DIR/usr/bin/openvpn3-gui"
(cd "$STAGE_DIR" && find usr -type f -print0 | LC_ALL=C sort -z | xargs -0 md5sum > DEBIAN/md5sums)
find "$STAGE_DIR" -exec touch -h -d "@$SOURCE_DATE_EPOCH" {} +
dpkg-deb --root-owner-group --build "$STAGE_DIR" "$PROJECT_DIR/dist/openvpn3-gui_${PACKAGE_VERSION}_all.deb"
install -m 755 "$PROJECT_DIR/scripts/install-deb.sh" "$PROJECT_DIR/dist/install-openvpn3-gui.sh"
(cd "$PROJECT_DIR/dist" && sha256sum "openvpn3-gui_${PACKAGE_VERSION}_all.deb" install-openvpn3-gui.sh > SHA256SUMS)
