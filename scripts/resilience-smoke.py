#!/usr/bin/python3
"""Fault-injection and identity regression tests. All VPN data is simulated."""

from pathlib import Path
import sys
import time
import traceback
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from openvpn3_gui.app import Application, MainWindow
from openvpn3_gui.backend import Backend, CLIError
from gi.repository import GLib, Gtk

app = Application(demo=True)
app.set_application_id("io.github.openvpn3gui.Resilience")
state = {"step": 0, "start": time.monotonic(), "ok": False, "discover": False}
original_discover = Backend.discover


def discover(backend):
    if not state["discover"]:
        raise CLIError("Simulated CLI failure")
    return original_discover(backend)


def fail_sessions():
    raise CLIError("Simulated session service outage")


def select(window, key):
    for row in window.profile_store:
        if row[3] == key:
            window.profile_tree.get_selection().select_iter(row.iter)
            return
    raise AssertionError("Expected profile/session row is missing")


def tick():
    try:
        if time.monotonic() - state["start"] > 45:
            raise AssertionError(f"Timeout at step {state['step']}")
        if state["step"] == 13:
            setup = next(
                w for w in app.get_windows() if w.get_title() == "Set up OpenVPN 3 GUI"
            )
            content = setup.get_child()
            actions = content.get_children()[-1]
            demo_button = next(
                b for b in actions.get_children() if b.get_label() == "Explore demo"
            )
            with patch("shutil.which", return_value=None):
                demo_button.clicked()
            state["step"] = 14
            return True
        window = next((w for w in app.get_windows() if isinstance(w, MainWindow)), None)
        if not window or window.refreshing or window.busy:
            return True
        step = state["step"]
        if step == 0:
            if window.discovering:
                return True
            assert not window.commands and not window.primary_button.get_sensitive()
            assert "Simulated CLI failure" in window.banner.get_text()
            state["discover"] = True
            window.refresh()
            state["step"] = 1
        elif step == 1:
            if not window.commands:
                return True
            assert window.primary_button.get_sensitive()
            state["sessions"] = window.backend.sessions
            window.backend.sessions = fail_sessions
            window.refresh()
            state["step"] = 2
        elif step == 2:
            assert window.session_error
            assert not window.primary_button.get_sensitive()
            assert window.profile_store[0][1] == "Status unavailable"
            window.backend.sessions = state["sessions"]
            window.refresh()
            state["step"] = 3
        elif step == 3:
            assert not window.session_error and window.primary_button.get_sensitive()
            assert "available again" in window.banner.get_text()
            window.backend._demo_sessions.append(
                {
                    **window.backend.sessions()[0],
                    "path": "/net/openvpn/v3/sessions/second",
                }
            )
            window.refresh()
            state["step"] = 4
        elif step == 4:
            assert window.session_picker.get_visible()
            window.session_picker.set_active_id("/net/openvpn/v3/sessions/second")
            window.render_profiles()
            assert window.selected_session["path"].endswith("/second")
            window.primary_action()
            state["step"] = 5
        elif step == 5:
            assert (
                len(window.sessions) == 1
                and window.primary_button.get_label() == "Disconnect"
            )
            window.backend._demo_sessions.append(
                {
                    "name": "Office VPN",
                    "path": "/net/openvpn/v3/sessions/orphan",
                    "config_path": "/net/openvpn/v3/configuration/deleted",
                    "status": "Client connected",
                    "details": [],
                }
            )
            window.refresh()
            state["step"] = 6
        elif step == 6:
            assert len(window.profile_store) == 4
            select(window, "/net/openvpn/v3/sessions/orphan")
            assert (
                window.selected_profile is None and window.selected_session is not None
            )
            assert all(not button.get_sensitive() for button in window.profile_buttons)
            window.primary_action()
            state["step"] = 7
        elif step == 7:
            assert len(window.sessions) == 1
            select(window, "/net/openvpn/v3/configuration/demo_temporary")
            with patch("openvpn3_gui.app.confirm", return_value=False):
                window.delete_profile()
            assert len(window.backend.profiles()) == 3 and not window.busy

            def confirm_and_change_selection(*_):
                select(window, "/net/openvpn/v3/configuration/demo_persistent")
                return True

            with patch(
                "openvpn3_gui.app.confirm", side_effect=confirm_and_change_selection
            ):
                window.delete_profile()
            state["step"] = 8
        elif step == 8:
            assert len(window.profiles) == 2
            assert all(
                not p["path"].endswith("demo_temporary") for p in window.profiles
            )
            assert any(p["path"].endswith("demo_persistent") for p in window.profiles)
            window.run_command(
                [
                    "config-import",
                    "--config",
                    "/demo/sample.ovpn",
                    "--name=Test import",
                    "--persistent",
                ],
                routine=True,
            )
            state["step"] = 9
        elif step == 9:
            profile = next(p for p in window.profiles if p["name"] == "Test import")
            state["imported"] = profile["path"]
            window.run_command(
                [
                    "config-manage",
                    "--path",
                    profile["path"],
                    "--rename=Renamed profile",
                ],
                routine=True,
            )
            state["step"] = 10
        elif step == 10:
            assert any(
                p["name"] == "Renamed profile" and p["path"] == state["imported"]
                for p in window.profiles
            )
            window.profile_search.set_text("nothing-matches-this")
            window.render_profiles()
            assert (
                not len(window.profile_store)
                and not window.primary_button.get_sensitive()
            )
            assert window.profile_empty.get_text() == "No matching VPNs."
            window.profile_search.set_text("")
            window.backend._demo_profiles = []
            window.backend._demo_sessions = []
            window.refresh()
            state["step"] = 11
        elif step == 11:
            assert (
                not len(window.profile_store) and window.import_button.get_sensitive()
            )
            assert "No VPNs yet" in window.profile_empty.get_text()
            window.resize(960, 680)
            state["step"] = 12
        elif step == 12:
            assert window.workspace.get_orientation() == Gtk.Orientation.VERTICAL
            app.hold()
            window.destroy()
            app.demo = False
            with patch("shutil.which", return_value=None):
                app.activate()
            app.release()
            state["step"] = 13
        elif step == 14:
            if not window.commands:
                return True
            assert window.backend.demo and window.backend.executable is None
            assert len(window.commands) == 16
            print(
                "PASS: discovery retry, service recovery, multiple/orphan sessions, exact deletion, import/rename, empty/search states, compact layout, missing-CLI setup, offline demo."
            )
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


GLib.timeout_add(150, tick)
with patch.object(Backend, "discover", discover):
    app.run([sys.argv[0]])
sys.exit(0 if state["ok"] else 1)
