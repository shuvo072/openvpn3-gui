#!/usr/bin/python3
"""Drive the real curses UI through a PTY, without a graphical display or VPN."""

import fcntl
import os
from pathlib import Path
import pty
import select
import signal
import struct
import sys
import termios
import tempfile
import time

ROOT = Path(__file__).resolve().parent.parent
samples = tempfile.TemporaryDirectory(prefix="openvpn3-tui-smoke-")
sample = Path(samples.name) / "terminal-test.ovpn"
sample.write_text("client\ndev tun\nremote vpn.example.invalid 1194\n")
exported = Path(samples.name) / "exported.ovpn"
launcher = os.environ.get("TUI_TEST_LAUNCHER", str(ROOT / "openvpn3-tui"))


def run_scenario(term="xterm-256color"):
    pid, fd = pty.fork()
    if pid == 0:
        os.environ.pop("DISPLAY", None)
        os.environ.pop("WAYLAND_DISPLAY", None)
        os.environ["TERM"] = term
        os.environ["LC_ALL"] = "C.UTF-8"
        os.execv(launcher, [launcher, "--demo"])
    output = bytearray()
    initial = termios.tcgetattr(fd)

    def resize(rows, cols):
        fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
        os.kill(pid, signal.SIGWINCH)

    def read_for(seconds):
        until = time.monotonic() + seconds
        while time.monotonic() < until:
            if select.select([fd], [], [], max(0, until - time.monotonic()))[0]:
                try:
                    chunk = os.read(fd, 65536)
                except OSError:
                    break
                if not chunk:
                    break
                output.extend(chunk)

    def wait(text, timeout=10):
        start = len(output)
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            read_for(0.1)
            if text.encode() in bytes(output[start:]):
                return
        raise AssertionError(
            f"Expected {text!r}; recent terminal output: {bytes(output[-1600:])!r}"
        )

    def send(value):
        os.write(fd, value.encode())

    try:
        resize(30, 110)
        wait("Ready.")
        if term in ("linux", "vt100"):
            send("q")
        else:
            resize(12, 45)
            wait("Resize to at least")
            resize(30, 110)
            wait("MY VPNS")
            send("v")
            wait("Profile and connection details")
            send("q")
            read_for(0.3)
            send("d")
            wait("Type y")
            send("y\n")
            wait("Press Enter to return")
            assert b"Connection statistics:" in output
            send("\n")
            wait("MY VPNS")
            read_for(0.5)
            send("c")
            wait("Type y")
            send("y\n")
            wait("Username:")
            send("demo-user\n")
            wait("Password:")
            send("test-password-not-echoed\n")
            wait("Press Enter to return")
            assert b"test-password-not-echoed" not in output
            send("\n")
            wait("MY VPNS")
            read_for(0.5)
            send("l")
            wait("Type y")
            send("y\n")
            wait("[demo] Connection")
            send("\x03")
            wait("Press Enter to return")
            send("\n")
            wait("MY VPNS")
            read_for(0.5)
            send("x")
            wait("Type DELETE")
            send("\x1b")
            read_for(1.3)
            send("a")
            wait("Advanced tools")
            send("session-stats\n")
            wait("Add option")
            send("\n")
            wait("Choose an option")
            send("path\n")
            wait("A value is required")
            send("q")
            wait("Enter accepts")
            send("/net/openvpn/v3/sessions/demo_session\n")
            wait("Add option")
            send("Run command\n")
            wait("Type y")
            send("y\n")
            wait("Press Enter to return")
            send("\n")
            wait("MY VPNS")
            read_for(0.5)
            send("i")
            wait("Path to .ovpn")
            send(str(sample) + "\n")
            wait("Profile name")
            send("\x15Terminal profile\n")
            wait("Remember after restart")
            send("\n")
            wait("Type y")
            send("y\n")
            wait("Press Enter to return")
            send("\n")
            wait("MY VPNS")
            read_for(0.5)
            send("/")
            wait("Find a VPN")
            send("Terminal profile\n")
            read_for(0.5)
            send("e")
            wait("Export to .ovpn")
            send(str(exported) + "\n")
            wait("Profile exported")
            assert exported.stat().st_mode & 0o777 == 0o600
            assert "vpn.example.invalid" in exported.read_text()
            send("n")
            wait("New profile name")
            send("\x15Renamed terminal\n")
            wait("Type y")
            send("y\n")
            wait("Press Enter to return")
            send("\n")
            wait("MY VPNS")
            read_for(0.5)
            send("/")
            wait("Find a VPN")
            send("\x15Renamed terminal\n")
            read_for(0.5)
            send("x")
            wait("Type DELETE")
            send("DELETE\n")
            wait("Press Enter to return")
            send("\n")
            wait("MY VPNS")
            read_for(0.5)
            send("q")
        read_for(1)
        exit_deadline = time.monotonic() + 8
        while time.monotonic() < exit_deadline:
            finished, status = os.waitpid(pid, os.WNOHANG)
            if finished:
                assert os.waitstatus_to_exitcode(status) == 0, bytes(output[-2000:])
                after = termios.tcgetattr(fd)
                for flag in (termios.ECHO, termios.ICANON):
                    assert bool(after[3] & flag) == bool(
                        initial[3] & flag
                    ), "Terminal state was not restored"
                assert b"Traceback" not in output
                return
            read_for(0.1)
            # PTY EOF can precede waitpid readiness; avoid a tight retry loop.
            time.sleep(0.02)
        raise AssertionError(f"TUI did not exit: {bytes(output[-2000:])!r}")
    finally:
        try:
            os.kill(pid, signal.SIGKILL)
            os.waitpid(pid, 0)
        except ProcessLookupError:
            pass
        os.close(fd)


run_scenario()
run_scenario("linux")
run_scenario("vt100")
samples.cleanup()
print(
    "PASS: headless PTY dashboard, resizing, details, disconnect, hidden-password authentication, log cancellation, delete cancellation, advanced command execution, import/rename/delete/private export, Linux console, monochrome terminal, terminal restoration."
)
