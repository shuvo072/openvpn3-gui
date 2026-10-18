"""Terminal identity, safe rendering, stale reads and destructive actions."""

from concurrent.futures import Future
import curses
import unittest
import subprocess
import sys
import threading
import time
from unittest.mock import patch

from openvpn3_gui.backend import Backend, CLIError, cancellable_read
from openvpn3_gui.tui import TerminalApp, clip, networks, safe_text


class Screen:
    def __init__(self, keys=()):
        self.keys = iter(keys)
        self.output = []

    def keypad(self, value):
        pass

    def timeout(self, value):
        pass

    def getmaxyx(self):
        return (24, 80)

    def erase(self):
        pass

    def refresh(self):
        pass

    def getch(self):
        return next(self.keys)

    def get_wch(self):
        return next(self.keys)

    def addstr(self, y, x, value, attr=0):
        self.output.append(value)


class TerminalTests(unittest.TestCase):
    def app(self, keys=()):
        with patch("curses.curs_set"), patch("curses.has_colors", return_value=False):
            app = TerminalApp(Screen(keys), Backend(demo=True))
        self.addCleanup(lambda: app.executor.shutdown(wait=True, cancel_futures=True))
        app.rows = networks(app.backend.profiles(), app.backend.sessions())
        app.filter_rows()
        return app

    def test_duplicate_profiles_and_multiple_orphan_sessions(self):
        profiles = [
            {"path": "/p/one", "name": "same"},
            {"path": "/p/two", "name": "same"},
        ]
        sessions = [
            {
                "path": "/s/one",
                "name": "old name",
                "config_path": "/p/one",
                "status": "Connected",
            },
            {
                "path": "/s/two",
                "name": "same",
                "config_path": "/p/one",
                "status": "Paused",
            },
            {
                "path": "/s/orphan",
                "name": "same",
                "config_path": "/missing",
                "status": "Connected",
            },
        ]
        rows = networks(profiles, sessions)
        self.assertEqual(
            [r.key for r in rows],
            [
                ("/p/one", "/s/one"),
                ("/p/one", "/s/two"),
                ("/p/two", ""),
                ("", "/s/orphan"),
            ],
        )
        self.assertEqual(rows[0].name, "same")
        self.assertIsNone(rows[-1].profile)

    def test_terminal_controls_and_unicode_width(self):
        self.assertNotIn("\x1b", safe_text("VPN\x1b[2J\x07\n\u202e"))
        self.assertEqual(clip("東京 VPN", 5), "東京 ")
        self.assertEqual(clip("e\u0301x", 1), "e\u0301")

    def test_filter_preserves_exact_selection(self):
        app = self.app()
        key = app.rows[1].key
        app.filter_rows(key)
        self.assertEqual(app.selected.key, key)
        app.query = "no such VPN"
        app.filter_rows(key)
        self.assertIsNone(app.selected)

    def test_secret_prompt_does_not_render_secret(self):
        app = self.app("private-password\n")
        self.assertEqual(app.prompt("Password", secret=True), "private-password")
        self.assertNotIn("private-password", "".join(app.screen.output))
        self.assertIn("*****", "".join(app.screen.output))

    def test_exact_action_targets_and_stale_controls(self):
        app = self.app()
        with patch.object(app, "run_command") as run:
            app.action(ord("d"))
            run.assert_called_once_with(
                [
                    "session-manage",
                    "--path",
                    "/net/openvpn/v3/sessions/demo_session",
                    "--disconnect",
                ]
            )
            run.reset_mock()
            app.session_error = "offline"
            app.action(ord("d"))
            run.assert_not_called()

    def test_delete_cancel_never_starts_process(self):
        app = self.app()
        with (
            patch.object(app, "prompt", return_value="y"),
            patch("subprocess.run") as run,
        ):
            app.run_command(["config-remove", "--path", "/exact/profile"])
            run.assert_not_called()
        self.assertEqual(app.message, "Cancelled.")

    def test_stale_refresh_does_not_restore_removed_sessions(self):
        app = self.app()
        app.next_refresh = app.next_traffic = float("inf")
        future = Future()
        future.set_result(([], [], [], [None, None, None]))
        app.snapshot = (0, future)
        app.epoch = 1
        original = app.rows[:]
        app.service_jobs()
        self.assertEqual(app.rows, original)

    def test_service_failure_clears_sessions(self):
        app = self.app()
        app.next_refresh = app.next_traffic = float("inf")
        future = Future()
        future.set_result((app.backend.profiles(), [], [], [None, "offline", None]))
        app.snapshot = (0, future)
        app.service_jobs()
        self.assertEqual(app.session_error, "offline")
        self.assertTrue(all(row.session is None for row in app.rows))


class ReadCancellationTests(unittest.TestCase):
    def test_cancel_reaps_a_stalled_read(self):
        stopped = threading.Event()
        timer = threading.Timer(0.25, stopped.set)
        started = time.monotonic()
        timer.start()
        try:
            with self.assertRaisesRegex(CLIError, "Client closed"):
                cancellable_read(
                    [sys.executable, "-c", "import time; time.sleep(30)"], stopped
                )
        finally:
            timer.cancel()
        self.assertLess(time.monotonic() - started, 3)

    def test_read_completion_and_timeout(self):
        stopped = threading.Event()
        result = cancellable_read([sys.executable, "-c", "print('ready')"], stopped)
        self.assertEqual(result.stdout, "ready\n")
        self.assertEqual(result.returncode, 0)
        with self.assertRaises(subprocess.TimeoutExpired):
            cancellable_read(
                [sys.executable, "-c", "import time; time.sleep(30)"],
                stopped,
                timeout=0.1,
            )
