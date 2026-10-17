import json
import re
import subprocess
import os
import tempfile
import unittest
from unittest.mock import patch

from openvpn3_gui.backend import (
    Backend,
    CLIError,
    Option,
    build_arguments,
    command_preview,
    parse_commands,
    parse_options,
    parse_profiles,
    parse_sessions,
    save_private_file,
    group_connections,
    connection_status,
    demo_commands,
)


class ParsingTests(unittest.TestCase):
    def test_offline_demo_has_a_complete_catalog(self):
        with patch("shutil.which", return_value=None):
            backend = Backend(demo=True)
            commands = backend.discover()
            self.assertEqual(len(commands), 16)
            self.assertEqual(sum(len(c.options) for c in commands), 115)
            self.assertEqual(len(backend.profiles()), 3)
            self.assertIn("openvpn3_gui.demo_cli", backend.argv(["session-start"]))

    def test_real_mode_reports_missing_cli(self):
        with patch("shutil.which", return_value=None):
            with self.assertRaisesRegex(CLIError, "not installed"):
                Backend()

    def test_action_timeout_does_not_leak_arguments(self):
        backend = Backend(demo=True)
        secret = "private-password-do-not-print"
        with patch(
            "subprocess.run",
            side_effect=subprocess.TimeoutExpired(
                ["openvpn3", "--proxy-password=" + secret], 30
            ),
        ):
            with self.assertRaises(CLIError) as caught:
                backend.execute(["config-manage", "--proxy-password=" + secret])
        self.assertNotIn(secret, str(caught.exception))
        self.assertIn("outcome is uncertain", str(caught.exception))

    def test_read_timeout_and_nonzero_output(self):
        with patch("shutil.which", return_value="/usr/bin/openvpn3"):
            backend = Backend()
        with patch(
            "subprocess.run", side_effect=subprocess.TimeoutExpired(["openvpn3"], 20)
        ):
            with self.assertRaisesRegex(CLIError, "20 seconds"):
                backend.read("sessions-list")
        with patch(
            "subprocess.run",
            return_value=subprocess.CompletedProcess([], 1, "", "Permission denied"),
        ):
            with self.assertRaisesRegex(CLIError, "Permission denied"):
                backend.read("sessions-list")

    def test_invalid_json_is_reported_clearly(self):
        with self.assertRaisesRegex(CLIError, "invalid profile list"):
            parse_profiles("broken JSON")

    def test_export_failure_preserves_existing_file_and_cleans_temporary(self):
        with tempfile.TemporaryDirectory() as directory:
            filename = os.path.join(directory, "test.ovpn")
            with open(filename, "w") as stream:
                stream.write("original")
            with patch("os.replace", side_effect=OSError("disk unavailable")):
                with self.assertRaises(OSError):
                    save_private_file(filename, "new content")
            with open(filename) as stream:
                self.assertEqual(stream.read(), "original")
            self.assertEqual(os.listdir(directory), ["test.ovpn"])

    def test_export_replaces_symlink_without_writing_through_it(self):
        with tempfile.TemporaryDirectory() as directory:
            target = os.path.join(directory, "unrelated")
            with open(target, "w") as stream:
                stream.write("keep")
            destination = os.path.join(directory, "export.ovpn")
            os.symlink(target, destination)
            save_private_file(destination, "config")
            with open(target) as stream:
                self.assertEqual(stream.read(), "keep")
            self.assertFalse(os.path.islink(destination))

    def test_demo_import_rename_delete_preserves_identity(self):
        backend = Backend(demo=True)
        backend.command_succeeded(
            ["config-import", "--name=New profile", "--config", "/demo.ovpn"]
        )
        imported = next(p for p in backend.profiles() if p["name"] == "New profile")
        backend.command_succeeded(
            ["config-manage", "--path", imported["path"], "--rename=Changed"]
        )
        self.assertTrue(
            any(
                p["path"] == imported["path"] and p["name"] == "Changed"
                for p in backend.profiles()
            )
        )
        backend.command_succeeded(["config-remove", "--path", imported["path"]])
        self.assertEqual(len(backend.profiles()), 3)

    def test_sessions_join_by_path_across_duplicate_names_and_renames(self):
        profiles = [{"path": "a", "name": "Office"}, {"path": "b", "name": "Office"}]
        sessions = [
            {"path": "s1", "name": "Old name", "config_path": "b"},
            {"path": "s2", "name": "Office", "config_path": "b"},
            {"path": "s3", "name": "Office"},
        ]
        groups = group_connections(profiles, sessions)
        self.assertEqual(groups["a"], [])
        self.assertEqual([s["path"] for s in groups["b"]], ["s1", "s2"])
        self.assertEqual(groups["s3"], [sessions[2]])

    def test_deleted_profile_session_stays_accessible(self):
        session = {"path": "s", "config_path": "deleted", "name": "Office"}
        self.assertEqual(group_connections([], [session]), {"s": [session]})

    def test_friendly_status_distinguishes_connected_and_disconnected(self):
        self.assertEqual(connection_status([]), "Disconnected")
        for status, expected in (
            ("Client connected", "Connected"),
            ("Client disconnected", "Disconnected"),
            ("Client paused", "Paused"),
            ("Client reconnecting", "Reconnecting…"),
        ):
            self.assertEqual(connection_status([{"status": status}]), expected)

    def test_action_failure_preserves_diagnostics(self):
        backend = Backend(demo=True)
        with patch(
            "subprocess.run",
            return_value=subprocess.CompletedProcess([], 1, "Access denied"),
        ) as run:
            with self.assertRaisesRegex(CLIError, "Access denied"):
                backend.execute(["session-manage", "--disconnect"])
            self.assertEqual(run.call_args.kwargs["stdin"], subprocess.DEVNULL)
            self.assertNotIn("shell", run.call_args.kwargs)

    def test_export_is_private_even_when_overwriting_public_file(self):
        with tempfile.TemporaryDirectory() as directory:
            filename = os.path.join(directory, "test.ovpn")
            with open(filename, "w") as stream:
                stream.write("old data")
            os.chmod(filename, 0o644)
            save_private_file(filename, "private key data")
            self.assertEqual(os.stat(filename).st_mode & 0o777, 0o600)
            with open(filename) as stream:
                self.assertEqual(stream.read(), "private key data")
            self.assertEqual(os.listdir(directory), ["test.ovpn"])

    def test_options_include_alias_multiline_and_optional_argument(self):
        options = parse_options("""openvpn3: test
   -o | --path CONFIG-PATH     - Configuration identifier
        --config-path CONFIG-PATH
                               - Alias for --path
        --log-level[=LEVEL]    - View/set level
        --ipv6 <yes|no|default>
                               - IPv6 policy
   -s | --show                 - Show settings
   -G | --grant <UID | username>
                               - Grant access
""")
        self.assertEqual(
            [o.name for o in options],
            ["path", "config-path", "log-level", "ipv6", "show", "grant"],
        )
        self.assertEqual(options[1].description, "Alias for --path")
        self.assertTrue(options[2].optional)
        self.assertEqual(options[2].argument, "LEVEL")
        self.assertEqual(options[3].choices, ["yes", "no", "default"])
        self.assertFalse(options[4].argument)
        self.assertFalse(options[5].choices)

    def test_duplicate_profiles_keep_exact_identity(self):
        first = "/net/openvpn/v3/configuration/a"
        second = "/net/openvpn/v3/configuration/b"
        records = parse_profiles(
            json.dumps({first: {"name": "Office"}, second: {"name": "Office"}})
        )
        self.assertEqual(len(records), 2)
        self.assertEqual({p["path"] for p in records}, {first, second})

    def test_profile_data_cannot_override_identity(self):
        path = "/net/openvpn/v3/configuration/a"
        self.assertEqual(
            parse_profiles(json.dumps({path: {"name": "Office", "path": "wrong"}}))[0][
                "path"
            ],
            path,
        )

    def test_reject_unexpected_profile_schema(self):
        for data in ([], {"profiles": []}, {"wrong": {}}):
            with self.assertRaises(CLIError):
                parse_profiles(json.dumps(data))

    def test_sessions_preserve_multiline_details(self):
        sessions = parse_sessions(
            """-----------------------------------------------------------------------------
        Path: /net/openvpn/v3/sessions/one
     Created: Thu Oct 15 08:10:00 2026                  PID: 123
       Owner: someone                              Device: tun0
 Config name: Office VPN
      Status: Connection, Client connected
-----------------------------------------------------------------------------
        Path: /net/openvpn/v3/sessions/two
 Config name: Office VPN
      Status: Connection, Client paused
-----------------------------------------------------------------------------
"""
        )
        self.assertEqual(len(sessions), 2)
        self.assertEqual(sessions[0]["name"], "Office VPN")
        self.assertEqual(sessions[1]["status"], "Connection, Client paused")
        self.assertIn("PID: 123", sessions[0]["details"][1])
        self.assertEqual(parse_sessions("No sessions available\n"), [])
        with self.assertRaises(CLIError):
            parse_sessions("new unsupported format")

    def test_argument_values_are_literal_and_repeatable(self):
        payload = "$(touch /tmp/unsafe); `id` name with spaces"
        arguments = build_arguments(
            "config-import",
            [
                (Option("name", "NAME"), payload),
                (Option("tag", "TAG"), "one"),
                (Option("tag", "TAG"), "two"),
                (Option("persistent"), ""),
            ],
        )
        self.assertEqual(
            arguments,
            [
                "config-import",
                "--name=" + payload,
                "--tag=one",
                "--tag=two",
                "--persistent",
            ],
        )

    def test_optional_value_and_empty_required_value(self):
        option = Option("log-level", "LEVEL", optional=True)
        self.assertEqual(
            build_arguments("session-manage", [(option, "")]),
            ["session-manage", "--log-level"],
        )
        self.assertEqual(
            build_arguments("session-manage", [(option, "4")]),
            ["session-manage", "--log-level=4"],
        )
        with self.assertRaises(ValueError):
            build_arguments("config-import", [(Option("config", "FILE"), "")])

    def test_redaction_for_both_argument_styles(self):
        preview = command_preview(
            [
                "config-manage",
                "--proxy-password=private",
                "--proxy-password",
                "another-secret",
            ]
        )
        self.assertNotIn("private", preview)
        self.assertNotIn("another-secret", preview)

    def test_demo_never_reads_services_or_launches_openvpn(self):
        with patch("shutil.which", return_value="/usr/bin/openvpn3"):
            backend = Backend(demo=True)
        with patch.object(
            backend, "read", side_effect=AssertionError("service access")
        ):
            self.assertEqual(len(backend.profiles()), 3)
            self.assertEqual(len(backend.sessions()), 1)
            self.assertIn("openvpn3_gui.demo_cli", backend.argv(["session-start"]))


class InstalledCLITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.backend = Backend()
        except CLIError as error:
            raise unittest.SkipTest(str(error))

    def test_every_installed_command_and_option_is_exposed(self):
        commands = self.backend.discover()
        names = set(self.backend.read("shell-completion", "--list-commands").split())
        # Upstream completion deliberately excludes the two CLI helper commands.
        self.assertEqual(
            {command.name for command in commands}, names | {"help", "shell-completion"}
        )
        for command in commands:
            with self.subTest(command=command.name):
                # Independently extract every option at the start of a help row.
                expected = set(
                    re.findall(
                        r"^\s+(?:-\w\s*\|\s*)?--([a-z0-9-]+)", command.help, re.M
                    )
                )
                self.assertEqual({option.name for option in command.options}, expected)
                if command.name in names:
                    # v27's completion helper emits valid flags with a nonzero exit status.
                    completed = subprocess.run(
                        [
                            self.backend.executable,
                            "shell-completion",
                            "--list-options",
                            command.name,
                        ],
                        capture_output=True,
                        text=True,
                        timeout=10,
                    ).stdout
                    flags = {
                        flag[2:].rstrip("=")
                        for flag in completed.split()
                        if flag.startswith("--")
                    }
                    self.assertEqual({option.name for option in command.options}, flags)
                for option in command.options:
                    self.assertTrue(
                        option.description,
                        f"Missing description for {command.name} --{option.name}",
                    )
                    self.assertNotIn(" - ", option.argument)


if __name__ == "__main__":
    unittest.main()
