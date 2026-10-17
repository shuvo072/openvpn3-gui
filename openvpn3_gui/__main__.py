import argparse
import sys
import os


def main():
    parser = argparse.ArgumentParser(
        description="Native GTK desktop interface for OpenVPN 3 Linux"
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Use isolated sample profiles and simulated operations",
    )
    from . import __version__

    parser.add_argument(
        "--version", action="version", version=f"OpenVPN 3 GUI {__version__}"
    )
    options = parser.parse_args()
    try:
        from .app import Application
    except (ImportError, ValueError) as error:
        print(
            f"Desktop dependency missing: {error}\nInstall: sudo apt install python3-gi gir1.2-gtk-3.0 gir1.2-vte-2.91",
            file=sys.stderr,
        )
        return 1
    from gi.repository import GLib
    from gi.repository import Gtk

    if not Gtk.init_check()[0]:
        print(
            "No graphical display is available. Start OpenVPN 3 GUI from your desktop session.",
            file=sys.stderr,
        )
        return 1
    if os.geteuid() == 0 and not options.demo:
        print(
            "Run OpenVPN 3 GUI as your normal desktop user, without sudo. Use --demo for isolated testing.",
            file=sys.stderr,
        )
        return 1
    GLib.set_prgname("openvpn3-gui")
    GLib.set_application_name("OpenVPN 3 GUI")
    return Application(demo=options.demo).run([sys.argv[0]])


if __name__ == "__main__":
    sys.exit(main())
