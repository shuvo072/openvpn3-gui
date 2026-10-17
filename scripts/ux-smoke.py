#!/usr/bin/python3
"""Regression test for the unified VPN page and routine-action lifecycle."""

from pathlib import Path
import sys
import time
import traceback
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from openvpn3_gui.app import Application, MainWindow
from openvpn3_gui.widgets import CommandWindow
from gi.repository import GLib, Vte

app = Application(demo=True)
app.set_application_id("io.github.openvpn3gui.UXSmoke")
state = {"step": 0, "start": time.monotonic(), "ok": False}


def text(terminal):
    if hasattr(terminal, "get_text_format"):
        return terminal.get_text_format(Vte.Format.TEXT) or ""
    return terminal.get_text(None, None)[0] or ""


def command_windows():
    return [w for w in app.get_windows() if isinstance(w, CommandWindow)]


def tick():
    try:
        if time.monotonic() - state["start"] > 45:
            raise AssertionError(f"Timeout in step {state['step']}")
        window = next((w for w in app.get_windows() if isinstance(w, MainWindow)), None)
        if not window or not window.commands or window.refreshing:
            return True
        step = state["step"]
        if step == 0:
            assert len(window.navigation.get_children()) == 3
            assert window.profile_store[0][1] == "Connected"
            assert (
                window.profile_store[1][1] == "Disconnected"
            )  # Same name, different ID.
            window.profile_tree.get_selection().select_path(0)
            assert window.primary_button.get_label() == "Disconnect"
            window.toggle_pause()
            assert window.busy and not window.primary_button.get_sensitive()
            assert not command_windows()
            state["step"] = 1
        elif step == 1 and not window.busy:
            assert window.pause_button.get_label() == "Resume"
            assert window.connection_label.get_text() == "Paused"
            window.toggle_pause()
            state["step"] = 2
        elif step == 2 and not window.busy:
            assert not command_windows(), "Successful resume popup must close"
            assert window.connection_label.get_text() == "Connected"
            window.primary_action()
            assert not command_windows(), "Disconnect should not open a popup"
            state["step"] = 3
        elif step == 3 and not window.busy:
            assert window.primary_button.get_label() == "Connect"
            assert window.profile_store[0][1] == "Disconnected"
            assert window.banner.get_text() == "Disconnected."
            assert not command_windows()
            buffer = window.activity_view.get_buffer()
            assert "BYTES_IN" in buffer.get_text(*buffer.get_bounds(), True)
            assert window.activity.get_visible() and not window.activity.get_expanded()
            window.run_command(["config-manage", "--demo-fail"], routine=True)
            state["step"] = 4
        elif step == 4 and not window.busy:
            assert window.activity.get_expanded()
            assert window.primary_button.get_sensitive()
            assert "could not" in window.banner.get_text()
            state["runner"] = window.run_command(
                ["session-start", "--demo-fail"], routine=True
            )
            state["step"] = 5
        elif step == 5 and not window.busy:
            runner = state["runner"]
            assert runner in command_windows(), "Errors must remain visible"
            assert "access denied" in text(runner.terminal)
            runner.destroy()
            state["runner"] = window.primary_action()
            state["step"] = 6
        elif step == 6:
            runner = state["runner"]
            output = text(runner.terminal)
            if "Username:" in output:
                runner.terminal.feed_child(b"demo\n")
                state["step"] = 7
        elif step == 7:
            runner = state["runner"]
            if "Password:" in text(runner.terminal):
                runner.terminal.feed_child(b"test-secret\n")
                state["step"] = 8
        elif step == 8 and not window.busy:
            assert not command_windows(), "Successful connect popup must close"
            assert window.primary_button.get_label() == "Disconnect"
            assert window.connection_label.get_text() == "Connected"
            window.session_command("session-stats", run=True)
            state["step"] = 9
        elif step == 9:
            runners = command_windows()
            if runners and not runners[0].running:
                assert "BYTES_IN" in text(runners[0].terminal)
                runners[0].destroy()  # Read-only output stays available until closed.
                window.refresh()
                state["step"] = 10
        elif step == 10:
            assert window.primary_button.get_label() == "Disconnect"
            assert window.selected_profile["path"].endswith("demo_persistent")
            # Render the app itself; compositor screenshots may contain stale frames.
            try:
                import cairo

                surface = cairo.ImageSurface(
                    cairo.FORMAT_ARGB32,
                    window.get_allocated_width(),
                    window.get_allocated_height(),
                )
                window.draw(cairo.Context(surface))
                surface.write_to_png("/tmp/openvpn3-gui-unified.png")
            except ImportError:
                pass
            state["runner"] = window.run_command(
                ["session-start", "--config-path", window.selected_profile["path"]],
                routine=True,
            )
            state["step"] = 11
        elif step == 11:
            runner = state["runner"]
            if "Username:" in text(runner.terminal):
                with patch("openvpn3_gui.widgets.confirm", return_value=True):
                    # Gtk.Window.close may defer delete-event until after the
                    # mock context exits on X11. Invoke its handler synchronously.
                    runner.on_close()
                state["step"] = 12
        elif step == 12 and not window.busy:
            assert (
                not command_windows()
            ), "Cancelling authentication must close its window"
            assert (
                window.primary_button.get_sensitive()
            ), "Cancellation must release the busy state"
            assert window.banner.get_text().startswith("Command stopped.")
            print(
                "PASS: combined status, duplicate identity, pause/resume, quiet disconnect, retained statistics, inline failures, terminal failures, automatic close, authentication, read-only output retention."
            )
            state["ok"] = True
            window.destroy()
            app.quit()
            return False
        return True
    except Exception:
        traceback.print_exc()
        for window in app.get_windows():
            if isinstance(window, CommandWindow):
                window.stop_command()
            window.destroy()
        app.quit()
        return False


GLib.timeout_add(150, tick)
app.run([sys.argv[0]])
sys.exit(0 if state["ok"] else 1)
