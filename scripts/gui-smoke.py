#!/usr/bin/python3
"""Exercise real GTK/VTE with an isolated demo backend; no VPN mutations."""

from pathlib import Path
import sys
import time
import traceback

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from openvpn3_gui.app import Application, MainWindow
from openvpn3_gui.widgets import CommandForm
from gi.repository import Gdk, GLib, Vte

app = Application(demo=True)
app.set_application_id("io.github.openvpn3gui.Smoke")
state = {"step": 0, "started": time.monotonic(), "ok": False}


def terminal_text(terminal):
    if hasattr(terminal, "get_text_format"):
        return terminal.get_text_format(Vte.Format.TEXT) or ""
    return terminal.get_text(None, None)[0] or ""


def poll():
    try:
        if time.monotonic() - state["started"] > 45:
            raise AssertionError("GUI smoke test timed out")
        window = next((w for w in app.get_windows() if isinstance(w, MainWindow)), None)
        if not window or not window.commands or not window.profiles:
            return True
        if state["step"] == 0:
            assert len(window.profile_store) == 3
            # Real widget generation for every command and option.
            for command in window.commands.values():
                window.open_command(command.name)
                form = window.form_holder.get_children()[0]
                assert isinstance(form, CommandForm)
                assert len(form.rows) == len(command.options)
                for row in form.rows:
                    if row.option.argument and not row.option.optional:
                        row.set_value(
                            row.option.choices[0]
                            if row.option.choices
                            else "test value"
                        )
                    else:
                        row.set_value()
                assert len(form.arguments()) == len(command.options) + 1
            window.open_command("session-manage", {"log-level": ""})
            assert "--log-level" in window.form_holder.get_children()[0].arguments()
            window.navigation.select_row(window.navigation.get_row_at_index(0))
            window.profile_tree.get_selection().select_path(0)
            assert window.selected_profile["path"].endswith("demo_persistent")
            window.render_profiles()
            assert window.selected_profile["path"].endswith("demo_persistent")
            window.profile_search.set_text("Home lab")
            window.render_profiles()
            assert len(window.profile_store) == 1
            window.profile_search.set_text("")
            window.render_profiles()
            window.profile_tree.get_selection().select_path(0)
            state["runner"] = window.run_command(
                ["session-start", "--config-path", window.selected_profile["path"]]
            )
            state["step"] = 1
        elif state["step"] in (1, 2, 3):
            runner = state["runner"]
            text = terminal_text(runner.terminal)
            if state["step"] == 1 and "Username:" in text:
                runner.terminal.feed_child(b"demo-user\n")
                state["step"] = 2
            elif state["step"] == 2 and "Password:" in text:
                runner.terminal.feed_child(b"do-not-echo-this\n")
                state["step"] = 3
            elif state["step"] == 3 and not runner.running:
                assert "authentication complete" in text
                assert "do-not-echo-this" not in text
                assert runner.status.get_text() == "Completed successfully"
                runner.destroy()
                state["runner"] = window.run_command(
                    ["log", "--session-path", "/net/openvpn/v3/sessions/demo_session"]
                )
                state["step"] = 4
        elif state["step"] == 4:
            runner = state["runner"]
            text = terminal_text(runner.terminal)
            if "Client connected" in text:
                runner.stop_command()
                state["step"] = 5
        elif state["step"] == 5:
            runner = state["runner"]
            if not runner.running:
                runner.destroy()
                window.present()
                window.profile_tree.get_selection().select_path(0)
                state["step"] = 6
        elif state["step"] == 6:
            if window.refreshing:
                return True
            assert (
                window.selected_profile is not None
            ), "Profile selection was lost after asynchronous refresh"
            assert window.profile_name.get_text() == window.selected_profile["name"]
            assert window.profile_path.get_text() == window.selected_profile["path"]
            assert all(control.get_sensitive() for control in window.profile_buttons)
            # Allow the compositor to present the last selection/detail redraw.
            state["settle"] = state.get("settle", 0) + 1
            if state["settle"] < 5:
                return True
            surface = window.get_window()
            picture = Gdk.pixbuf_get_from_window(
                surface,
                0,
                0,
                window.get_allocated_width(),
                window.get_allocated_height(),
            )
            if picture:
                picture.savev("/tmp/openvpn3-gui-demo.png", "png", [], [])
            print(
                f"PASS: {len(window.commands)} command forms, duplicate identity, filtering, selection retention, VTE authentication, hidden password, live logs, cancellation."
            )
            state["ok"] = True
            window.destroy()
            app.quit()
            return False
        return True
    except Exception:
        traceback.print_exc()
        for w in app.get_windows():
            if hasattr(w, "stop_command"):
                w.stop_command()
            w.destroy()
        app.quit()
        return False


GLib.timeout_add(150, poll)
app.run([sys.argv[0]])
sys.exit(0 if state["ok"] else 1)
