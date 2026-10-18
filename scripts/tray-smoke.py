#!/usr/bin/python3
"""Exercise a real Ayatana indicator against an isolated status notifier watcher."""

from pathlib import Path
import sys
import time
import traceback
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from openvpn3_gui.app import Application, MainWindow
from openvpn3_gui.tray import Tray, tray_status, menu_name
from gi.repository import Gdk, Gio, GLib, Gtk
from tray_fixture import Watcher

watcher = Watcher()
app = Application(demo=True)
app.set_application_id("io.github.openvpn3gui.TrayTest")
state = {"step": 0, "started": time.monotonic(), "ok": False}


def all_items(menu):
    for item in menu.get_children():
        if isinstance(item, Gtk.MenuItem):
            yield item
            if item.get_submenu():
                yield from all_items(item.get_submenu())


def snapshot(window):
    menu = window.tray.menu
    menu.popup_at_widget(window, Gdk.Gravity.NORTH_EAST, Gdk.Gravity.NORTH_EAST, None)

    def save():
        try:
            pixbuf = Gdk.pixbuf_get_from_window(
                menu.get_window(),
                0,
                0,
                menu.get_allocated_width(),
                menu.get_allocated_height(),
            )
            assert pixbuf
            pixbuf.savev(str(ROOT / "docs/screenshots/tray-menu.png"), "png", [], [])
        finally:
            menu.popdown()
        return False

    GLib.timeout_add(150, save)


def tick():
    try:
        assert (
            time.monotonic() - state["started"] < 30
        ), f"Timed out at step {state['step']}"
        window = next((w for w in app.get_windows() if isinstance(w, MainWindow)), None)
        if not window or not window.commands or window.refreshing:
            return True
        tray = window.tray
        step = state["step"]
        if step == 0:
            if not tray.available:
                return True
            assert watcher.items, "Indicator was not registered"
            assert tray.indicator.get_status() == tray.api.IndicatorStatus.ACTIVE
            assert Path(tray.indicator.get_icon()).is_file()
            assert tray_status([], True)[0] == "error"
            assert tray_status([], busy=True)[0] == "connecting"
            for status, icon in [
                ("Connected", "connected"),
                ("Connecting", "connecting"),
                ("Paused", "paused"),
                ("Disconnected", "disconnected"),
                ("Connection failed", "error"),
            ]:
                assert tray_status([{"status": status}])[0] == icon
            assert (
                tray_status(
                    [{"status": "Connected"}, {"status": "Authentication needed"}]
                )[0]
                == "connecting"
            )
            assert "\n" not in menu_name({"name": "unsafe\nname", "path": "/id"})
            titles = [i.get_label() for i in all_items(tray.menu)]
            assert "Connect to VPN" in titles and "Disconnect" in titles
            # Validate the actual exported D-Bus menu, not just GTK widgets.
            sender, path = watcher.items[-1]
            watcher.bus.call(
                sender,
                path,
                "org.freedesktop.DBus.Properties",
                "GetAll",
                GLib.Variant("(s)", ("org.kde.StatusNotifierItem",)),
                None,
                Gio.DBusCallFlags.NONE,
                2000,
                None,
                properties_ready,
            )
            if "--screenshot" in sys.argv:
                snapshot(window)
            state["step"] = 1
        elif step == 1:
            if "properties" not in state:
                return True
            properties = state["properties"]
            assert properties["Status"] == "Active"
            assert properties["Menu"].startswith("/")
            assert "openvpn3-" in properties["IconName"]
            assert window.on_close() is True and not window.get_visible()
            app.activate()
            assert window.get_visible()
            assert sum(isinstance(w, MainWindow) for w in app.get_windows()) == 1
            window.on_close()
            watcher.set_host(False)
            state["step"] = 2
        elif step == 2:
            if tray.available or not window.get_visible():
                return True
            assert window.on_close() is False, "Do not hide without a tray host"
            watcher.set_host(True)
            state["step"] = 3
        elif step == 3:
            if not tray.available:
                return True
            window.on_close()
            watcher.release()
            state["step"] = 4
        elif step == 4:
            if tray.available or not window.get_visible():
                return True
            watcher.own()
            state["step"] = 5
        elif step == 5:
            if not tray.available:
                return True
            # Exact IDs, duplicate names, stale menu clicks, and busy/error guards.
            original = window.run_command
            calls = []
            window.run_command = lambda args, routine=False: calls.append(
                (args, routine)
            )
            session = window.sessions[0]
            profile = next(
                p for p in window.profiles if p["path"] != session.get("config_path")
            )
            next(
                i for i in all_items(tray.menu) if i.get_label() == "Disconnect"
            ).activate()
            assert calls.pop() == (
                ["session-manage", "--path", session["path"], "--disconnect"],
                True,
            )
            window.hide()
            tray.action("connect", profile["path"])
            assert calls.pop() == (
                ["session-start", "--config-path", profile["path"]],
                True,
            )
            assert window.get_visible(), "Credentials must be visible"
            tray.action("disconnect", "/missing")
            tray.action("connect", session.get("config_path"))
            window.busy = True
            tray.action("disconnect", session["path"])
            window.update_actions()
            assert not next(
                i for i in all_items(tray.menu) if i.get_label() == "Disconnect"
            ).get_sensitive()
            window.request_quit()
            assert not window.closed
            window.busy = False
            window.session_error = "service unavailable"
            tray.action("disconnect", session["path"])
            window.session_error = None
            assert not calls
            window.run_command = original
            window.keep_running_check.set_active(False)
            assert window.on_close() is False
            window.keep_running_check.set_active(True)
            # Missing GI typelib remains a usable window.
            with patch("gi.require_version", side_effect=ValueError("missing")):
                missing = Tray(window)
            assert missing.indicator is None and not missing.available
            missing.close()
            window.hide()
            window.show_error("Test action failure")
            assert window.get_visible()
            state["indicator"] = tray.indicator
            state["sessions"] = list(window.backend._demo_sessions)
            # A real quiet disconnect via tray, while hidden.
            window.hide()
            tray.action("disconnect", session["path"])
            state["step"] = 6
        elif step == 6:
            if window.busy or window.refreshing:
                return True
            assert not window.sessions
            assert (
                not window.get_visible()
            ), "Successful quiet disconnect should not raise the window"
            # Quitting must leave established VPN sessions alone.
            window.backend._demo_sessions = state["sessions"]
            next(
                i
                for i in all_items(tray.menu)
                if i.get_label() == "Quit app (keep VPN connected)"
            ).activate()
            assert window.backend._demo_sessions == state["sessions"]
            assert window.closed and tray.stopped
            assert state["indicator"].get_status() == tray.api.IndicatorStatus.PASSIVE
            state["ok"] = True
            app.quit()
            return False
        return True
    except Exception:
        traceback.print_exc()
        for window in app.get_windows():
            window.destroy()
        app.quit()
        return False


def properties_ready(bus, result):
    try:
        state["properties"] = bus.call_finish(result).unpack()[0]
    except Exception as error:
        state["properties"] = {"error": str(error)}


GLib.timeout_add(250, tick)
app.run([sys.argv[0]])
watcher.close()
if state["ok"]:
    print(
        "PASS: real indicator registration/export, exact-ID tray actions, busy/error guards, hide/reopen/quit, absent/lost/restarted host, missing library, and quiet disconnect."
    )
sys.exit(0 if state["ok"] else 1)
