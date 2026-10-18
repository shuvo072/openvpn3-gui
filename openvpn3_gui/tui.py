"""Curses client for local consoles and SSH. No GTK or display dependency."""

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import curses
from dataclasses import dataclass
import locale
import os
from pathlib import Path
import re
import subprocess
import sys
import textwrap
import time
import threading
import unicodedata

from . import __version__
from .backend import (
    Backend,
    CLIError,
    build_arguments,
    command_preview,
    connection_status,
    group_connections,
    save_private_file,
)
from .traffic import TrafficHistory, format_bytes


def safe_text(value):
    """Never interpret service-provided terminal controls or bidi formatting."""
    return "".join(
        " " if unicodedata.category(c).startswith("C") else c for c in str(value)
    )


def clip(value, width):
    result, cells = "", 0
    for char in safe_text(value):
        size = (
            0
            if unicodedata.combining(char)
            else (2 if unicodedata.east_asian_width(char) in "WF" else 1)
        )
        if cells + size > width:
            break
        result += char
        cells += size
    return result


@dataclass
class Network:
    profile: object
    session: object

    @property
    def key(self):
        return (
            self.profile["path"] if self.profile else "",
            self.session["path"] if self.session else "",
        )

    @property
    def name(self):
        return (self.profile or self.session)["name"]

    @property
    def status(self):
        return connection_status([self.session] if self.session else [])


def networks(profiles, sessions):
    groups = group_connections(profiles, sessions)
    rows = []
    for profile in profiles:
        rows.extend(
            Network(profile, s) for s in groups.pop(profile["path"], []) or [None]
        )
    for group in groups.values():
        rows.extend(Network(None, s) for s in group)
    return rows


def sparkline(history, index, width=30):
    """ASCII works on Linux virtual consoles as well as Unicode terminals."""
    if not history or not history.samples:
        return " " * width
    end = time.monotonic()
    buckets = [None] * width
    for when, rates in history.samples:
        slot = int((when - end + 60) / 60 * width)
        if rates is not None and 0 <= slot < width:
            buckets[slot] = max(buckets[slot] or 0, rates[index])
    peak = max((value for value in buckets if value is not None), default=0)
    levels = "._-=+*#@"
    return "".join(
        " " if v is None else levels[min(7, int(v / peak * 7)) if peak else 0]
        for v in buckets
    )


class TerminalApp:
    def __init__(self, screen, backend):
        self.screen, self.backend = screen, backend
        self.backend.cancel_reads = threading.Event()
        self.executor = ThreadPoolExecutor(
            max_workers=2, thread_name_prefix="openvpn3-tui"
        )
        self.snapshot = self.traffic_job = None
        self.epoch = 0
        self.rows, self.visible, self.commands = [], [], []
        self.index, self.query = 0, ""
        self.profile_error = self.session_error = None
        self.histories = {}
        self.traffic_error = None
        self.message = "Loading OpenVPN profiles and sessions..."
        self.next_refresh = self.next_traffic = 0
        self.running = True
        self.screen.keypad(True)
        self.screen.timeout(150)
        try:
            curses.curs_set(0)
        except curses.error:
            pass
        self.accent = curses.A_BOLD
        if curses.has_colors():
            curses.start_color()
            try:
                curses.use_default_colors()
                curses.init_pair(1, curses.COLOR_CYAN, -1)
                self.accent |= curses.color_pair(1)
            except curses.error:
                pass

    def put(self, y, x, text, attr=0, width=None):
        height, cols = self.screen.getmaxyx()
        if 0 <= y < height and 0 <= x < cols - 1:
            try:
                self.screen.addstr(
                    y, x, clip(text, min(width or cols, cols - x - 1)), attr
                )
            except curses.error:
                pass

    @property
    def selected(self):
        return self.visible[self.index] if self.visible else None

    def filter_rows(self, key=None):
        self.visible = [
            r
            for r in self.rows
            if self.query.casefold() in (r.name + " " + " ".join(r.key)).casefold()
        ]
        self.index = next(
            (i for i, r in enumerate(self.visible) if r.key == key),
            min(self.index, max(0, len(self.visible) - 1)),
        )

    def request_refresh(self):
        self.next_refresh = 0

    def service_jobs(self):
        now = time.monotonic()
        if self.snapshot and self.snapshot[1].done():
            epoch, future = self.snapshot
            self.snapshot = None
            if epoch == self.epoch:
                profiles, sessions, commands, errors = future.result()
                key = self.selected.key if self.selected else None
                self.rows = networks(profiles, sessions)
                self.filter_rows(key)
                self.commands = commands or self.commands
                self.profile_error, self.session_error = errors[:2]
                self.message = (
                    " | ".join(e for e in errors if e)
                    or "Ready. Profiles refresh every 5 seconds. Traffic every 2 seconds."
                )
                paths = {s["path"] for s in sessions}
                self.histories = {p: h for p, h in self.histories.items() if p in paths}
        if self.snapshot is None and now >= self.next_refresh:
            self.next_refresh = now + 5
            known_commands = list(self.commands)

            def read_snapshot():
                results, errors = [], []
                for method in (
                    self.backend.profiles,
                    self.backend.sessions,
                    lambda: known_commands or self.backend.discover(),
                ):
                    try:
                        results.append(method())
                        errors.append(None)
                    except Exception as error:
                        results.append([])
                        errors.append(str(error))
                return (*results, errors)

            self.snapshot = (self.epoch, self.executor.submit(read_snapshot))
        if self.traffic_job and self.traffic_job[2].done():
            epoch, path, future = self.traffic_job
            self.traffic_job = None
            if (
                epoch == self.epoch
                and self.selected
                and self.selected.session
                and self.selected.session["path"] == path
            ):
                history = self.histories.setdefault(path, TrafficHistory())
                try:
                    history.add(now, future.result())
                    self.traffic_error = None
                except Exception as error:
                    history.interrupt()
                    self.traffic_error = str(error)
        row = self.selected
        if (
            self.traffic_job is None
            and now >= self.next_traffic
            and row
            and row.session
            and row.status == "Connected"
            and not self.session_error
        ):
            self.next_traffic = now + 2
            path = row.session["path"]
            self.traffic_job = (
                self.epoch,
                path,
                self.executor.submit(self.backend.session_stats, path),
            )

    def draw(self):
        self.screen.erase()
        h, w = self.screen.getmaxyx()
        self.put(
            0,
            2,
            f"OpenVPN 3 TUI  {__version__}"
            + ("  [DEMO - no VPN changes]" if self.backend.demo else ""),
            self.accent,
        )
        if h < 24 or w < 80:
            self.put(2, 1, "Resize to at least 80 columns x 24 rows. Q quits.")
            self.screen.refresh()
            return
        left = max(30, w * 2 // 5)
        self.put(
            2,
            2,
            "MY VPNS" + (f"  / {self.query}" if self.query else ""),
            self.accent,
            left - 3,
        )
        self.put(2, left + 2, "CONNECTION", self.accent)
        visible_count = h - 10
        start = max(0, self.index - visible_count + 1)
        names = Counter(row.name for row in self.visible)
        for pos, row in enumerate(self.visible[start : start + visible_count], start):
            selected = pos == self.index
            name = row.name
            if names[name] > 1:
                suffix = (row.session or row.profile)["path"].rsplit("/", 1)[-1][-7:]
                name = clip(name, left - 15) + " #" + suffix
            self.put(
                4 + pos - start,
                2,
                ("> " if selected else "  ") + name,
                curses.A_REVERSE if selected else 0,
                left - 3,
            )
        if not self.visible:
            self.put(
                4,
                2,
                "No matches." if self.query else "No VPNs. Press I to import.",
                width=left - 3,
            )
        for y in range(3, h - 6):
            self.put(y, left, "|", curses.A_DIM)
        row = self.selected
        if row:
            x, width = left + 2, w - left - 4
            self.put(4, x, row.name, curses.A_BOLD, width)
            self.put(
                5,
                x,
                "Status: " + ("Unavailable" if self.session_error else row.status),
                width=width,
            )
            self.put(
                6,
                x,
                "Session: "
                + (row.session["path"].rsplit("/", 1)[-1] if row.session else "None"),
                width=width,
            )
            self.put(
                7,
                x,
                "Profile: "
                + (
                    row.profile["path"].rsplit("/", 1)[-1]
                    if row.profile
                    else "Unavailable"
                ),
                width=width,
            )
            history = self.histories.get(row.session["path"]) if row.session else None
            live = (
                history
                and history.updated
                and now_fresh(history.updated)
                and row.status == "Connected"
                and not self.traffic_error
            )
            rates = history.rates if live else None
            totals = history.totals if history else None
            self.put(9, x, "TRAFFIC  (transport bytes)", self.accent, width)
            for i, title in enumerate(("Received", "Sent")):
                self.put(
                    10 + i * 2,
                    x,
                    title
                    + ": "
                    + format_bytes(rates[i] if rates else None, True)
                    + " | "
                    + format_bytes(totals[i] if totals else None)
                    + " total",
                    width=width,
                )
                self.put(
                    11 + i * 2,
                    x,
                    sparkline(history, i, min(width, 30)),
                    self.accent,
                    width,
                )
            note = (
                "Traffic unavailable; retrying."
                if self.traffic_error
                else (
                    "Last 60 seconds; sampled while selected."
                    if live
                    else "Connect to collect traffic; V shows details."
                )
            )
            self.put(15, x, note, curses.A_DIM, width)
        self.put(h - 5, 2, "[! details] " + self.message)
        self.put(
            h - 3,
            2,
            "Enter/C connect  D disconnect  P pause/resume  I import  N rename  X delete",
        )
        self.put(
            h - 2,
            2,
            "A tools  L logs  S stats  E export  V details  / find  R reload  ? help  Q quit",
        )
        self.screen.refresh()

    def prompt(self, title, initial="", secret=False):
        value = initial
        while True:
            self.draw()
            h, w = self.screen.getmaxyx()
            self.put(h - 4, 1, " " * (w - 2))
            self.put(h - 4, 2, title + " (Enter accepts; Esc cancels)", self.accent)
            self.put(h - 3, 1, " " * (w - 2))
            shown = "*" * len(value) if secret else safe_text(value)
            self.put(h - 3, 2, "> " + shown[-max(1, w - 6) :])
            self.screen.refresh()
            try:
                key = self.screen.get_wch()
            except curses.error:
                continue
            if key in ("\n", "\r", curses.KEY_ENTER):
                return value
            if key == "\x1b":
                return None
            if key in ("\b", "\x7f", curses.KEY_BACKSPACE):
                value = value[:-1]
            elif key == "\x15":
                value = ""
            elif isinstance(key, str) and key.isprintable():
                value += key

    def view(self, title, content):
        offset = 0
        while True:
            self.screen.erase()
            h, w = self.screen.getmaxyx()
            lines = [
                part
                for line in content.splitlines()
                for part in (textwrap.wrap(safe_text(line), max(1, w - 4)) or [""])
            ]
            self.put(0, 2, title, self.accent)
            offset = min(offset, max(0, len(lines) - max(1, h - 4)))
            for i, line in enumerate(lines[offset : offset + max(1, h - 4)]):
                self.put(i + 2, 2, line)
            self.put(h - 1, 1, "Up/Down or PgUp/PgDn scroll | Q / Esc closes")
            self.screen.refresh()
            key = self.screen.getch()
            if key in (ord("q"), ord("Q"), 27):
                return
            offset = max(
                0,
                offset
                + {
                    curses.KEY_DOWN: 1,
                    curses.KEY_UP: -1,
                    curses.KEY_NPAGE: max(1, h - 4),
                    curses.KEY_PPAGE: -max(1, h - 4),
                }.get(key, 0),
            )

    def choose(self, title, items):
        """Searchable picker; returns the original item index."""
        query, index = "", 0
        while True:
            found = [
                (i, text)
                for i, text in enumerate(items)
                if query.casefold() in text.casefold()
            ]
            index = min(index, max(0, len(found) - 1))
            self.screen.erase()
            h, w = self.screen.getmaxyx()
            self.put(0, 2, title, self.accent)
            self.put(1, 2, "Filter: " + query)
            count = max(1, h - 5)
            start = max(0, index - count + 1)
            for pos, (_, text) in enumerate(found[start : start + count], start):
                self.put(
                    3 + pos - start, 2, text, curses.A_REVERSE if pos == index else 0
                )
            self.put(
                h - 1, 1, "Type to filter | Arrows select | Enter chooses | Esc cancels"
            )
            self.screen.refresh()
            try:
                key = self.screen.get_wch()
            except curses.error:
                continue
            if key == "\x1b":
                return None
            if key in ("\n", "\r", curses.KEY_ENTER) and found:
                return found[index][0]
            if key == curses.KEY_UP:
                index = max(0, index - 1)
            elif key == curses.KEY_DOWN:
                index = min(max(0, len(found) - 1), index + 1)
            elif key in ("\b", "\x7f", curses.KEY_BACKSPACE):
                query = query[:-1]
                index = 0
            elif isinstance(key, str) and key.isprintable():
                query += key
                index = 0

    def run_command(self, arguments):
        flags = {arg.split("=", 1)[0] for arg in arguments[1:]}
        destructive = arguments[0] == "config-remove" or "--seal" in flags
        self.message = command_preview(arguments)
        expected = (
            "DELETE"
            if arguments[0] == "config-remove"
            else ("SEAL" if "--seal" in flags else "y")
        )
        response = self.prompt(
            f"Type {expected} to "
            + ("confirm irreversible change" if destructive else "run command")
        )
        if response != expected:
            self.message = "Cancelled."
            return
        self.epoch += 1  # Discard reads started before the action.
        curses.def_prog_mode()
        curses.endwin()
        success = False
        try:
            print("\n" + safe_text(command_preview(arguments)), flush=True)
            print(
                "OpenVPN owns this terminal until it finishes. Ctrl+C stops the command.\n",
                flush=True,
            )
            result = subprocess.run(
                self.backend.argv(arguments),
                cwd=Path(__file__).resolve().parent.parent,
                check=False,
            )
            success = result.returncode == 0
            print(f"\nCommand exited with status {result.returncode}.", flush=True)
            if success:
                self.backend.command_succeeded(arguments)
        except KeyboardInterrupt:
            print("\nCommand interrupted. Refresh to check its outcome.", flush=True)
        except OSError as error:
            print("\n" + safe_text(error), flush=True)
        finally:
            try:
                input("Press Enter to return to My VPNs...")
            except (KeyboardInterrupt, EOFError):
                pass
            curses.reset_prog_mode()
            self.screen.keypad(True)
            self.screen.timeout(150)
            self.screen.clear()
        self.message = (
            "Command completed."
            if success
            else "Command stopped or failed. Check refreshed status."
        )
        self.traffic_error = None
        self.histories.clear()
        self.session_error = "Refreshing after command"
        self.request_refresh()

    def advanced(self):
        if not self.commands:
            self.message = "CLI options are loading or unavailable. Press R to retry."
            return
        chosen = self.choose(
            "Advanced tools - all installed CLI commands",
            [c.name + " - " + c.description for c in self.commands],
        )
        if chosen is None:
            return
        command, values = self.commands[chosen], []
        while True:
            preview = command_preview(build_arguments(command.name, values))
            choice = self.choose(
                preview,
                [
                    "Add option (repeatable)",
                    "Remove an enabled option",
                    "Read command help",
                    "Run command",
                    "Back to My VPNs",
                ],
            )
            if choice is None or choice == 4:
                return
            if choice == 0:
                selected = self.choose(
                    "Choose an option",
                    [
                        "--" + o.name + " " + o.argument + " - " + o.description
                        for o in command.options
                    ],
                )
                if selected is None:
                    continue
                option = command.options[selected]
                value = ""
                if option.argument:
                    self.view(
                        "--" + option.name,
                        option.description
                        + "\nValue: "
                        + option.argument
                        + (
                            "\nOptional: leave empty to use the flag alone."
                            if option.optional
                            else "\nA value is required."
                        ),
                    )
                    value = self.prompt(
                        "--" + option.name,
                        secret=bool(
                            re.search("password|secret|token", option.name, re.I)
                        ),
                    )
                    if value is None:
                        continue
                try:
                    build_arguments(command.name, [(option, value)])
                except ValueError as error:
                    self.view("Invalid value", str(error))
                    continue
                values.append((option, value))
            elif choice == 1:
                selected = self.choose(
                    "Remove option",
                    [
                        command_preview(build_arguments(command.name, [v]))
                        for v in values
                    ],
                )
                if selected is not None:
                    values.pop(selected)
            elif choice == 2:
                self.view(command.name, command.help)
            elif choice == 3:
                self.run_command(build_arguments(command.name, values))
                return

    def import_profile(self):
        filename = self.prompt("Path to .ovpn file")
        if not filename:
            return
        path = Path(filename).expanduser().absolute()
        if not path.is_file():
            self.message = "That file does not exist."
            return
        name = self.prompt("Profile name (Ctrl+U clears)", path.stem)
        if not name:
            return
        if any(r.profile and r.profile["name"] == name for r in self.rows):
            self.message = "That name already exists. Choose a unique name."
            return
        persistent = self.prompt("Remember after restart? y/n", "y")
        if persistent is None:
            return
        if persistent.lower() not in ("y", "n"):
            self.message = "Enter y or n."
            return
        args = ["config-import", "--config", str(path), "--name=" + name]
        if persistent.lower() == "y":
            args.append("--persistent")
        self.run_command(args)

    def export_profile(self, row):
        filename = self.prompt("Export to .ovpn file (may contain private keys)")
        if not filename:
            return
        path = Path(filename).expanduser().absolute()
        if (
            path.exists()
            and self.prompt("Overwrite existing file? Type OVERWRITE") != "OVERWRITE"
        ):
            self.message = "Export cancelled."
            return
        # Export runs off the curses thread too; keep the UI cancellable while reading.
        future = self.executor.submit(self.backend.dump_profile, row.profile["path"])
        self.message = "Reading profile for export. Esc cancels."
        while not future.done():
            self.draw()
            if self.screen.getch() == 27:
                future.cancel()
                self.message = "Export cancelled."
                return
        try:
            save_private_file(path, future.result())
            self.message = "Profile exported with owner-only permissions."
        except (OSError, CLIError) as error:
            self.message = str(error)

    def action(self, key):
        if key == curses.KEY_ENTER:
            key = 10
        row = self.selected
        if key in (ord("q"), ord("Q")):
            self.running = False
        elif key == ord("!"):
            self.view("Latest notification", self.message)
        elif key == ord("?"):
            self.view(
                "Help - OpenVPN 3 Linux client",
                "Use arrows to select a profile or session. Multiple sessions have separate rows.\n\nEnter/C connect; D disconnect; P pause/resume; I import; N rename; X delete; E export; V full identifiers; S raw statistics; L live logs; A all CLI options. / searches, R refreshes, and ! shows the full notification.\n\nCommands ask for confirmation and temporarily use the normal terminal for passwords, MFA, output, and Ctrl+C. Press Enter afterward to return. Do not put credentials in profile names.\n\nClosing the app does not disconnect VPN sessions. Run as the user who owns the profiles; sudo changes the OpenVPN identity.\n\nTraffic uses transport bytes including overhead. Charts show the last 60 seconds sampled while selected, in ASCII intensity levels. Missing samples are gaps.\n\nIndependent community app, not affiliated with OpenVPN Inc. MIT License; see the installed LICENSE file.",
            )
        elif key in (curses.KEY_UP, curses.KEY_DOWN):
            self.index = min(
                max(0, len(self.visible) - 1),
                max(0, self.index + (1 if key == curses.KEY_DOWN else -1)),
            )
            self.traffic_error = None
            self.next_traffic = 0
        elif key == ord("/"):
            query = self.prompt("Find a VPN; empty shows all", self.query)
            if query is not None:
                self.query = query
                self.filter_rows()
        elif key in (ord("r"), ord("R")):
            self.request_refresh()
        elif key in (ord("a"), ord("A")):
            self.advanced()
        elif key in (ord("i"), ord("I")):
            self.import_profile()
        elif row:
            key = chr(key).lower() if 0 <= key < 256 else key
            if key == "v":
                self.view(
                    "Profile and connection details",
                    row.name
                    + "\n"
                    + row.status
                    + "\n\nProfile ID: "
                    + (row.profile["path"] if row.profile else "Unavailable")
                    + "\nSession ID: "
                    + (row.session["path"] if row.session else "None")
                    + "\n"
                    + "\n".join(row.session.get("details", []) if row.session else []),
                )
            elif self.session_error or self.profile_error:
                self.message = "VPN data is unavailable. Refresh before taking action."
            elif key in ("c", "\n", "\r") and row.profile and not row.session:
                self.run_command(
                    ["session-start", "--config-path", row.profile["path"]]
                )
            elif key in ("d", "p", "s", "l") and row.session:
                path = row.session["path"]
                if key in ("s", "l"):
                    self.run_command(
                        [
                            "session-stats" if key == "s" else "log",
                            "--path" if key == "s" else "--session-path",
                            path,
                        ]
                    )
                else:
                    action = (
                        "disconnect"
                        if key == "d"
                        else ("resume" if row.status == "Paused" else "pause")
                    )
                    self.run_command(["session-manage", "--path", path, "--" + action])
            elif key == "x" and row.profile:
                self.run_command(["config-remove", "--path", row.profile["path"]])
            elif key == "n" and row.profile:
                name = self.prompt("New profile name", row.name)
                if name:
                    self.run_command(
                        [
                            "config-manage",
                            "--path",
                            row.profile["path"],
                            "--rename=" + name,
                        ]
                    )
            elif key == "e" and row.profile:
                self.export_profile(row)

    def run(self):
        try:
            while self.running:
                self.service_jobs()
                self.draw()
                key = self.screen.getch()
                if key != -1:
                    self.action(key)
        finally:
            self.backend.cancel_reads.set()
            self.executor.shutdown(wait=False, cancel_futures=True)


def now_fresh(timestamp):
    return time.monotonic() - timestamp <= 8


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Terminal interface for OpenVPN 3 Linux; no graphical display required"
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Use isolated simulated profiles and commands",
    )
    parser.add_argument(
        "--version", action="version", version=f"OpenVPN 3 TUI {__version__}"
    )
    args = parser.parse_args(argv)
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        print(
            "An interactive terminal is required. Run openvpn3-tui in a console, terminal emulator, or SSH session.",
            file=sys.stderr,
        )
        return 2
    if os.environ.get("TERM", "") in ("", "dumb", "unknown"):
        print(
            "A curses-capable terminal is required; check your TERM setting.",
            file=sys.stderr,
        )
        return 2
    try:
        backend = Backend(demo=args.demo)
        locale.setlocale(locale.LC_ALL, "")
        curses.wrapper(lambda screen: TerminalApp(screen, backend).run())
    except (CLIError, curses.error, locale.Error) as error:
        print(safe_text(error), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
