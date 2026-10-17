"""CLI discovery and data handling. No GTK, shell, credentials, or root required."""

from dataclasses import dataclass, field
import json
import os
import re
import shlex
import shutil
import subprocess
import tempfile
from pathlib import Path


class CLIError(RuntimeError):
    pass


def save_private_file(filename, content):
    """Atomically export a configuration with owner-only access, including overwrites."""
    filename = os.path.abspath(filename)
    fd, temporary = tempfile.mkstemp(
        prefix=".openvpn3-export-", dir=os.path.dirname(filename)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, filename)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


@dataclass
class Option:
    name: str
    argument: str = ""
    description: str = ""
    optional: bool = False
    short: str = ""

    @property
    def choices(self):
        value = self.argument.strip("<>")
        if "|" in value and " " not in value:
            return value.split("|")
        return []


@dataclass
class Command:
    name: str
    description: str
    help: str
    options: list = field(default_factory=list)


def parse_commands(output):
    return [
        (m[1], m[2])
        for line in output.splitlines()
        if (m := re.match(r"^\s{2,}([a-z][a-z0-9-]*)\s+-\s+(.+)$", line))
    ]


def parse_options(output):
    options = []
    for line in output.splitlines():
        match = re.match(r"^\s+(?:-([A-Za-z0-9])\s*\|\s*)?--([a-z0-9-]+)(.*)$", line)
        if match:
            short, name, tail = match.groups()
            parts = re.split(r"\s+-\s+", tail, maxsplit=1)
            argument = parts[0].strip()
            optional = argument.startswith("[=") and argument.endswith("]")
            if optional:
                argument = argument[2:-1]
            options.append(
                Option(
                    name,
                    argument,
                    parts[1].strip() if len(parts) > 1 else "",
                    optional,
                    short or "",
                )
            )
        elif options and line.strip().startswith("- "):
            options[-1].description = line.strip()[2:]
    return options


def build_arguments(command, values):
    """values is an ordered list of (Option, value); duplicates are intentional."""
    args = [command]
    for option, value in values:
        if not option.argument:
            args.append("--" + option.name)
        elif option.optional:
            args.append("--" + option.name + ("=" + value if value else ""))
        elif not value:
            raise ValueError(f"--{option.name} requires a value.")
        else:
            # Equals preserves values beginning with '-' as values, not options.
            args.append(f"--{option.name}={value}")
    return args


def command_preview(arguments):
    redacted = []
    hide_next = False
    for argument in arguments:
        if hide_next:
            redacted.append("••••••")
            hide_next = False
        elif re.search(r"password|secret|token", argument.split("=", 1)[0], re.I):
            if "=" in argument:
                redacted.append(argument.split("=", 1)[0] + "=••••••")
            else:
                redacted.append(argument)
                hide_next = True
        else:
            redacted.append(argument)
    return shlex.join(["openvpn3", *redacted])


def parse_profiles(output):
    try:
        data = json.loads(output)
    except json.JSONDecodeError as error:
        raise CLIError(
            "OpenVPN returned an invalid profile list. Use Refresh to retry."
        ) from error
    if not isinstance(data, dict):
        raise CLIError(
            "Unexpected profile list format; open All CLI commands → configs-list to inspect it."
        )
    profiles = []
    for path, properties in data.items():
        if not path.startswith("/net/openvpn/v3/configuration/") or not isinstance(
            properties, dict
        ):
            raise CLIError("Unexpected configuration identifier in profile list.")
        profiles.append(
            {**properties, "path": path, "name": str(properties.get("name", path))}
        )
    return sorted(profiles, key=lambda item: (item["name"].casefold(), item["path"]))


def parse_sessions(output):
    sessions = []
    current = None
    for line in output.splitlines():
        match = re.match(r"\s*Path:\s*(/net/openvpn/v3/sessions/\S+)", line)
        if match:
            current = {
                "path": match[1],
                "name": "VPN session",
                "status": "Unknown",
                "details": [],
            }
            sessions.append(current)
        if (
            current is not None
            and line.strip()
            and not re.match(r"^[-=]+$", line.strip())
        ):
            current["details"].append(line.strip())
            for label, key in (
                ("Config name", "name"),
                ("Status", "status"),
                ("Owner", "owner"),
                ("Device", "device"),
            ):
                field_match = re.match(r"\s*" + label + r":\s*(.*)", line)
                if field_match:
                    current[key] = field_match[1]
    if not sessions and output.strip() and "No sessions" not in output:
        raise CLIError(
            "Could not read the session list. Open All CLI commands → sessions-list for the raw output."
        )
    return sessions


def group_connections(profiles, sessions):
    """Join only on immutable configuration paths, never on ambiguous names."""
    groups = {profile["path"]: [] for profile in profiles}
    for session in sessions:
        key = session.get("config_path")
        groups.setdefault(key if key in groups else session["path"], []).append(session)
    return groups


def connection_status(sessions):
    if not sessions:
        return "Disconnected"
    if len(sessions) > 1:
        return f"{len(sessions)} sessions"
    status = sessions[0].get("status", "Unknown")
    lowered = status.lower()
    for needle, title in (
        ("failed", "Connection failed"),
        ("error", "Connection error"),
        ("disconnected", "Disconnected"),
        ("paused", "Paused"),
        ("reconnecting", "Reconnecting…"),
        ("connected", "Connected"),
        ("connecting", "Connecting…"),
        ("auth", "Authentication needed"),
    ):
        if needle in lowered:
            return title
    return status


def demo_commands():
    """Offline demo catalog of API names; real mode always discovers the installed CLI."""
    data = json.loads(
        (Path(__file__).parent / "data" / "demo-capabilities.json").read_text()
    )
    descriptions = {
        "help": "Browse available commands",
        "version": "Show the installed version",
        "shell-completion": "Inspect shell completion metadata",
        "config-import": "Import a VPN profile",
        "config-manage": "Configure a saved profile",
        "config-acl": "Manage profile access",
        "config-dump": "View an imported configuration",
        "config-remove": "Remove an imported profile",
        "configs-list": "List saved profiles",
        "session-start": "Connect a VPN profile",
        "session-manage": "Control a VPN connection",
        "session-auth": "Complete authentication",
        "session-acl": "Manage connection access",
        "session-stats": "View connection statistics",
        "sessions-list": "List VPN connections",
        "log": "Watch connection logs",
    }
    commands = []
    for item in data:
        options = [
            Option(**o, description="CLI option: " + o["name"].replace("-", " "))
            for o in item["options"]
        ]
        help_text = "Offline demo · OpenVPN 3 v27.1 option shapes\n\n" + "\n".join(
            "    --"
            + o.name
            + ("[=" + o.argument + "]" if o.optional else " " + o.argument)
            + "  - "
            + o.description
            for o in options
        )
        commands.append(
            Command(item["name"], descriptions[item["name"]], help_text, options)
        )
    return commands


class Backend:
    def __init__(self, demo=False):
        self.demo = demo
        self._demo_sessions = None
        self._demo_profiles = None
        self.executable = shutil.which("openvpn3")
        if not self.executable and not demo:
            raise CLIError(
                "OpenVPN 3 Linux is not installed. Install openvpn3 using the official OpenVPN repository, then reopen this app."
            )

    def read(self, *arguments):
        try:
            result = subprocess.run(
                [self.executable, *arguments],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=20,
                env={**os.environ, "LC_ALL": "C"},
            )
        except subprocess.TimeoutExpired as error:
            raise CLIError(
                "OpenVPN did not respond within 20 seconds. Check the service and try Refresh."
            ) from error
        except OSError as error:
            raise CLIError(str(error)) from error
        if result.returncode:
            raise CLIError(
                (result.stderr or result.stdout).strip()
                or f"Command exited with {result.returncode}"
            )
        return result.stdout

    def discover(self):
        if self.demo and not self.executable:
            return demo_commands()
        commands = []
        for name, description in parse_commands(self.read("--help")):
            output = (
                self.read(name, "--help") if name != "help" else self.read("--help")
            )
            commands.append(Command(name, description, output, parse_options(output)))
        if not commands:
            raise CLIError(
                "Could not discover CLI commands. Check that openvpn3 --help works."
            )
        return commands

    def profiles(self):
        if self.demo:
            if self._demo_profiles is None:
                self._demo_profiles = [
                    {
                        "name": "Office VPN",
                        "path": "/net/openvpn/v3/configuration/demo_persistent",
                        "lastused": "Today, 08:21",
                        "imported": "Today, 08:16",
                        "valid": True,
                        "acl": {"owner": "demo", "public_access": False},
                        "use_count": 3,
                    },
                    {
                        "name": "Office VPN",
                        "path": "/net/openvpn/v3/configuration/demo_temporary",
                        "lastused": "Never",
                        "imported": "Today, 08:10",
                        "valid": True,
                        "acl": {"owner": "demo", "public_access": False},
                        "use_count": 0,
                    },
                    {
                        "name": "Home lab",
                        "path": "/net/openvpn/v3/configuration/demo_lab",
                        "lastused": "Yesterday",
                        "valid": True,
                        "acl": {"owner": "demo"},
                    },
                ]
            return [dict(profile) for profile in self._demo_profiles]
        return parse_profiles(self.read("configs-list", "--json"))

    def sessions(self):
        if self.demo:
            if self._demo_sessions is None:
                self._demo_sessions = [
                    {
                        "name": "Office VPN",
                        "path": "/net/openvpn/v3/sessions/demo_session",
                        "config_path": "/net/openvpn/v3/configuration/demo_persistent",
                        "status": "Connection, Client connected",
                        "details": [
                            "Device: tun0",
                            "Owner: demo",
                            "Status: Connection, Client connected",
                        ],
                    }
                ]
            return [dict(session) for session in self._demo_sessions]
        sessions = parse_sessions(self.read("sessions-list"))
        if sessions:
            # Read-only D-Bus property documented by OpenVPN. Missing permissions
            # leave a standalone session row, rather than guessing by its name.
            from gi.repository import Gio, GLib

            try:
                bus = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
            except GLib.Error:
                return sessions
            for session in sessions:
                try:
                    result = bus.call_sync(
                        "net.openvpn.v3.sessions",
                        session["path"],
                        "org.freedesktop.DBus.Properties",
                        "Get",
                        GLib.Variant(
                            "(ss)", ("net.openvpn.v3.sessions", "config_path")
                        ),
                        GLib.VariantType.new("(v)"),
                        Gio.DBusCallFlags.NONE,
                        1000,
                        None,
                    )
                    session["config_path"] = result.unpack()[0]
                except GLib.Error:
                    pass
        return sessions

    def execute(self, arguments):
        """Run a noninteractive action, capturing diagnostics in memory only."""
        try:
            result = subprocess.run(
                self.argv(arguments),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
                cwd=os.path.dirname(os.path.dirname(__file__)),
                env={**os.environ, "LC_ALL": "C"},
            )
        except subprocess.TimeoutExpired as error:
            raise CLIError(
                "The action timed out after 30 seconds. Its outcome is uncertain; refresh the connection status before retrying."
            ) from error
        except OSError as error:
            raise CLIError(str(error)) from error
        if result.returncode:
            raise CLIError(
                result.stdout.strip() or f"Command exited with {result.returncode}"
            )
        return result.stdout

    def command_succeeded(self, arguments):
        """Keep the isolated demo responsive to the same actions as real sessions."""
        if not self.demo:
            return
        self.sessions()
        values = {}
        for index, arg in enumerate(arguments[1:], 1):
            if arg.startswith("--"):
                flag, equal, value = arg.partition("=")
                values[flag] = (
                    value
                    if equal
                    else (
                        arguments[index + 1]
                        if index + 1 < len(arguments)
                        and not arguments[index + 1].startswith("--")
                        else ""
                    )
                )
        if arguments[0] == "config-import":
            self.profiles()
            name = values.get("--name") or values.get("--config", "Imported profile")
            self._demo_profiles.append(
                {
                    "name": name,
                    "path": "/net/openvpn/v3/configuration/demo_" + os.urandom(4).hex(),
                    "lastused": "Never",
                    "imported": "Today",
                    "valid": True,
                    "acl": {"owner": "demo"},
                }
            )
        elif arguments[0] in {"config-manage", "config-remove"}:
            self.profiles()
            path = values.get("--path", values.get("--config-path"))
            if arguments[0] == "config-remove":
                self._demo_profiles = [
                    p for p in self._demo_profiles if p["path"] != path
                ]
            elif "--rename" in values:
                for profile in self._demo_profiles:
                    if profile["path"] == path:
                        profile["name"] = values["--rename"]
        elif arguments[0] == "session-start" and "--config-path" in values:
            path = values["--config-path"]
            profile = next((p for p in self.profiles() if p["path"] == path), None)
            if profile:
                self._demo_sessions.append(
                    {
                        "name": profile["name"],
                        "config_path": path,
                        "path": "/net/openvpn/v3/sessions/demo_" + os.urandom(4).hex(),
                        "status": "Connection, Client connected",
                        "details": ["Demo connection"],
                    }
                )
        elif arguments[0] == "session-manage":
            path = values.get("--path", values.get("--session-path"))
            if "--disconnect" in values:
                self._demo_sessions = [
                    s for s in self._demo_sessions if s["path"] != path
                ]
            else:
                for session in self._demo_sessions:
                    if session["path"] == path:
                        if "--pause" in values:
                            session["status"] = "Connection, Client paused"
                        elif "--resume" in values or "--restart" in values:
                            session["status"] = "Connection, Client connected"

    def argv(self, arguments):
        if self.demo:
            return ["/usr/bin/python3", "-m", "openvpn3_gui.demo_cli", *arguments]
        return [self.executable, *arguments]

    def dump_profile(self, path):
        if self.demo:
            return "# Demonstration profile — contains no keys or credentials\nclient\ndev tun\nproto udp\nremote vpn.example.invalid 1194\n"
        return self.read("config-dump", "--path", path)
