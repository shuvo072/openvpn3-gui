"""GTK widgets for command forms and interactive, shell-free execution."""

import os
from pathlib import Path
import signal
import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("Vte", "2.91")
from gi.repository import Gdk, GLib, Gtk, Pango, Vte

from .backend import build_arguments, command_preview


def label(text, style=None):
    widget = Gtk.Label(label=text, xalign=0)
    widget.set_line_wrap(True)
    # Paths and server messages may contain no spaces. They must wrap rather
    # than impose their full word length as a minimum width on the window.
    widget.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
    widget.set_max_width_chars(60)
    if style:
        widget.get_style_context().add_class(style)
    return widget


def button(text, callback, style=None):
    widget = Gtk.Button(label=text)
    widget.connect("clicked", callback)
    if style:
        widget.get_style_context().add_class(style)
    return widget


def scrolled(child):
    scroll = Gtk.ScrolledWindow()
    scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
    scroll.add(child)
    return scroll


def confirm(parent, title, detail, action="Continue"):
    dialog = Gtk.MessageDialog(
        transient_for=parent,
        modal=True,
        message_type=Gtk.MessageType.WARNING,
        buttons=Gtk.ButtonsType.NONE,
        text=title,
    )
    dialog.format_secondary_text(detail)
    dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
    accept = dialog.add_button(action, Gtk.ResponseType.OK)
    accept.get_style_context().add_class("destructive-action")
    dialog.set_default_response(Gtk.ResponseType.CANCEL)
    result = dialog.run() == Gtk.ResponseType.OK
    dialog.destroy()
    return result


class OptionRow(Gtk.Box):
    def __init__(self, option, changed):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.get_style_context().add_class("option-row")
        self.option = option
        self.set_margin_bottom(12)
        line = Gtk.Box(spacing=12)
        self.pack_start(line, False, False, 0)
        self.enabled = Gtk.CheckButton(label="--" + option.name)
        self.enabled.set_size_request(220, -1)
        self.enabled.set_tooltip_text(
            ("Alias: -" + option.short + "\n" if option.short else "")
            + option.description
        )
        line.pack_start(self.enabled, False, False, 0)
        self.editor = None
        if option.argument:
            if option.choices:
                self.editor = Gtk.ComboBoxText.new_with_entry()
                for choice in option.choices:
                    self.editor.append_text(choice)
                self.entry = self.editor.get_child()
            else:
                self.editor = Gtk.Entry()
                self.entry = self.editor
            self.entry.set_placeholder_text(
                option.argument + (" · blank = query" if option.optional else "")
            )
            if any(word in option.name for word in ("password", "secret", "token")):
                self.entry.set_visibility(False)
                self.entry.set_input_purpose(Gtk.InputPurpose.PASSWORD)
            self.entry.connect("changed", lambda *_: changed())
            self.editor.set_sensitive(False)
            line.pack_start(self.editor, True, True, 0)
        self.enabled.connect("toggled", lambda *_: self.on_toggle(changed))
        description = label(option.description, "muted")
        description.set_margin_start(8)
        self.pack_start(description, False, False, 0)

    def on_toggle(self, changed):
        if self.editor:
            self.editor.set_sensitive(self.enabled.get_active())
        changed()

    def value(self):
        return self.entry.get_text() if self.editor else ""

    def set_value(self, value=""):
        self.enabled.set_active(True)
        if self.editor:
            self.entry.set_text(value)


class CommandForm(Gtk.Box):
    def __init__(self, command, run, defaults=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        self.command = command
        self.rows = []
        self.set_border_width(20)
        self.pack_start(label(command.name, "page-title"), False, False, 0)
        self.pack_start(label(command.description, "muted"), False, False, 0)
        self.search = Gtk.SearchEntry(placeholder_text="Find an option…")
        self.search.connect("search-changed", self.filter_rows)
        self.pack_start(self.search, False, False, 0)
        self.fields = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.pack_start(scrolled(self.fields), True, True, 0)
        for option in command.options:
            self.add_row(option)
        repeat_line = Gtk.Box(spacing=8)
        repeat_line.pack_start(label("Repeat an option"), False, False, 0)
        self.repeat = Gtk.ComboBoxText()
        for option in command.options:
            self.repeat.append_text("--" + option.name)
        self.repeat.set_active(0)
        repeat_line.pack_start(self.repeat, True, True, 0)
        add = button("Add", self.repeat_option)
        add.set_sensitive(bool(command.options))
        repeat_line.pack_start(add, False, False, 0)
        self.pack_start(repeat_line, False, False, 0)
        self.preview = label("", "command-preview")
        self.preview.set_selectable(True)
        self.preview.set_line_wrap_mode(Pango.WrapMode.CHAR)
        self.pack_start(self.preview, False, False, 0)
        footer = Gtk.Box(spacing=10)
        footer.pack_start(button("CLI help", self.show_help), False, False, 0)
        footer.pack_start(button("Reset options", self.reset), False, False, 0)
        self.run_button = button(
            "Run command", lambda *_: run(self.arguments()), "suggested-action"
        )
        footer.pack_end(self.run_button, False, False, 0)
        self.pack_start(footer, False, False, 0)
        for row in self.rows:
            if defaults and row.option.name in defaults:
                row.set_value(defaults[row.option.name])
        self.update_preview()

    def reset(self, *_):
        for row in self.rows[len(self.command.options) :]:
            self.fields.remove(row)
            row.destroy()
        self.rows = self.rows[: len(self.command.options)]
        for row in self.rows:
            row.enabled.set_active(False)
            if row.editor:
                row.entry.set_text("")
        self.search.set_text("")
        self.update_preview()

    def add_row(self, option):
        row = OptionRow(option, self.update_preview)
        self.rows.append(row)
        self.fields.pack_start(row, False, False, 0)
        return row

    def repeat_option(self, *_):
        index = self.repeat.get_active()
        if index >= 0:
            row = self.add_row(self.command.options[index])
            row.show_all()
            self.search.set_text("")
            row.enabled.set_active(True)
            if row.editor:
                row.entry.grab_focus()

    def filter_rows(self, *_):
        query = self.search.get_text().casefold()
        for row in self.rows:
            row.set_visible(
                query in (row.option.name + " " + row.option.description).casefold()
            )

    def arguments(self):
        return build_arguments(
            self.command.name,
            [
                (row.option, row.value())
                for row in self.rows
                if row.enabled.get_active()
            ],
        )

    def update_preview(self):
        if not hasattr(self, "preview"):
            return
        try:
            self.preview.set_text(command_preview(self.arguments()))
            self.run_button.set_sensitive(True)
        except ValueError as error:
            self.preview.set_text(str(error))
            self.run_button.set_sensitive(False)

    def show_help(self, *_):
        dialog = Gtk.Dialog(
            title=f"{self.command.name} · CLI help", transient_for=self.get_toplevel()
        )
        dialog.set_default_size(820, 580)
        view = Gtk.TextView(
            editable=False, monospace=True, wrap_mode=Gtk.WrapMode.WORD_CHAR
        )
        view.set_left_margin(16)
        view.set_right_margin(16)
        view.get_buffer().set_text(self.command.help)
        dialog.get_content_area().pack_start(scrolled(view), True, True, 0)
        dialog.add_button("Close", Gtk.ResponseType.CLOSE)
        dialog.connect("response", lambda *_: dialog.destroy())
        dialog.show_all()


class CommandWindow(Gtk.Window):
    def __init__(self, parent, backend, arguments, finished, auto_close=False):
        super().__init__(title=f"{arguments[0]} · OpenVPN 3 GUI", transient_for=parent)
        self.set_application(parent.get_application())
        self.set_default_size(850, 540)
        self.running = True
        self.pid = None
        self.finished = finished
        self.auto_close = auto_close
        self.close_requested = False
        self.connect("delete-event", self.on_close)
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        outer.set_border_width(18)
        self.add(outer)
        preview = label(command_preview(arguments), "command-preview")
        preview.set_line_wrap_mode(Pango.WrapMode.CHAR)
        preview.set_selectable(True)
        outer.pack_start(preview, False, False, 0)
        outer.pack_start(
            label(
                "Respond to prompts below. Password input stays hidden when requested by OpenVPN.",
                "muted",
            ),
            False,
            False,
            0,
        )
        self.terminal = Vte.Terminal()
        self.terminal.set_scrollback_lines(5000)
        self.terminal.set_font(Pango.FontDescription("Monospace 11"))
        bg, fg = Gdk.RGBA(), Gdk.RGBA()
        bg.parse("#152238")
        fg.parse("#ecf3ff")
        self.terminal.set_colors(fg, bg, [])
        self.terminal.set_input_enabled(True)
        self.terminal.connect("child-exited", self.on_exit)
        self.terminal.connect("key-press-event", self.on_key)
        outer.pack_start(scrolled(self.terminal), True, True, 0)
        footer = Gtk.Box(spacing=8)
        self.status = label("Starting…", "muted")
        footer.pack_start(self.status, True, True, 0)
        footer.pack_end(button("Close", lambda *_: self.close()), False, False, 0)
        self.stop = button("Stop command", self.stop_command)
        footer.pack_end(self.stop, False, False, 0)
        footer.pack_end(
            button(
                "Copy selection",
                lambda *_: self.terminal.copy_clipboard_format(Vte.Format.TEXT),
            ),
            False,
            False,
            0,
        )
        outer.pack_start(footer, False, False, 0)
        self.show_all()
        env = {**os.environ, "LC_ALL": "C", "TERM": "xterm-256color"}
        # The demo module is launched from the project/install root, independently of cwd.
        directory = str(Path(__file__).resolve().parent.parent)
        self.terminal.spawn_async(
            Vte.PtyFlags.DEFAULT,
            directory,
            backend.argv(arguments),
            [f"{key}={value}" for key, value in env.items()],
            GLib.SpawnFlags.DEFAULT,
            None,
            None,
            -1,
            None,
            self.on_spawn,
            None,
        )

    def on_spawn(self, terminal, pid, error, *_):
        if error:
            self.running = False
            self.status.set_text(f"Could not start: {error.message}")
            self.stop.set_sensitive(False)
            self.finished(False)
            if self.close_requested:
                self.destroy()
            return
        self.pid = pid
        if self.running:
            self.status.set_text(
                "Running · credentials and output are not saved by this app"
            )
            self.terminal.grab_focus()
            if self.close_requested:
                self.terminate_child()

    def on_exit(self, terminal, status):
        self.running = False
        self.pid = None
        code = os.waitstatus_to_exitcode(status)
        self.status.set_text(
            "Completed successfully"
            if code == 0
            else f"Command ended (exit {code}) · see output above"
        )
        self.stop.set_sensitive(False)
        self.terminal.set_input_enabled(False)
        self.finished(None if self.close_requested else code == 0)
        if (code == 0 and self.auto_close) or self.close_requested:
            self.destroy()

    def on_key(self, terminal, event):
        modifiers = event.state & Gtk.accelerator_get_default_mod_mask()
        if modifiers == (Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.SHIFT_MASK):
            if event.keyval in (Gdk.KEY_C, Gdk.KEY_c):
                terminal.copy_clipboard_format(Vte.Format.TEXT)
                return True
            if event.keyval in (Gdk.KEY_V, Gdk.KEY_v):
                terminal.paste_clipboard()
                return True
        return False

    def stop_command(self, *_):
        if self.pid and self.running:
            try:
                os.kill(self.pid, signal.SIGINT)
                self.status.set_text("Interrupt requested…")
            except ProcessLookupError:
                pass

    def on_close(self, *_):
        if self.running:
            if not self.close_requested and not confirm(
                self,
                "Close this running command?",
                "This stops the CLI process. A VPN session may continue in the background; use My VPNs to disconnect it.",
                "Stop and close",
            ):
                return True
            self.close_requested = True
            self.terminate_child()
            # Keep the PTY alive until child-exited releases the main window's
            # busy state. Destroying it now can lose that completion signal.
            return True
        return False

    def terminate_child(self):
        self.status.set_text("Stopping command…")
        if self.pid:
            try:
                os.kill(self.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
