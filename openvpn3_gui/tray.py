"""Ayatana status notifier with exact-identity actions and safe window recovery."""

from collections import Counter
from pathlib import Path
import unicodedata

import gi
from gi.repository import Gio, GLib, Gtk

from .backend import connection_status


def tray_status(sessions, unavailable=False, busy=False):
    """Return an icon state and an honest summary, including mixed sessions."""
    if unavailable:
        return "error", "VPN status unavailable"
    if busy:
        return "connecting", "VPN action in progress…"
    states = [connection_status([session]) for session in sessions]
    connected = states.count("Connected")
    if not states:
        return "disconnected", "Disconnected"
    summary = (
        states[0]
        if len(states) == 1
        else f"{connected} connected · {len(states)} sessions"
    )
    if any("failed" in s.lower() or "error" in s.lower() for s in states):
        return "error", summary
    if any(s not in ("Connected", "Disconnected", "Paused") for s in states):
        return "connecting", summary
    if connected:
        return "connected", summary
    if "Paused" in states:
        return "paused", summary
    return "disconnected", summary


def menu_name(item, duplicate=False):
    name = str(item.get("name") or "Unnamed VPN")
    if name.startswith("/"):
        name = Path(name).name
    name = "".join(c for c in name if not unicodedata.category(c).startswith("C"))
    if len(name) > 48:
        name = name[:45] + "…"
    return name + (" · " + item["path"].rsplit("/", 1)[-1][-10:] if duplicate else "")


class Tray:
    def __init__(self, window):
        self.window = window
        self.indicator = None
        self.api = None
        self.menu = None
        self.signature = None
        self.connected = False
        self.host = False
        self.available = False
        self.stopped = False
        self.proxy = None
        self.cancel = Gio.Cancellable()
        self.proxy_handlers = []
        self.reason = "Tray support is unavailable. Closing the window exits the app."
        try:
            gi.require_version("AyatanaAppIndicator3", "0.1")
            from gi.repository import AyatanaAppIndicator3
        except (ImportError, ValueError):
            self.reason = "Tray library unavailable. Install gir1.2-ayatanaappindicator3-0.1 to enable it."
            return
        self.api = AyatanaAppIndicator3
        self.indicator = self.api.Indicator.new(
            "openvpn3-gui-demo" if window.backend.demo else "openvpn3-gui",
            self.icon_path("disconnected"),
            self.api.IndicatorCategory.COMMUNICATIONS,
        )
        self.indicator.set_title(
            "OpenVPN 3 GUI" + (" (demo)" if window.backend.demo else "")
        )
        self.connection_handler = self.indicator.connect(
            "connection-changed", self.connection_changed
        )
        self.update()
        self.indicator.set_status(self.api.IndicatorStatus.ACTIVE)
        self.connected = self.indicator.get_property("connected")
        Gio.DBusProxy.new_for_bus(
            Gio.BusType.SESSION,
            Gio.DBusProxyFlags.DO_NOT_AUTO_START,
            None,
            "org.kde.StatusNotifierWatcher",
            "/StatusNotifierWatcher",
            "org.kde.StatusNotifierWatcher",
            self.cancel,
            self.proxy_ready,
        )

    @staticmethod
    def icon_path(state):
        return str(Path(__file__).parent / "data/tray" / f"openvpn3-{state}.svg")

    def proxy_ready(self, _, result):
        try:
            proxy = Gio.DBusProxy.new_for_bus_finish(result)
        except GLib.Error:
            return
        if self.stopped:
            return
        self.proxy = proxy
        self.proxy_handlers = [
            proxy.connect("notify::g-name-owner", self.host_changed),
            proxy.connect("g-properties-changed", self.host_changed),
            proxy.connect("g-signal", self.host_signal),
        ]
        self.host_changed()

    def host_changed(self, *_):
        value = self.proxy.get_cached_property("IsStatusNotifierHostRegistered")
        self.host = bool(self.proxy.get_name_owner() and value and value.unpack())
        self.availability_changed()

    def host_signal(self, proxy, sender, signal, parameters):
        if signal in ("StatusNotifierHostRegistered", "StatusNotifierHostUnregistered"):
            self.host = (
                bool(proxy.get_name_owner())
                and signal == "StatusNotifierHostRegistered"
            )
            self.availability_changed()

    def connection_changed(self, indicator, connected):
        self.connected = connected
        self.availability_changed()

    def availability_changed(self):
        if self.stopped:
            return
        self.available = bool(self.connected and self.host)
        self.reason = (
            "Tray icon available. Use its menu to reopen or quit the app."
            if self.available
            else "No tray host detected. Closing the window exits the app. On GNOME, enable an AppIndicator extension."
        )
        self.window.tray_availability_changed(self.available, self.reason)

    def add_item(self, menu, title, callback=None, enabled=True):
        item = Gtk.MenuItem(label=title, use_underline=False)
        item.set_sensitive(enabled and callback is not None)
        if callback:
            item.connect("activate", lambda *_: callback())
        menu.append(item)
        return item

    def update(self):
        if self.stopped or not self.indicator:
            return
        window = self.window
        state, summary = tray_status(
            window.sessions,
            window.refresh_error or bool(window.session_error),
            window.busy,
        )
        if window.backend.demo:
            summary = "Demo · " + summary
        self.indicator.set_icon_full(self.icon_path(state), summary)
        profiles = window.profiles
        sessions = window.sessions
        enabled = bool(window.commands) and not (
            window.busy or window.refresh_error or window.session_error
        )
        signature = (
            summary,
            enabled,
            tuple((p["path"], p["name"]) for p in profiles),
            tuple(
                (s["path"], s["name"], s.get("status"), s.get("config_path"))
                for s in sessions
            ),
        )
        if signature == self.signature:
            return
        self.signature = signature
        menu = Gtk.Menu()
        self.add_item(menu, summary)
        self.add_item(menu, "Open OpenVPN 3 GUI", window.present)
        menu.append(Gtk.SeparatorMenuItem())
        if sessions:
            names = Counter(menu_name(s) for s in sessions)
            for session in sessions:
                path = session["path"]
                status = connection_status([session])
                item = self.add_item(
                    menu,
                    f"{menu_name(session, names[menu_name(session)] > 1)} — {status}",
                    lambda: None,
                )
                submenu = Gtk.Menu()
                self.add_item(
                    submenu,
                    "Disconnect",
                    lambda path=path: self.action("disconnect", path),
                    enabled,
                )
                if status in ("Connected", "Paused"):
                    action = "resume" if status == "Paused" else "pause"
                    self.add_item(
                        submenu,
                        action.capitalize(),
                        lambda path=path, action=action: self.action(action, path),
                        enabled,
                    )
                item.set_submenu(submenu)
        else:
            self.add_item(
                menu,
                (
                    "No active sessions"
                    if not window.session_error
                    else "Sessions unavailable"
                ),
            )
        connect = self.add_item(
            menu, "Connect to VPN", lambda: None, enabled and bool(profiles)
        )
        submenu = Gtk.Menu()
        names = Counter(menu_name(p) for p in profiles)
        for profile in profiles:
            path = profile["path"]
            active = any(s.get("config_path") == path for s in sessions)
            self.add_item(
                submenu,
                menu_name(profile, names[menu_name(profile)] > 1)
                + (" (active)" if active else ""),
                lambda path=path: self.action("connect", path),
                enabled and not active,
            )
        connect.set_submenu(submenu)
        menu.append(Gtk.SeparatorMenuItem())
        self.add_item(menu, "Refresh", window.refresh, not window.busy)
        self.add_item(menu, "Quit app (keep VPN connected)", window.request_quit)
        menu.show_all()
        old = self.menu
        self.menu = menu
        self.indicator.set_menu(menu)
        if old:
            old.destroy()

    def action(self, action, path):
        """Revalidate stale menu callbacks; never use display names or selection."""
        window = self.window
        if self.stopped or window.busy or window.refresh_error or window.session_error:
            return
        if action == "connect":
            if not any(p["path"] == path for p in window.profiles):
                return
            if any(s.get("config_path") == path for s in window.sessions):
                return
            arguments = ["session-start", "--config-path", path]
        elif action in ("disconnect", "pause", "resume"):
            session = next((s for s in window.sessions if s["path"] == path), None)
            if not session:
                return
            if action == "resume" and connection_status([session]) != "Paused":
                return
            if action == "pause" and connection_status([session]) != "Connected":
                return
            arguments = ["session-manage", "--path", path, "--" + action]
        else:
            return
        if action in ("connect", "resume"):
            window.present()  # Interactive credentials must remain visible.
        window.run_command(arguments, routine=True)

    def close(self):
        self.stopped = True
        self.cancel.cancel()
        if self.proxy:
            for handler in self.proxy_handlers:
                self.proxy.disconnect(handler)
        if self.indicator:
            self.indicator.disconnect(self.connection_handler)
            self.indicator.set_status(self.api.IndicatorStatus.PASSIVE)
        if self.menu:
            self.menu.destroy()
        self.indicator = None
