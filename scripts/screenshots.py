#!/usr/bin/python3
"""Capture real GTK widgets using isolated demo data, never personal VPN data."""

from pathlib import Path
import sys
import tempfile
import time
import traceback

import cairo

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from openvpn3_gui.app import Application, MainWindow
from gi.repository import GLib, Gtk

OUTPUT = ROOT / "docs/screenshots"
OUTPUT.mkdir(parents=True, exist_ok=True)
app = Application(demo=True)
app.set_application_id("io.github.openvpn3gui.Screenshots")
state = {"step": 0, "started": time.monotonic(), "ok": False}
sample_directory = tempfile.TemporaryDirectory(prefix="openvpn3-screenshot-")
sample = Path(sample_directory.name) / "travel.ovpn"
sample.write_text("# Demo only\nclient\ndev tun\nremote vpn.example.invalid 1194\n")


def capture(widget, name):
    surface = cairo.ImageSurface(
        cairo.FORMAT_ARGB32, widget.get_allocated_width(), widget.get_allocated_height()
    )
    widget.draw(cairo.Context(surface))
    surface.write_to_png(str(OUTPUT / name))


def children(widget):
    yield widget
    if isinstance(widget, Gtk.Container):
        for child in widget.get_children():
            yield from children(child)


def prepare_import():
    dialog = next(
        w for w in Gtk.Window.list_toplevels() if w.get_title() == "Import VPN profile"
    )
    for widget in children(dialog):
        if isinstance(widget, Gtk.FileChooserButton):
            widget.set_filename(str(sample))
            widget.emit("file-set")
        elif (
            isinstance(widget, Gtk.Entry)
            and widget.get_placeholder_text() == "Friendly name, e.g. Office VPN"
        ):
            widget.set_text("Travel VPN")

    def save():
        capture(dialog, "import-profile.png")
        dialog.response(Gtk.ResponseType.CANCEL)
        return False

    GLib.timeout_add(400, save)
    return False


def tick():
    try:
        if time.monotonic() - state["started"] > 30:
            raise RuntimeError("Screenshot capture timed out")
        window = next((w for w in app.get_windows() if isinstance(w, MainWindow)), None)
        if not window or not window.commands or window.refreshing:
            return True
        step = state["step"]
        if step == 0:
            # Illustrative names; changes are only in the in-memory demo backend.
            window.backend._demo_profiles[1]["name"] = "Development"
            window.resize(1240, 820)
            window.refresh()
            state["step"] = 1
        elif step == 1:
            capture(window, "dashboard.png")
            window.open_command(
                "config-manage",
                {
                    "path": "/net/openvpn/v3/configuration/demo_persistent",
                    "dns-scope": "tunnel",
                    "dns-fallback-google": "false",
                },
            )
            form = window.form_holder.get_children()[0]
            form.search.set_text("dns")
            form.filter_rows()
            state["step"] = 2
        elif step == 2:
            capture(window, "advanced-options.png")
            state["step"] = 3
            window.navigation.select_row(window.navigation.get_row_at_index(0))
            GLib.timeout_add(250, prepare_import)
            window.import_profile()
        elif step == 3:
            window.primary_action()
            state["step"] = 4
        elif step == 4 and not window.busy and not window.refreshing:
            window.resize(1240, 1020)
            window.activity.set_expanded(True)
            state["step"] = 5
        elif step == 5:
            capture(window, "disconnect-details.png")
            window.activity.set_expanded(False)
            window.backend._demo_profiles[0][
                "name"
            ] = "/home/demo/Downloads/OpenVPN/Office_VPN_server_example_user.ovpn"
            window.resize(1240, 820)
            window.refresh()
            state["step"] = 6
        elif step == 6:
            window.dashboard_scroll.get_vadjustment().set_value(0)
            capture(window, "long-name-1240.png")
            window.resize(960, 1120)
            state["step"] = 7
        elif step == 7:
            capture(window, "long-name-960.png")
            state["ok"] = True
            window.destroy()
            app.quit()
            return False
        return True
    except Exception:
        traceback.print_exc()
        for window in Gtk.Window.list_toplevels():
            window.destroy()
        app.quit()
        return False


GLib.timeout_add(500, tick)
app.run([sys.argv[0]])
sample_directory.cleanup()
if state["ok"]:
    print(
        "Captured dashboard, import, advanced options, disconnect, and long-name wide/compact layouts using demo data."
    )
sys.exit(0 if state["ok"] else 1)
