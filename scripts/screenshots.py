#!/usr/bin/python3
"""Capture real GTK widgets using isolated demo data, never personal VPN data."""

from pathlib import Path
import sys
import tempfile
import time
import traceback
import math

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from openvpn3_gui.app import Application, MainWindow
from openvpn3_gui.traffic import TrafficHistory
from gi.repository import Gdk, GLib, Gtk

# Keep the pointer away from the demo controls in Xvfb so tooltips cannot
# obscure the mapped-window captures. No production desktop setting is changed.
display = Gdk.Display.get_default()
if display and "X11" in type(display).__name__:
    display.get_default_seat().get_pointer().warp(Gdk.Screen.get_default(), 0, 0)

OUTPUT = ROOT / "docs/screenshots"
OUTPUT.mkdir(parents=True, exist_ok=True)
app = Application(demo=True)
app.set_application_id("io.github.openvpn3gui.Screenshots")
state = {"step": 0, "started": time.monotonic(), "ok": False}
sample_directory = tempfile.TemporaryDirectory(prefix="openvpn3-screenshot-")
sample = Path(sample_directory.name) / "travel.ovpn"
sample.write_text("# Demo only\nclient\ndev tun\nremote vpn.example.invalid 1194\n")


def capture(widget, name):
    # Capture the mapped window so native TreeView headers and controls appear.
    pixbuf = Gdk.pixbuf_get_from_window(
        widget.get_window(),
        0,
        0,
        widget.get_allocated_width(),
        widget.get_allocated_height(),
    )
    if pixbuf is None:
        raise RuntimeError("Could not capture the mapped demo window")
    pixbuf.savev(str(OUTPUT / name), "png", [], [])


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
            window.resize(1240, 960)
            window.appearance_combo.set_active_id("dark")
            # Seed an explicitly demo-only minute so exported charts are useful.
            history = TrafficHistory()
            now = time.monotonic()
            received, sent = 12000000, 2000000
            for index in range(31):
                received += int(280000 + 190000 * math.sin(index / 3))
                sent += int(60000 + 35000 * math.cos(index / 4))
                history.add(now - 60 + index * 2, (received, sent))
            session = window.selected_session
            window.backend._demo_traffic[session["path"]] = (now, received, sent)
            window.traffic_records[session["path"]] = (
                window.selected_key,
                history,
                None,
            )
            window.render_traffic()
            window.refresh()
            state["step"] = 1
        elif step == 1:
            capture(window, "dashboard.png")
            window.appearance_combo.set_active_id("light")
            state["step"] = 10
        elif step == 10:
            capture(window, "dashboard-light.png")
            window.sidebar_toggle.set_active(False)
            window.resize(960, 960)
            state["step"] = 11
        elif step == 11:
            capture(window, "sidebar-collapsed.png")
            window.sidebar_toggle.set_active(True)
            window.resize(1240, 960)
            window.appearance_combo.set_active_id("dark")
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
            window.resize(1240, 1180)
            window.activity.set_expanded(True)
            state["step"] = 5
        elif step == 5:
            capture(window, "disconnect-details.png")
            window.activity.set_expanded(False)
            window.backend._demo_profiles[0][
                "name"
            ] = "/home/demo/Downloads/OpenVPN/Office_VPN_server_example_user.ovpn"
            window.notice.set_reveal_child(False)
            window.resize(1240, 1020)
            window.refresh()
            state["step"] = 6
        elif step == 6:
            window.dashboard_scroll.get_vadjustment().set_value(0)
            capture(window, "long-name-1240.png")
            window.resize(960, 1280)
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
        "Captured dark/light dashboards, collapsed sidebar, import, advanced options, disconnect, and long-name layouts using demo data."
    )
sys.exit(0 if state["ok"] else 1)
