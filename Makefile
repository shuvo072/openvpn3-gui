.PHONY: tui tui-demo run demo test check integration screenshots deb install
run:
	/usr/bin/python3 -m openvpn3_gui
demo:
	/usr/bin/python3 -m openvpn3_gui --demo
test:
	/usr/bin/python3 -m unittest discover -s tests -v
check:
	./scripts/check.sh
integration:
	/usr/bin/python3 scripts/integration-profile.py
screenshots:
	/usr/bin/python3 scripts/screenshots.py
deb:
	./scripts/build-deb.sh
install: deb
	./scripts/install-deb.sh

tui:
	./openvpn3-tui
tui-demo:
	./openvpn3-tui --demo
