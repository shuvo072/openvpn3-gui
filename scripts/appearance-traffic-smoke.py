#!/usr/bin/python3
"""Exercise theme/sidebar changes and asynchronous live traffic without a VPN."""

from pathlib import Path
import sys
import time
import traceback

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from openvpn3_gui.app import Application, MainWindow
from gi.repository import Gio, GLib, Gtk

# Own a fake Settings portal on this isolated test session bus. Version 1's
# Read reply wraps its value twice; real desktops can use either variant form.
bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
bus.call_sync(
    "org.freedesktop.DBus",
    "/org/freedesktop/DBus",
    "org.freedesktop.DBus",
    "RequestName",
    GLib.Variant("(su)", ("org.freedesktop.portal.Desktop", 0)),
    None,
    Gio.DBusCallFlags.NONE,
    1000,
    None,
)
info = Gio.DBusNodeInfo.new_for_xml(
    """<node><interface name="org.freedesktop.portal.Settings">
<method name="Read"><arg type="s" direction="in"/><arg type="s" direction="in"/><arg type="v" direction="out"/></method>
<signal name="SettingChanged"><arg type="s"/><arg type="s"/><arg type="v"/></signal>
</interface></node>"""
)


def read_setting(connection, sender, path, interface, method, parameters, invocation):
    invocation.return_value(
        GLib.Variant("(v)", (GLib.Variant("v", GLib.Variant("u", 1)),))
    )


registration = bus.register_object(
    "/org/freedesktop/portal/desktop", info.interfaces[0], read_setting, None, None
)


Gtk.Settings.get_default().set_property("gtk-theme-name", "Adwaita-dark")
app = Application(demo=True)
app.set_application_id("io.github.openvpn3gui.AppearanceTrafficTest")
state = {"step": 0, "started": time.monotonic(), "ok": False}
pending = []


def tick():
    try:
        assert time.monotonic() - state["started"] < 25, "Test timed out"
        window = next((w for w in app.get_windows() if isinstance(w, MainWindow)), None)
        if not window or not window.commands or window.refreshing:
            return True
        step = state["step"]
        if step == 0:
            assert app.appearance.mode == "system"
            if app.appearance.portal is None:
                return True
            assert app.appearance.portal == 1
            assert app.appearance.dark
            window.appearance_combo.set_active_id("light")
            assert not app.appearance.dark
            assert (
                Gtk.Settings.get_default().get_property("gtk-theme-name") == "Adwaita"
            )
            assert not Gtk.Settings.get_default().get_property(
                "gtk-application-prefer-dark-theme"
            )
            app.appearance.set_system_scheme(1)
            assert not app.appearance.dark
            window.appearance_combo.set_active_id("dark")
            assert app.appearance.dark
            window.appearance_combo.set_active_id("system")
            bus.emit_signal(
                None,
                "/org/freedesktop/portal/desktop",
                "org.freedesktop.portal.Settings",
                "SettingChanged",
                GLib.Variant(
                    "(ssv)",
                    (
                        "org.freedesktop.appearance",
                        "color-scheme",
                        GLib.Variant("u", 2),
                    ),
                ),
            )
            window.sidebar_toggle.set_active(False)
            state["width"] = window.dashboard_scroll.get_allocated_width()
            state["step"] = 1
        elif step == 1:
            # Wait for the portal signal and completed GTK layout/animation.
            # A fixed 300 ms delay can expire before the first frame on busy CI.
            if (
                app.appearance.portal != 2
                or window.sidebar_revealer.get_child_revealed()
                or window.dashboard_scroll.get_allocated_width() <= state["width"]
            ):
                return True
            assert app.appearance.portal == 2
            assert not app.appearance.dark
            assert not window.sidebar_revealer.get_child_revealed()
            assert window.dashboard_scroll.get_allocated_width() > state["width"]
            window.sidebar_toggle.set_active(True)
            window.poll_traffic()
            state["step"] = 2
        elif step == 2:
            if window.traffic_inflight:
                return True
            if not window.traffic_records:
                return True
            path = window.selected_session["path"]
            history = window.traffic_records[path][1]
            assert history.totals and history.totals[0] > 0
            if history.rates is None:
                return True
            assert "/s" in window.traffic_panel.speeds[0].get_text()
            state["path"] = path
            state["background"] = window.background
            # Hold a read to reproduce a selection change while it is in flight.
            window.background = lambda work, done, failed=None: pending.append(
                (work, done, failed)
            )
            window.poll_traffic()
            window.poll_traffic()
            assert len(pending) == 1, "Traffic polling must not overlap"
            window.profile_tree.get_selection().select_path(
                Gtk.TreePath.new_from_indices([1])
            )
            pending.pop()[1]((99999999, 2222222))
            assert (
                window.traffic_panel.totals[0].get_text() == "— total"
            ), "Stale result reached a different profile"
            window.profile_tree.get_selection().select_path(
                Gtk.TreePath.new_from_indices([0])
            )
            window.poll_traffic()
            pending.pop()[2]("Stats unavailable")
            assert "unavailable" in window.traffic_panel.note.get_text()
            assert window.traffic_panel.speeds[0].get_text() == "—"
            window.poll_traffic()
            pending.pop()[1]((100000000, 2222223))
            assert "Demo traffic" in window.traffic_panel.note.get_text()
            assert (
                window.traffic_panel.speeds[0].get_text() == "—"
            ), "Recovery needs a new rate baseline"
            window.poll_traffic()
            # Disconnect before the last read arrives; the result must be ignored.
            window.backend._demo_sessions = []
            window.sessions = []
            window.render_profiles()
            pending.pop()[1]((200000000, 99999999))
            assert "Last recorded" in window.traffic_panel.note.get_text()
            assert window.traffic_records[path][1].totals == (100000000, 2222223)
            window.background = state["background"]
            state["ok"] = True
            window.destroy()
            app.quit()
            return False
        return True
    except Exception:
        traceback.print_exc()
        for window in app.get_windows():
            window.destroy()
        app.quit()
        return False


GLib.timeout_add(300, tick)
app.run([sys.argv[0]])
bus.unregister_object(registration)
if state["ok"]:
    print(
        "PASS: system/light/dark appearance, hamburger resizing, live counters, bounded polling, stale selection/disconnect results, error recovery."
    )
sys.exit(0 if state["ok"] else 1)
