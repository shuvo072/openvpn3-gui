#!/usr/bin/python3
"""Capture the real curses app inside a terminal, using isolated demo data."""

import os
from pathlib import Path
import signal
import sys
import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("Vte", "2.91")
from gi.repository import Gdk, GLib, Gtk, Pango, Vte

ROOT = Path(__file__).resolve().parent.parent
window = Gtk.Window(title="OpenVPN 3 TUI - demo terminal")
terminal = Vte.Terminal()
terminal.set_font(Pango.FontDescription("DejaVu Sans Mono 11"))
terminal.set_size(112, 30)
background, foreground = Gdk.RGBA(), Gdk.RGBA()
background.parse("#101325")
foreground.parse("#edf0f7")
terminal.set_color_background(background)
terminal.set_color_foreground(foreground)
window.add(terminal)
window.show_all()
state = {"pid": None, "ok": False, "capture": 0}


def spawned(widget, pid, error, *_):
    if error:
        print(error, file=sys.stderr)
        Gtk.main_quit()
        return
    state["pid"] = pid
    GLib.timeout_add_seconds(9, capture)


def capture():
    name = "tui-dashboard.png" if state["capture"] == 0 else "tui-advanced.png"
    pixbuf = Gdk.pixbuf_get_from_window(
        window.get_window(),
        0,
        0,
        window.get_allocated_width(),
        window.get_allocated_height(),
    )
    if pixbuf is None:
        Gtk.main_quit()
        return False
    pixbuf.savev(str(ROOT / "docs/screenshots" / name), "png", [], [])
    if state["capture"] == 0:
        state["capture"] = 1
        terminal.feed_child(b"a")
        GLib.timeout_add_seconds(1, capture)
    else:
        state["ok"] = True
        terminal.feed_child(b"\x1b")
        GLib.timeout_add(1200, lambda: terminal.feed_child(b"q"))
    return False


def exited(*_):
    Gtk.main_quit()


terminal.connect("child-exited", exited)
env = {**os.environ, "TERM": "xterm-256color", "LC_ALL": "C.UTF-8"}
terminal.spawn_async(
    Vte.PtyFlags.DEFAULT,
    str(ROOT),
    [str(ROOT / "openvpn3-tui"), "--demo"],
    [f"{k}={v}" for k, v in env.items()],
    GLib.SpawnFlags.DEFAULT,
    None,
    None,
    -1,
    None,
    spawned,
    None,
)
GLib.timeout_add_seconds(25, lambda: Gtk.main_quit())
Gtk.main()
if state["pid"]:
    try:
        os.kill(state["pid"], signal.SIGTERM)
    except ProcessLookupError:
        pass
window.destroy()
if not state["ok"]:
    sys.exit(1)
print("Captured real terminal dashboard and advanced picker using demo data.")
