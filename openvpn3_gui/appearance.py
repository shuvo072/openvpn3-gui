"""Application-local themes following the desktop portal, with GTK fallback."""

from gi.repository import Gdk, Gio, GLib, Gtk
from .preferences import MODES, is_dark, read_mode, write_mode
from .theme import css_for


class Appearance:
    def __init__(self, persist=True):
        self.persist = persist
        self.mode = read_mode() if persist else "system"
        self.portal = None
        self.portal_signal_seen = False
        self.desktop = None
        self.settings = Gtk.Settings.get_default()
        self.fallback = (
            bool(self.settings.get_property("gtk-application-prefer-dark-theme"))
            or "dark" in self.settings.get_property("gtk-theme-name").lower()
        )
        self.applying = False
        self.settings.connect("notify::gtk-theme-name", self.theme_changed)
        self.provider = Gtk.CssProvider()
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(),
            self.provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )
        source = Gio.SettingsSchemaSource.get_default()
        schema = source.lookup("org.gnome.desktop.interface", True) if source else None
        if schema and schema.has_key("color-scheme"):
            self.desktop = Gio.Settings.new_full(schema, None, None)
            self.desktop.connect("changed::color-scheme", lambda *_: self.apply())
            if schema.has_key("gtk-theme"):
                self.desktop.connect("changed::gtk-theme", self.desktop_theme_changed)
        self.connection = None
        self.subscription = None
        self.cancel = Gio.Cancellable()
        self.stopped = False
        self.apply()
        Gio.bus_get(Gio.BusType.SESSION, self.cancel, self.bus_ready)

    def desktop_theme_changed(self, *_):
        self.fallback = "dark" in self.desktop.get_string("gtk-theme").lower()
        self.apply()

    def theme_changed(self, *_):
        if self.applying:
            return
        self.fallback = "dark" in self.settings.get_property("gtk-theme-name").lower()
        self.apply()

    def bus_ready(self, _, result):
        try:
            connection = Gio.bus_get_finish(result)
        except GLib.Error:
            return
        if self.stopped:
            return
        self.connection = connection
        self.subscription = connection.signal_subscribe(
            "org.freedesktop.portal.Desktop",
            "org.freedesktop.portal.Settings",
            "SettingChanged",
            "/org/freedesktop/portal/desktop",
            None,
            Gio.DBusSignalFlags.NONE,
            self.setting_changed,
        )
        # Read is supported by both the v1 and v2 Settings portal.
        connection.call(
            "org.freedesktop.portal.Desktop",
            "/org/freedesktop/portal/desktop",
            "org.freedesktop.portal.Settings",
            "Read",
            GLib.Variant("(ss)", ("org.freedesktop.appearance", "color-scheme")),
            None,
            Gio.DBusCallFlags.NONE,
            2000,
            self.cancel,
            self.read_ready,
        )

    def read_ready(self, connection, result):
        try:
            value = connection.call_finish(result).unpack()[0]
        except GLib.Error:
            return
        if not self.stopped and not self.portal_signal_seen:
            self.set_system_scheme(value)

    def setting_changed(self, connection, sender, path, interface, signal, parameters):
        namespace, key, value = parameters.unpack()
        if namespace == "org.freedesktop.appearance" and key == "color-scheme":
            self.portal_signal_seen = True
            self.set_system_scheme(value)

    def set_system_scheme(self, value):
        while isinstance(value, GLib.Variant):
            value = value.unpack()
        self.portal = value if type(value) is int and value in (0, 1, 2) else None
        self.apply()

    def set_mode(self, mode):
        if mode not in MODES:
            raise ValueError("Unknown appearance mode")
        self.mode = mode
        self.apply()
        if self.persist:
            write_mode(mode)

    def apply(self):
        desktop = self.desktop.get_string("color-scheme") if self.desktop else "default"
        self.dark = is_dark(self.mode, self.portal, desktop, self.fallback)
        # Keep native controls consistent even when the user's base theme has
        # a hard-coded -dark suffix. These settings affect this process only.
        self.applying = True
        try:
            self.settings.set_property("gtk-theme-name", "Adwaita")
            self.settings.set_property("gtk-application-prefer-dark-theme", self.dark)
            self.provider.load_from_data(css_for(self.dark))
        finally:
            self.applying = False

    def close(self):
        self.stopped = True
        self.cancel.cancel()
        if self.connection and self.subscription:
            self.connection.signal_unsubscribe(self.subscription)
        Gtk.StyleContext.remove_provider_for_screen(
            Gdk.Screen.get_default(), self.provider
        )
