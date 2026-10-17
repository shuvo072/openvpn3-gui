#!/usr/bin/python3
"""Check actual GTK allocations with long profile names and resized windows."""

from pathlib import Path
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from openvpn3_gui.app import Application, MainWindow
from gi.repository import GLib, Gtk

app = Application(demo=True)
app.set_application_id("io.github.openvpn3gui.Layout")
names = [
    "/home/demo/Downloads/OpenVPN/Office_VPN_server_example_user.ovpn",
    "VeryLongUnbrokenProfileName" * 30,
    "অফিস সংযোগ / 東京オフィス / München " * 20,
]
cases = [(width, name) for name in names for width in (1240, 960, 1120, 1600)]
state = {"index": 0, "prepared": False, "ok": False, "started": time.monotonic()}


def fail(error_type, error, tb):
    traceback.print_exception(error_type, error, tb)
    state["ok"] = False
    app.quit()


# GTK callbacks otherwise print exceptions without failing the test process.
sys.excepthook = fail


def within(widget, viewport):
    position = widget.translate_coordinates(viewport, 0, 0)
    assert position is not None
    left = position[0]
    right = left + widget.get_allocated_width()
    width = viewport.get_allocated_width()
    assert left >= 0 and right <= width + 1, (type(widget).__name__, left, right, width)


def tick():
    if time.monotonic() - state["started"] > 45:
        raise AssertionError("Layout test timed out")
    window = next((w for w in app.get_windows() if isinstance(w, MainWindow)), None)
    if not window or not window.commands or window.refreshing:
        return True
    width, name = cases[state["index"]]
    if not state["prepared"]:
        window.appearance_combo.set_active_id("dark" if state["index"] % 2 else "light")
        window.backend._demo_profiles[0]["name"] = name
        window.backend._demo_profiles[0]["acl"] = {"owner": "long-owner-" * 30}
        window.resize(width, 680 if width == 960 else 820)
        for child in window.workspace.get_children()[1].get_children():
            if isinstance(child, Gtk.Expander):
                child.set_expanded(True)
        window.refresh()
        state["prepared"] = True
        return True

    if window.get_size().width != width:

        def report(widget, depth=0):
            minimum, natural = widget.get_preferred_width()
            if minimum > 600:
                print(
                    " " * depth,
                    type(widget).__name__,
                    minimum,
                    natural,
                    widget.get_allocated_width(),
                    flush=True,
                )
                if isinstance(widget, Gtk.Container):
                    for child in widget.get_children():
                        report(child, depth + 1)

        report(window)
    assert window.get_size().width == width, window.get_size()
    viewport = window.dashboard_scroll.get_child()
    adjustment = window.dashboard_scroll.get_hadjustment()
    assert adjustment.get_upper() <= adjustment.get_page_size() + 1, (
        state["index"],
        width,
        adjustment.get_upper(),
        adjustment.get_page_size(),
        window.workspace.get_orientation(),
        [
            (type(c).__name__, c.get_preferred_width())
            for c in viewport.get_child().get_children()
        ],
    )
    for widget in [
        window.metrics,
        *window.metrics.get_children(),
        window.import_button,
        window.profile_search,
        window.profile_tree,
        window.profile_name,
        window.profile_path,
        window.profile_meta,
        window.primary_button,
        window.pause_button,
        window.traffic_panel,
        window.traffic_panel.graph,
        window.logs_button,
        window.more_button,
    ]:
        within(widget, viewport)
    assert window.profile_name.get_text() == name
    assert window.profile_name.get_tooltip_text() == name
    assert (
        window.profile_name.get_layout().get_pixel_size().width
        <= window.profile_name.get_allocated_width()
    )
    if width == 960:
        assert window.workspace.get_orientation() == Gtk.Orientation.VERTICAL
    if width == 1600:
        assert window.workspace.get_orientation() == Gtk.Orientation.HORIZONTAL
    state["index"] += 1
    state["prepared"] = False
    if state["index"] == len(cases):
        state["ok"] = True
        print(
            "PASS: 12 long-name/window-size layouts, visible controls, wrapping, exact names, compact/wide transitions."
        )
        window.destroy()
        app.quit()
        return False
    return True


GLib.timeout_add(350, tick)
app.run([sys.argv[0]])
sys.exit(0 if state["ok"] else 1)
