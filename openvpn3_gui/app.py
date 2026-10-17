"""Native GTK desktop interface for the installed OpenVPN 3 CLI."""

from concurrent.futures import ThreadPoolExecutor
from collections import Counter
from pathlib import Path
import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gdk, GdkPixbuf, Gio, GLib, Gtk, Pango

from . import __version__
from .backend import (
    Backend,
    CLIError,
    save_private_file,
    group_connections,
    connection_status,
)
from .widgets import CommandForm, CommandWindow, button, confirm, label, scrolled


from .theme import CSS


def application_icon_path():
    source = Path(__file__).resolve().parent.parent / "packaging/openvpn3-gui.svg"
    return source if source.is_file() else Path(__file__).parent / "data/app-icon.svg"


def application_icon(size):
    return Gtk.Image.new_from_pixbuf(
        GdkPixbuf.Pixbuf.new_from_file_at_scale(
            str(application_icon_path()), size, size, True
        )
    )


class MainWindow(Gtk.ApplicationWindow):
    def __init__(self, app, backend):
        super().__init__(application=app, title="OpenVPN 3 GUI")
        self.backend = backend
        self.commands = {}
        self.discovering = False
        self.refresh_error = False
        self.profiles = []
        self.sessions = []
        self.executor = ThreadPoolExecutor(
            max_workers=3, thread_name_prefix="openvpn3-read"
        )
        self.refreshing = False
        self.refresh_again = False
        self.busy = False
        self.session_error = None
        self.groups = {}
        self.selected_key = None
        self.closed = False
        self.layout_pending = False
        self.selected_profile = None
        self.selected_session = None
        self.set_default_size(1240, 820)
        self.set_size_request(960, 680)
        self.connect("destroy", self.on_destroy)
        self.connect("delete-event", self.on_close)
        self.connect("key-press-event", self.on_shortcut)
        header = Gtk.HeaderBar(
            title="OpenVPN 3 GUI",
            subtitle="Independent Linux client",
            show_close_button=True,
        )
        self.refresh_button = button("Refresh", lambda *_: self.refresh())
        self.refresh_button.set_image(
            Gtk.Image.new_from_icon_name("view-refresh-symbolic", Gtk.IconSize.BUTTON)
        )
        self.refresh_button.set_always_show_image(True)
        self.refresh_button.set_tooltip_text("Refresh profiles and sessions (Ctrl+R)")
        header.pack_end(self.refresh_button)
        if backend.demo:
            header.set_subtitle("Demo mode · no VPN changes")
        self.set_titlebar(header)
        layout = Gtk.Box()
        self.add(layout)
        sidebar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        sidebar.set_size_request(190, -1)
        sidebar.get_style_context().add_class("sidebar")
        brand = Gtk.Box(spacing=10)
        brand_icon = application_icon(40)
        brand.pack_start(brand_icon, False, False, 0)
        brand_name = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        brand_name.pack_start(label("OpenVPN 3", "brand"), False, False, 0)
        brand_name.pack_start(label("COMMUNITY GUI", "brand-caption"), False, False, 0)
        brand.pack_start(brand_name, False, False, 0)
        sidebar.pack_start(brand, False, False, 0)
        sidebar.pack_start(label("YOUR WORKSPACE", "sidebar-note"), False, False, 6)
        self.navigation = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
        for text, page in (
            ("My VPNs", "profiles"),
            ("Advanced tools", "commands"),
            ("About & help", "about"),
        ):
            row = Gtk.ListBoxRow()
            row.page = page
            item = Gtk.Box(spacing=10)
            icon = {
                "profiles": "network-vpn-symbolic",
                "commands": "utilities-terminal-symbolic",
                "about": "help-browser-symbolic",
            }[page]
            item.pack_start(
                Gtk.Image.new_from_icon_name(icon, Gtk.IconSize.MENU), False, False, 0
            )
            item.pack_start(label(text), False, False, 0)
            row.add(item)
            self.navigation.add(row)
        self.navigation.connect("row-selected", self.navigate)
        sidebar.pack_start(self.navigation, True, True, 0)
        sidebar.pack_end(
            label(
                f"LOCAL DESKTOP CLIENT\nv{__version__} · MIT License", "sidebar-note"
            ),
            False,
            False,
            8,
        )
        layout.pack_start(sidebar, False, False, 0)
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        body.set_border_width(24)
        layout.pack_start(body, True, True, 0)
        self.banner = label("Reading your OpenVPN installation…", "success-banner")
        self.banner.set_selectable(True)
        self.notice = Gtk.Revealer(transition_type=Gtk.RevealerTransitionType.SLIDE_UP)
        notice_box = Gtk.Box(spacing=8)
        notice_box.get_style_context().add_class("notice")
        notice_box.pack_start(self.banner, True, True, 0)
        dismiss = button("Dismiss", lambda *_: self.notice.set_reveal_child(False))
        dismiss.get_accessible().set_name("Dismiss notification")
        notice_box.pack_end(dismiss, False, False, 0)
        self.notice.add(notice_box)
        body.pack_end(self.notice, False, False, 0)
        self.stack = Gtk.Stack(
            transition_type=Gtk.StackTransitionType.CROSSFADE, transition_duration=120
        )
        self.stack.set_hhomogeneous(False)
        self.stack.set_vhomogeneous(False)
        body.pack_start(self.stack, True, True, 0)
        self.dashboard_scroll = scrolled(self.make_profiles())
        # Keep the viewport shrinkable while the cards switch orientation.
        # NEVER would propagate the old two-column minimum to the window.
        self.dashboard_scroll.set_policy(
            Gtk.PolicyType.EXTERNAL, Gtk.PolicyType.AUTOMATIC
        )
        self.dashboard_scroll.connect("size-allocate", self.on_resize)
        self.stack.add_named(self.dashboard_scroll, "profiles")
        self.stack.add_named(self.make_commands(), "commands")
        self.stack.add_named(self.make_about(), "about")
        self.navigation.select_row(self.navigation.get_row_at_index(0))
        self.show_all()
        self.load_commands()
        self.refresh()
        self.poll_id = GLib.timeout_add_seconds(5, self.poll)

    def background(self, work, done, failed=None):
        future = self.executor.submit(work)

        def delivered(future):
            try:
                result = future.result()
            except Exception as error:
                GLib.idle_add(dispatch, failed or self.show_error, str(error))
            else:
                GLib.idle_add(dispatch, done, result)

        def dispatch(callback, value):
            if not self.closed:
                callback(value)
            return False

        future.add_done_callback(delivered)

    def show_error(self, error):
        self.banner.get_style_context().remove_class("success-banner")
        self.banner.get_style_context().add_class("error-banner")
        self.banner.set_text(str(error))
        self.notice.set_reveal_child(True)

    def show_status(self, text):
        self.banner.get_style_context().remove_class("error-banner")
        self.banner.get_style_context().add_class("success-banner")
        self.banner.set_text(text)
        self.notice.set_reveal_child(True)

    def on_shortcut(self, _, event):
        modifiers = event.state & Gtk.accelerator_get_default_mod_mask()
        if modifiers == Gdk.ModifierType.CONTROL_MASK:
            if event.keyval in (Gdk.KEY_r, Gdk.KEY_R):
                self.refresh()
                return True
            if event.keyval in (Gdk.KEY_f, Gdk.KEY_F):
                self.navigation.select_row(self.navigation.get_row_at_index(0))
                self.profile_search.grab_focus()
                return True
            if (
                event.keyval in (Gdk.KEY_i, Gdk.KEY_I)
                and self.import_button.get_sensitive()
            ):
                self.import_profile()
                return True
            if event.keyval in (Gdk.KEY_q, Gdk.KEY_Q):
                self.close()
                return True
        return False

    def on_resize(self, *_):
        # Changing requisitions inside size-allocate can leave GtkViewport's
        # scroll extent stale. Apply the change after allocation has finished.
        if not self.layout_pending:
            self.layout_pending = True
            GLib.idle_add(self.adapt_layout)

    def adapt_layout(self):
        self.layout_pending = False
        if not self.closed:
            width = self.dashboard_scroll.get_allocated_width()
            # Measure the actual content area and card minima, including theme
            # padding and text scaling, rather than the whole window width.
            card_minimum = max(
                child.get_preferred_width()[0]
                for child in self.workspace.get_children()
            )
            vertical = width < max(860, 2 * card_minimum + self.workspace.get_spacing())
            orientation = (
                Gtk.Orientation.VERTICAL if vertical else Gtk.Orientation.HORIZONTAL
            )
            if self.workspace.get_orientation() != orientation:
                self.workspace.set_orientation(orientation)
                self.workspace.set_homogeneous(not vertical)
            metric_minimum = max(
                child.get_preferred_width()[0] for child in self.metrics.get_children()
            )
            self.metrics.set_orientation(
                Gtk.Orientation.VERTICAL
                if width < 3 * metric_minimum + 2 * self.metrics.get_spacing()
                else Gtk.Orientation.HORIZONTAL
            )

        return False

    def navigate(self, _, row):
        if row:
            self.stack.set_visible_child_name(row.page)

    def page(self, title, subtitle):
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        page.pack_start(label(title, "page-title"), False, False, 0)
        page.pack_start(label(subtitle, "muted"), False, False, 0)
        return page

    def table(self, columns, model, selected):
        tree = Gtk.TreeView(model=model, headers_visible=True)
        tree.set_grid_lines(Gtk.TreeViewGridLines.NONE)
        for index, title in enumerate(columns):
            renderer = Gtk.CellRendererText()
            renderer.set_property("ellipsize", Pango.EllipsizeMode.MIDDLE)
            column = Gtk.TreeViewColumn(title, renderer, text=index)
            column.set_resizable(True)
            column.set_expand(index == 0)
            column.set_min_width(160 if index == 0 else 145)
            tree.append_column(column)
        tree.get_selection().connect("changed", selected)
        tree.set_tooltip_column(3)
        return tree

    def make_profiles(self):
        page = self.page(
            "My VPNs",
            "A clear view of your networks. One place to connect and stay in control.",
        )
        metrics = Gtk.Box(spacing=14, homogeneous=True)
        self.metrics = metrics
        self.metric_values = []
        for title, icon in (
            ("Saved profiles", "folder-symbolic"),
            ("Connected", "network-vpn-symbolic"),
            ("Sessions", "network-transmit-receive-symbolic"),
        ):
            card = Gtk.Box(spacing=10)
            card.get_style_context().add_class("metric")
            picture = Gtk.Image.new_from_icon_name(icon, Gtk.IconSize.LARGE_TOOLBAR)
            picture.get_style_context().add_class("metric-icon")
            card.pack_start(picture, False, False, 0)
            words = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
            value = label("—", "metric-value")
            self.metric_values.append(value)
            words.pack_start(value, False, False, 0)
            words.pack_start(label(title, "muted"), False, False, 0)
            card.pack_start(words, True, True, 0)
            metrics.pack_start(card, True, True, 0)
        page.pack_start(metrics, False, False, 4)
        top = Gtk.Box(spacing=10)
        self.profile_search = Gtk.SearchEntry(placeholder_text="Find a VPN…")
        self.profile_search.connect("search-changed", lambda *_: self.render_profiles())
        top.pack_start(self.profile_search, True, True, 0)
        self.import_button = button(
            "Import profile", self.import_profile, "suggested-action"
        )
        self.import_button.set_image(
            Gtk.Image.new_from_icon_name("list-add-symbolic", Gtk.IconSize.BUTTON)
        )
        self.import_button.set_always_show_image(True)
        self.import_button.set_tooltip_text("Import an OpenVPN configuration (Ctrl+I)")
        top.pack_end(self.import_button, False, False, 0)
        page.pack_start(top, False, False, 0)
        self.summary = label("Loading your VPNs…", "muted")
        page.pack_start(self.summary, False, False, 0)
        self.profile_store = Gtk.ListStore(str, str, str, str)
        self.profile_tree = self.table(
            ["Network", "Status"], self.profile_store, self.profile_selected
        )
        self.profile_tree.get_accessible().set_name(
            "Saved VPN profiles and active connections"
        )
        self.profile_tree.connect("row-activated", lambda *_: self.primary_action())
        workspace = Gtk.Box(spacing=16)
        self.workspace = workspace
        # Start stacked so a wide initial requisition cannot prevent shrinking.
        workspace.set_orientation(Gtk.Orientation.VERTICAL)
        page.pack_start(workspace, True, True, 0)
        network_list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        network_list.get_style_context().add_class("vpn-list")
        network_list.pack_start(label("YOUR NETWORKS", "eyebrow"), False, False, 0)
        network_scroll = scrolled(self.profile_tree)
        network_scroll.set_min_content_height(230)
        network_list.pack_start(network_scroll, True, True, 0)
        workspace.pack_start(network_list, True, True, 0)
        self.profile_empty = label("", "muted")
        network_list.pack_start(self.profile_empty, False, False, 0)
        details = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        details.get_style_context().add_class("card")
        self.connection_card = details
        self.connection_icon = application_icon(36)
        self.connection_icon.set_halign(Gtk.Align.START)
        self.connection_icon.set_pixel_size(32)
        self.connection_icon.set_valign(Gtk.Align.START)
        self.connection_icon.get_style_context().add_class("connection-icon")
        selection_header = Gtk.Box(spacing=16)
        selection_header.pack_start(self.connection_icon, False, False, 0)
        heading = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        heading.set_valign(Gtk.Align.CENTER)
        heading.pack_start(label("SELECTED NETWORK", "eyebrow"), False, False, 0)
        self.profile_name = label("Select a VPN", "section-title")
        self.profile_name.set_max_width_chars(24)
        self.profile_name.set_lines(2)
        self.profile_name.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
        heading.pack_start(self.profile_name, True, True, 0)
        self.primary_button = button(
            "Connect", lambda *_: self.primary_action(), "suggested-action"
        )

        selection_header.pack_start(heading, True, True, 0)
        details.pack_start(selection_header, False, False, 0)
        self.connection_label = label("Select a VPN", "status-pill")
        self.connection_label.set_halign(Gtk.Align.START)
        details.pack_start(self.connection_label, False, False, 0)
        self.connection_note = label(
            "Choose a saved profile to connect.", "connection-note"
        )
        details.pack_start(self.connection_note, False, False, 0)
        details.pack_start(self.primary_button, False, False, 2)
        details.pack_start(Gtk.Separator(), False, False, 2)
        self.session_picker = Gtk.ComboBoxText()
        self.session_picker.set_no_show_all(True)
        self.session_picker.connect("changed", self.choose_session)
        details.pack_start(self.session_picker, False, False, 0)
        actions = Gtk.Box(spacing=8)
        self.pause_button = button("Pause", self.toggle_pause)
        self.stats_button = button(
            "Statistics", lambda *_: self.session_command("session-stats", run=True)
        )
        self.logs_button = button(
            "Logs", lambda *_: self.session_command("log", run=True)
        )
        for control in (self.pause_button, self.stats_button, self.logs_button):
            actions.pack_start(control, False, False, 0)
        more = Gtk.MenuButton(label="More ▾")
        self.more_button = more
        menu = Gtk.Popover.new(more)
        options = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        options.set_border_width(10)
        self.profile_buttons = []
        self.session_buttons = [self.pause_button, self.stats_button, self.logs_button]
        for title, callback, category in (
            ("Rename profile", self.rename_profile, "profile"),
            (
                "Profile settings",
                lambda *_: self.profile_command("config-manage", {"show": ""}),
                "profile",
            ),
            (
                "Profile access",
                lambda *_: self.profile_command("config-acl", {"show": ""}),
                "profile",
            ),
            ("View / export profile", self.export_profile, "profile"),
            ("Delete profile…", self.delete_profile, "profile"),
            (
                "Restart connection",
                lambda *_: self.manage_session("restart"),
                "session",
            ),
            (
                "Connection access",
                lambda *_: self.session_command("session-acl", {"show": ""}),
                "session",
            ),
            (
                "Authentication requests",
                lambda *_: self.run_command(["session-auth"]),
                None,
            ),
            (
                "Clean up stale sessions",
                lambda *_: self.run_command(
                    ["session-manage", "--cleanup"], routine=True
                ),
                None,
            ),
        ):

            def clicked(widget, action=callback):
                menu.popdown()
                action(widget)

            control = button(title, clicked)
            options.pack_start(control, False, False, 0)
            if category == "profile":
                self.profile_buttons.append(control)
            elif category == "session":
                self.session_buttons.append(control)
        menu.add(options)
        options.show_all()
        more.set_popover(menu)
        actions.pack_end(more, False, False, 0)
        details.pack_start(actions, False, False, 0)
        technical = Gtk.Expander(label="Profile & connection details")
        technical_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.profile_path = label("", "muted")
        self.profile_path.set_selectable(True)
        self.profile_path.set_line_wrap_mode(Pango.WrapMode.CHAR)
        self.profile_meta = label("", "muted")
        self.session_details = label("", "muted")
        self.session_details.set_selectable(True)
        self.session_details.set_line_wrap_mode(Pango.WrapMode.CHAR)
        for control in (self.profile_path, self.profile_meta, self.session_details):
            technical_box.pack_start(control, False, False, 0)
        technical.add(technical_box)
        details.pack_start(technical, False, False, 0)
        workspace.pack_start(details, True, True, 0)
        self.activity = Gtk.Expander(label="Last action details")
        self.activity.connect("notify::expanded", self.reveal_activity)
        self.activity.set_no_show_all(True)
        self.activity_view = Gtk.TextView(
            editable=False, monospace=True, wrap_mode=Gtk.WrapMode.WORD_CHAR
        )
        activity_scroll = scrolled(self.activity_view)
        activity_scroll.set_size_request(-1, 110)
        self.activity.add(activity_scroll)
        activity_scroll.show_all()
        page.pack_start(self.activity, False, False, 0)
        self.update_actions()
        return page

    def reveal_activity(self, *_):
        if self.activity.get_expanded():

            def scroll_after_layout():
                if not self.closed and self.activity.get_expanded():
                    adjustment = self.dashboard_scroll.get_vadjustment()
                    adjustment.set_value(
                        max(
                            adjustment.get_lower(),
                            adjustment.get_upper() - adjustment.get_page_size(),
                        )
                    )
                return False

            GLib.timeout_add(100, scroll_after_layout)

    def make_commands(self):
        page = self.page(
            "Advanced tools",
            "Optional settings and diagnostics for experienced users. For everyday connections, use My VPNs. All installed CLI commands are available here.",
        )
        self.command_combo = Gtk.ComboBoxText()
        for renderer in self.command_combo.get_cells():
            renderer.set_property("ellipsize", Pango.EllipsizeMode.END)
            renderer.set_property("max-width-chars", 45)
        self.command_combo.connect("changed", self.command_changed)
        page.pack_start(self.command_combo, False, False, 0)
        self.form_holder = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        page.pack_start(self.form_holder, True, True, 0)
        return page

    def make_about(self):
        page = self.page(
            "A simpler way to connect",
            f"OpenVPN 3 GUI {__version__} · Native GTK desktop client for Debian and Ubuntu",
        )
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        content.get_style_context().add_class("card")
        for heading, body in (
            (
                "An independent community app",
                "OpenVPN 3 GUI is an independent Linux companion, not OpenVPN Connect. It is not affiliated with or endorsed by OpenVPN Inc. OpenVPN is a registered trademark of OpenVPN Inc.",
            ),
            (
                "Get connected",
                "Import an .ovpn file, give it a friendly name, and keep “Remember after restart” enabled. Select the profile and choose Connect. Enter credentials in the command window when prompted.",
            ),
            (
                "Duplicate names are safe to manage",
                "Profile actions use the unique D-Bus identifier. If two profiles share a name, select the identifier you want, then rename or delete that exact profile. Deleting a profile does not delete the original .ovpn file.",
            ),
            (
                "Full CLI access",
                "Advanced tools includes configuration overrides, tags, ACLs, authentication requests, log levels, statistics, JSON output, and CLI helpers. Options and aliases follow the installed openvpn3 version. Other binaries such as openvpn3-admin are outside this interface.",
            ),
            (
                "Authentication & privacy",
                "The embedded terminal supports passwords, MFA, and interactive prompts. Copy an authentication URL into your browser if your server uses web sign-in. Ctrl+Shift+C / Ctrl+Shift+V copy and paste. The app does not save credentials or command output. CLI arguments such as proxy passwords may be visible to local process inspection; configuration exports can contain private keys.",
            ),
            (
                "Connections outlive the window",
                "OpenVPN services manage the tunnel. Closing this app does not disconnect established VPN sessions. Use My VPNs → Disconnect when you want to end one. Run the app as your normal desktop user, without sudo.",
            ),
        ):
            content.pack_start(label(heading, "section-title"), False, False, 0)
            content.pack_start(label(body, "muted"), False, False, 0)
        self.coverage = label("Discovering CLI capabilities…", "muted")
        content.pack_start(self.coverage, False, False, 0)
        content.pack_start(
            Gtk.LinkButton(
                uri="https://openvpn.net/community-docs/openvpn-3-client-for-linux.html",
                label="OpenVPN 3 Linux documentation",
            ),
            False,
            False,
            0,
        )
        page.pack_start(scrolled(content), True, True, 0)
        return page

    def on_discover(self, commands):
        self.discovering = False
        self.commands = {command.name: command for command in commands}
        self.command_combo.remove_all()
        for command in commands:
            self.command_combo.append(
                command.name, f"{command.name} — {command.description}"
            )
        self.command_combo.set_active_id("config-manage")
        count = sum(len(command.options) for command in commands)
        self.coverage.set_text(
            f"Detected {len(commands)} commands and {count} command options from the installed openvpn3 CLI."
        )
        self.update_actions()

    def load_commands(self):
        if self.discovering or self.commands:
            return
        self.discovering = True

        def failed(error):
            self.discovering = False
            self.show_error(
                "Could not load CLI options. Use Refresh to retry.\n" + error
            )

        self.background(self.backend.discover, self.on_discover, failed)

    def command_changed(self, *_):
        name = self.command_combo.get_active_id()
        if name in self.commands:
            self.set_form(name)

    def set_form(self, name, defaults=None):
        for child in self.form_holder.get_children():
            self.form_holder.remove(child)
            child.destroy()
        form = CommandForm(self.commands[name], self.run_command, defaults)
        self.form_holder.pack_start(form, True, True, 0)
        self.form_holder.show_all()

    def open_command(self, name, defaults=None):
        if name not in self.commands:
            self.show_error(
                f"Command '{name}' is unavailable. CLI discovery may still be running."
            )
            return
        self.command_combo.set_active_id(name)
        self.set_form(name, defaults)
        self.navigation.select_row(self.navigation.get_row_at_index(1))

    def refresh(self):
        if self.closed:
            return
        self.load_commands()
        if self.refreshing:
            self.refresh_again = True
            return
        self.refreshing = True
        self.refresh_button.set_sensitive(False)

        def work():
            # One service may fail while the other remains available.
            values = []
            for method in (self.backend.profiles, self.backend.sessions):
                try:
                    values.append((method(), None))
                except Exception as error:
                    values.append((None, str(error)))
            return values

        def done(values):
            self.refreshing = False
            self.refresh_button.set_sensitive(True)
            errors = []
            for (result, error), kind in zip(values, ("profiles", "sessions")):
                if error:
                    errors.append(f"{kind.capitalize()}: {error}")
                    # Never leave stale controls enabled after a service failure.
                    setattr(self, kind, [])
                else:
                    setattr(self, kind, result)
            self.session_error = values[1][1]
            self.render_profiles()
            for widget, value in zip(
                self.metric_values,
                (
                    len(self.profiles),
                    sum(connection_status([s]) == "Connected" for s in self.sessions),
                    len(self.sessions),
                ),
            ):
                widget.set_text(str(value) if not errors else "—")
            if errors:
                self.refresh_error = True
                self.summary.set_text(
                    "Some VPN information is unavailable. Use Refresh to retry."
                )
                self.show_error("\n".join(errors))
            else:
                self.summary.set_text(
                    ("Demo · " if self.backend.demo else "")
                    + f"{len(self.profiles)} saved profiles  ·  {len(self.sessions)} sessions  ·  Updates automatically"
                )
                if self.banner.get_text() == "Reading your OpenVPN installation…":
                    self.banner.set_text("Ready")
                if self.refresh_error:
                    self.refresh_error = False
                    self.show_status("VPN services are available again.")
            if self.refresh_again:
                self.refresh_again = False
                self.refresh()

        self.background(work, done)

    def poll(self):
        if self.closed:
            return False
        self.refresh()
        return True

    def render_profiles(self):
        selected_key = self.selected_key
        selected_session = (
            self.selected_session["path"] if self.selected_session else None
        )
        self.groups = group_connections(self.profiles, self.sessions)
        self.profile_store.clear()
        query = self.profile_search.get_text().casefold()
        names = Counter(profile["name"] for profile in self.profiles)
        rows = [
            (p["path"], p["name"], p.get("lastused") or "Never", names[p["name"]] > 1)
            for p in self.profiles
        ]
        profile_keys = {p["path"] for p in self.profiles}
        rows += [
            (key, group[0]["name"] + " · connection", "—", False)
            for key, group in self.groups.items()
            if key not in profile_keys
        ]
        restore = None
        for key, name, last_used, duplicate in rows:
            if query not in (name + " " + key).casefold():
                continue
            status = (
                "Status unavailable"
                if self.session_error
                else connection_status(self.groups[key])
            )
            iterator = self.profile_store.append(
                [
                    name + (" · " + key.rsplit("/", 1)[-1][-8:] if duplicate else ""),
                    status,
                    last_used,
                    key,
                ]
            )
            if key == selected_key:
                restore = iterator
        if restore is None and len(self.profile_store):
            restore = self.profile_store.get_iter_first()
        if restore is not None:
            self.profile_tree.get_selection().select_iter(restore)
            if selected_session:
                self.session_picker.set_active_id(selected_session)
                if not self.session_picker.get_active_id():
                    self.session_picker.set_active(0)
        self.profile_empty.set_text(
            "No VPNs yet. Import an .ovpn file to get started."
            if not rows
            else ("No matching VPNs." if len(self.profile_store) == 0 else "")
        )

    def profile_selected(self, selection):
        model, iterator = selection.get_selected()
        self.selected_key = model[iterator][3] if iterator is not None else None
        self.selected_profile = next(
            (p for p in self.profiles if p["path"] == self.selected_key), None
        )
        sessions = self.groups.get(self.selected_key, [])
        profile = self.selected_profile
        self.profile_name.set_text(
            profile["name"]
            if profile
            else (sessions[0]["name"] if sessions else "Select a VPN")
        )
        self.profile_name.set_tooltip_text(self.profile_name.get_text())
        self.profile_path.set_text(
            profile["path"]
            if profile
            else "No accessible saved profile for this connection."
        )
        self.profile_meta.set_text(
            f"Owner: {profile.get('acl', {}).get('owner', '—')}\nLast used: {profile.get('lastused', 'Never')}\nImported: {profile.get('imported', '—')}"
            if profile
            else ""
        )
        self.session_picker.remove_all()
        for index, session in enumerate(sessions, 1):
            self.session_picker.append(
                session["path"],
                f"Connection {index} · "
                + connection_status([session])
                + " · "
                + session["path"][-8:],
            )
        self.session_picker.set_visible(len(sessions) > 1)
        self.session_picker.set_active(0 if sessions else -1)
        self.choose_session()

    def choose_session(self, *_):
        path = self.session_picker.get_active_id()
        self.selected_session = next(
            (s for s in self.sessions if s["path"] == path), None
        )
        self.update_actions()

    def update_actions(self):
        if not hasattr(self, "primary_button"):
            return
        profile, session = self.selected_profile, self.selected_session
        available = bool(self.commands) and not self.busy
        self.primary_button.set_label(
            "Please wait…" if self.busy else ("Disconnect" if session else "Connect")
        )
        self.primary_button.set_sensitive(
            available and bool(profile or session) and not self.session_error
        )
        for control in self.profile_buttons:
            control.set_sensitive(available and profile is not None)
        for control in self.session_buttons:
            control.set_sensitive(available and session is not None)
        self.import_button.set_sensitive(available)
        self.pause_button.set_label(
            "Resume" if session and "paused" in session["status"].lower() else "Pause"
        )
        status = (
            "Status unavailable"
            if self.session_error
            else (connection_status([session]) if session else "Disconnected")
        )
        card_context = self.connection_card.get_style_context()
        primary_context = self.primary_button.get_style_context()
        if status == "Connected":
            card_context.add_class("connected")
        else:
            card_context.remove_class("connected")
        if session:
            primary_context.add_class("connection-active")
        else:
            primary_context.remove_class("connection-active")
        self.connection_label.set_text(status)
        context = self.connection_label.get_style_context()
        for state in ("online", "pending", "failed", "offline"):
            context.remove_class(state)
        context.add_class(
            "online"
            if status == "Connected"
            else (
                "failed"
                if self.session_error or "failed" in status or "error" in status
                else "pending" if session else "offline"
            )
        )
        self.connection_note.set_text(
            "Refresh to check this connection."
            if self.session_error
            else (
                "Your VPN session is active. Manage it here."
                if status == "Connected"
                else (
                    "This session is paused. Resume when you are ready."
                    if status == "Paused"
                    else (
                        "Ready when you are. Connect to this network below."
                        if profile and not session
                        else (
                            "Select a saved network to get started."
                            if not session
                            else session["status"]
                        )
                    )
                )
            )
        )
        self.session_details.set_text(
            session["path"] + "\n" + "\n".join(session.get("details", []))
            if session
            else "No active connection."
        )

    def primary_action(self):
        if self.busy or self.session_error:
            return
        if self.selected_session:
            return self.manage_session("disconnect")
        return self.connect_profile()

    def connect_profile(self):
        if self.selected_profile and not self.busy:
            return self.run_command(
                ["session-start", "--config-path", self.selected_profile["path"]],
                routine=True,
            )

    def toggle_pause(self, *_):
        if self.selected_session:
            self.manage_session(
                "resume"
                if "paused" in self.selected_session["status"].lower()
                else "pause"
            )

    def profile_command(self, command, defaults=None):
        if self.selected_profile:
            self.open_command(
                command, {"path": self.selected_profile["path"], **(defaults or {})}
            )

    def session_command(self, command, defaults=None, run=False):
        if self.selected_session:
            flag = "session-path" if command == "log" else "path"
            if run:
                self.run_command([command, "--" + flag, self.selected_session["path"]])
            else:
                self.open_command(
                    command, {flag: self.selected_session["path"], **(defaults or {})}
                )

    def manage_session(self, action):
        if self.selected_session:
            return self.run_command(
                [
                    "session-manage",
                    "--path",
                    self.selected_session["path"],
                    "--" + action,
                ],
                routine=True,
            )

    def run_command(self, arguments, routine=False):
        if routine and self.busy:
            return None
        if arguments[0] not in self.commands:
            self.show_error(
                "CLI capabilities are still loading or this command is unavailable."
            )
            return None
        flags = {arg.split("=", 1)[0] for arg in arguments[1:]}
        if "--help" not in flags:
            if arguments[0] == "config-remove":
                if not confirm(
                    self,
                    "Delete this imported profile?",
                    "This removes the selected profile from OpenVPN. Its original .ovpn file is kept.\n\n"
                    + " ".join(arguments[1:]),
                    "Delete profile",
                ):
                    return None
                if "--force" not in flags:
                    arguments = [*arguments, "--force"]
            if arguments[0] == "config-acl" and "--seal" in flags:
                if not confirm(
                    self,
                    "Permanently seal this profile?",
                    "OpenVPN makes a sealed profile permanently read-only. This action cannot be undone.",
                    "Seal profile",
                ):
                    return None
        messages = {
            "session-start": "Connection request completed.",
            "config-import": "Profile imported.",
            "config-remove": "Profile deleted.",
            "config-manage": "Profile updated.",
        }
        success_message = messages.get(arguments[0], "Action completed.")
        for flag, message in (
            ("--disconnect", "Disconnected."),
            ("--pause", "Connection paused."),
            ("--resume", "Connection resumed."),
            ("--restart", "Connection restarted."),
            ("--cleanup", "Stale sessions cleaned up."),
        ):
            if flag in flags:
                success_message = message
        if routine:
            self.busy = True
            self.activity.hide()
            self.show_status("Working…")
            self.update_actions()

        def finished(success):
            if self.closed:
                return
            if success:
                self.backend.command_succeeded(arguments)
            if routine:
                self.busy = False
                if success:
                    self.show_status(success_message)
                elif success is None:
                    self.show_status(
                        "Command stopped. Check the connection status below."
                    )
                else:
                    self.show_error(
                        "Action could not be completed. See the error details."
                    )
                self.update_actions()
            self.refresh()

        # These shortcuts do not need credentials. Their diagnostics stay in
        # an inline expander; connect/resume/restart retain an interactive PTY.
        quiet = routine and (
            arguments[0] in {"config-import", "config-remove", "config-manage"}
            or arguments[0] == "session-manage"
            and bool(flags & {"--disconnect", "--pause", "--cleanup"})
        )
        if quiet:

            def completed(output):
                self.activity_view.get_buffer().set_text(output or success_message)
                self.activity.set_expanded(False)
                self.activity.show()
                finished(True)

            def failed(error):
                self.activity_view.get_buffer().set_text(error)
                self.activity.set_expanded(True)
                self.activity.show()
                finished(False)

            self.background(lambda: self.backend.execute(arguments), completed, failed)
            return None
        auto_close = routine or (
            arguments[0] == "session-manage"
            and bool(
                flags
                & {"--disconnect", "--pause", "--resume", "--restart", "--cleanup"}
            )
            and "--help" not in flags
        )
        return CommandWindow(
            self, self.backend, arguments, finished, auto_close=auto_close
        )

    def delete_profile(self, *_):
        if self.selected_profile:
            self.run_command(
                ["config-remove", "--path", self.selected_profile["path"]], routine=True
            )

    def rename_profile(self, *_):
        if not self.selected_profile:
            return
        profile = dict(self.selected_profile)
        dialog = Gtk.Dialog(title="Rename profile", transient_for=self, modal=True)
        dialog.add_buttons(
            "Cancel", Gtk.ResponseType.CANCEL, "Rename", Gtk.ResponseType.OK
        )
        entry = Gtk.Entry(text=profile["name"], activates_default=True)
        entry.set_width_chars(55)
        entry.set_margin_top(18)
        entry.set_margin_bottom(18)
        entry.set_margin_start(18)
        entry.set_margin_end(18)
        dialog.get_content_area().add(entry)
        dialog.set_default_response(Gtk.ResponseType.OK)
        dialog.show_all()
        response = dialog.run()
        name = entry.get_text().strip()
        dialog.destroy()
        if response == Gtk.ResponseType.OK and name:
            self.run_command(
                ["config-manage", "--path", profile["path"], "--rename=" + name],
                routine=True,
            )

    def import_profile(self, *_):
        dialog = Gtk.Dialog(title="Import VPN profile", transient_for=self, modal=True)
        dialog.set_default_size(560, 280)
        dialog.add_buttons(
            "Cancel", Gtk.ResponseType.CANCEL, "Import", Gtk.ResponseType.OK
        )
        content = dialog.get_content_area()
        content.set_border_width(20)
        content.set_spacing(12)
        content.pack_start(
            label("Choose your OpenVPN configuration", "section-title"), False, False, 0
        )
        chooser = Gtk.FileChooserButton(
            title="Choose an OpenVPN profile", action=Gtk.FileChooserAction.OPEN
        )
        filter_ = Gtk.FileFilter()
        filter_.set_name("OpenVPN profiles (*.ovpn, *.conf)")
        filter_.add_pattern("*.ovpn")
        filter_.add_pattern("*.conf")
        chooser.add_filter(filter_)
        all_files = Gtk.FileFilter()
        all_files.set_name("All files")
        all_files.add_pattern("*")
        chooser.add_filter(all_files)
        content.pack_start(chooser, False, False, 0)
        name = Gtk.Entry(placeholder_text="Friendly name, e.g. Office VPN")
        content.pack_start(name, False, False, 0)
        persistent = Gtk.CheckButton(label="Remember after restart (persistent)")
        persistent.set_active(True)
        content.pack_start(persistent, False, False, 0)
        tag = Gtk.Entry(placeholder_text="Optional tag")
        content.pack_start(tag, False, False, 0)
        notice = label(
            "Use a unique, friendly name to keep your profiles easy to recognize.",
            "muted",
        )
        content.pack_start(notice, False, False, 0)
        accept = dialog.get_widget_for_response(Gtk.ResponseType.OK)
        accept.get_style_context().add_class("suggested-action")
        accept.set_sensitive(False)

        def validate(*_):
            chosen_name = name.get_text().strip()
            duplicate = any(profile["name"] == chosen_name for profile in self.profiles)
            accept.set_sensitive(
                bool(chooser.get_filename() and chosen_name and not duplicate)
            )
            notice.set_text(
                "That name already exists. Choose another name."
                if duplicate
                else "Persistent profiles remain available after OpenVPN service restarts."
            )

        def chosen(*_):
            if not name.get_text() and chooser.get_filename():
                name.set_text(Path(chooser.get_filename()).stem)
            validate()

        chooser.connect("file-set", chosen)
        name.connect("changed", validate)
        dialog.show_all()
        response = dialog.run()
        args = [
            "config-import",
            "--config",
            chooser.get_filename() or "",
            "--name=" + name.get_text().strip(),
        ]
        if persistent.get_active():
            args.append("--persistent")
        if tag.get_text().strip():
            args.append("--tag=" + tag.get_text().strip())
        dialog.destroy()
        if response == Gtk.ResponseType.OK:
            self.run_command(args, routine=True)

    def export_profile(self, *_):
        if not self.selected_profile:
            return
        profile = dict(self.selected_profile)

        def loaded(content):
            dialog = Gtk.Dialog(title="View / export profile", transient_for=self)
            dialog.set_default_size(820, 600)
            dialog.add_buttons(
                "Close", Gtk.ResponseType.CLOSE, "Save .ovpn…", Gtk.ResponseType.APPLY
            )
            box = dialog.get_content_area()
            box.set_border_width(16)
            box.set_spacing(12)
            box.pack_start(
                label(
                    "This configuration may contain private keys. Save it only to a trusted location.",
                    "muted",
                ),
                False,
                False,
                0,
            )
            view = Gtk.TextView(
                editable=False, monospace=True, wrap_mode=Gtk.WrapMode.WORD_CHAR
            )
            view.get_buffer().set_text(content)
            box.pack_start(scrolled(view), True, True, 0)

            def respond(_, response):
                if response != Gtk.ResponseType.APPLY:
                    dialog.destroy()
                    return
                chooser = Gtk.FileChooserDialog(
                    title="Export OpenVPN profile",
                    transient_for=dialog,
                    action=Gtk.FileChooserAction.SAVE,
                )
                chooser.add_buttons(
                    "Cancel", Gtk.ResponseType.CANCEL, "Save", Gtk.ResponseType.OK
                )
                chooser.set_do_overwrite_confirmation(True)
                basename = Path(profile["name"]).name or "vpn-profile"
                chooser.set_current_name(
                    basename if basename.endswith(".ovpn") else basename + ".ovpn"
                )
                accepted = chooser.run() == Gtk.ResponseType.OK
                filename = chooser.get_filename()
                chooser.destroy()
                if accepted and filename:
                    try:
                        save_private_file(filename, content)
                        self.show_status(
                            "Profile exported with owner-only file permissions."
                        )
                    except OSError as error:
                        self.show_error(f"Could not export profile: {error}")

            dialog.connect("response", respond)
            dialog.show_all()

        self.background(lambda: self.backend.dump_profile(profile["path"]), loaded)

    def on_close(self, *_):
        if self.busy:
            self.show_error("An action is still running. Please wait for it to finish.")
            return True
        # Avoid orphaning hidden interactive prompts when closing the main window.
        active = [
            window
            for window in self.get_application().get_windows()
            if isinstance(window, CommandWindow) and window.running
        ]
        if active:
            self.show_error(
                "Finish or close the running command windows before closing the app."
            )
            active[0].present()
            return True
        for window in list(self.get_application().get_windows()):
            if window is not self:
                window.destroy()
        return False

    def on_destroy(self, *_):
        self.closed = True
        GLib.source_remove(self.poll_id)
        self.executor.shutdown(wait=False, cancel_futures=True)


class Application(Gtk.Application):
    def __init__(self, demo=False):
        super().__init__(
            application_id="io.github.openvpn3gui.Desktop" + (".Demo" if demo else ""),
            flags=Gio.ApplicationFlags.FLAGS_NONE,
        )
        self.demo = demo

    def do_activate(self):
        window = self.get_active_window()
        if window:
            window.present()
            return
        # Use a consistent dark base for dialogs, menus and native controls too.
        settings = Gtk.Settings.get_default()
        settings.set_property("gtk-theme-name", "Adwaita")
        settings.set_property("gtk-application-prefer-dark-theme", True)
        Gtk.Window.set_default_icon_from_file(str(application_icon_path()))
        provider = Gtk.CssProvider()
        provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
        try:
            backend = Backend(self.demo)
        except CLIError as error:
            window = Gtk.ApplicationWindow(
                application=self, title="Set up OpenVPN 3 GUI"
            )
            window.set_default_size(620, 340)
            content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20)
            content.set_border_width(32)
            content.pack_start(label("One more step", "page-title"), False, False, 0)
            content.pack_start(label(str(error), "muted"), False, False, 0)
            content.pack_start(
                Gtk.LinkButton(
                    uri="https://openvpn.net/community-docs/openvpn-client-for-linux.html",
                    label="Open the official installation guide",
                ),
                False,
                False,
                0,
            )

            def retry(_, demo=False):
                self.demo = demo
                window.destroy()
                self.activate()

            actions = Gtk.Box(spacing=12)
            actions.pack_start(
                button("Explore demo", lambda w: retry(w, True)), False, False, 0
            )
            actions.pack_end(
                button("Check again", retry, "suggested-action"), False, False, 0
            )
            content.pack_end(actions, False, False, 0)
            window.add(content)
            window.show_all()
            return
        MainWindow(self, backend)
