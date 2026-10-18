"""Minimal status notifier watcher for isolated D-Bus tests; not a desktop panel."""

from gi.repository import Gio, GLib


class Watcher:
    name = "org.kde.StatusNotifierWatcher"
    path = "/StatusNotifierWatcher"

    def __init__(self):
        self.bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        self.host = True
        self.items = []
        self.own()
        info = Gio.DBusNodeInfo.new_for_xml(
            """<node><interface name="org.kde.StatusNotifierWatcher">
          <method name="RegisterStatusNotifierItem"><arg type="s" direction="in"/></method>
          <method name="RegisterStatusNotifierHost"><arg type="s" direction="in"/></method>
          <property name="IsStatusNotifierHostRegistered" type="b" access="read"/>
          <property name="RegisteredStatusNotifierItems" type="as" access="read"/>
          <property name="ProtocolVersion" type="i" access="read"/>
          <signal name="StatusNotifierHostRegistered"/>
          <signal name="StatusNotifierHostUnregistered"/>
          <signal name="StatusNotifierItemRegistered"><arg type="s"/></signal>
        </interface></node>"""
        )
        self.registration = self.bus.register_object(
            self.path, info.interfaces[0], self.call, self.get, None
        )

    def own(self):
        result = self.bus.call_sync(
            "org.freedesktop.DBus",
            "/org/freedesktop/DBus",
            "org.freedesktop.DBus",
            "RequestName",
            GLib.Variant("(su)", (self.name, 4)),
            None,
            Gio.DBusCallFlags.NONE,
            1000,
            None,
        )
        assert (
            result.unpack()[0] == 1
        ), "Use an isolated dbus-run-session; a watcher already exists"

    def release(self):
        self.bus.call_sync(
            "org.freedesktop.DBus",
            "/org/freedesktop/DBus",
            "org.freedesktop.DBus",
            "ReleaseName",
            GLib.Variant("(s)", (self.name,)),
            None,
            Gio.DBusCallFlags.NONE,
            1000,
            None,
        )

    def call(self, connection, sender, path, interface, method, parameters, invocation):
        if method == "RegisterStatusNotifierItem":
            value = parameters.unpack()[0]
            self.items.append((sender, value))
        invocation.return_value(None)

    def get(self, connection, sender, path, interface, prop):
        if prop == "IsStatusNotifierHostRegistered":
            return GLib.Variant("b", self.host)
        if prop == "RegisteredStatusNotifierItems":
            return GLib.Variant("as", [sender + path for sender, path in self.items])
        return GLib.Variant("i", 0)

    def set_host(self, active):
        self.host = active
        self.bus.emit_signal(
            None,
            self.path,
            "org.freedesktop.DBus.Properties",
            "PropertiesChanged",
            GLib.Variant(
                "(sa{sv}as)",
                (
                    self.name,
                    {"IsStatusNotifierHostRegistered": GLib.Variant("b", active)},
                    [],
                ),
            ),
        )
        self.bus.emit_signal(
            None,
            self.path,
            self.name,
            (
                "StatusNotifierHostRegistered"
                if active
                else "StatusNotifierHostUnregistered"
            ),
            None,
        )

    def close(self):
        self.release()
        self.bus.unregister_object(self.registration)
