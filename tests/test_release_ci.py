"""Release gate must never substitute another commit's or branch's CI."""

import io
from pathlib import Path
import runpy
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parent.parent
module = runpy.run_path(str(ROOT / "scripts/release-ci-check.py"))
GateError = module["GateError"]
SHA = "a" * 40
REPO = "owner/project"


def run(**changes):
    return {
        "id": 1,
        "head_sha": SHA,
        "head_branch": "main",
        "event": "push",
        "path": ".github/workflows/check.yml",
        "head_repository": {"full_name": REPO},
        "status": "completed",
        "conclusion": "success",
        "html_url": "https://github.com/owner/project/actions/runs/1",
        **changes,
    }


class ReleaseCIGateTests(unittest.TestCase):
    def wait(self, fetch, **kwargs):
        return module["wait_for_ci"](fetch, REPO, SHA, report=Mock(), **kwargs)

    def test_exact_main_push_success(self):
        self.assertEqual(self.wait(lambda: [run()])["id"], 1)
        for field, value in [
            ("head_sha", "b" * 40),
            ("head_branch", "feature"),
            ("event", "pull_request"),
            ("event", "workflow_dispatch"),
            ("path", ".github/workflows/release.yml"),
            ("head_repository", {"full_name": "fork/project"}),
        ]:
            with self.subTest(field=field, value=value), self.assertRaises(GateError):
                self.wait(lambda: [run(**{field: value})], wait_seconds=0)

    def test_all_unsuccessful_conclusions_block(self):
        for conclusion in [
            "failure",
            "cancelled",
            "timed_out",
            "skipped",
            "neutral",
            "action_required",
            None,
        ]:
            with self.subTest(conclusion=conclusion), self.assertRaises(GateError):
                self.wait(lambda: [run(conclusion=conclusion)])

    def test_latest_run_cannot_fall_back_to_old_success(self):
        with self.assertRaises(GateError):
            self.wait(lambda: [run(id=2, conclusion="failure"), run()])
        with self.assertRaises(GateError):
            self.wait(
                lambda: [run(), run(id=2, status="in_progress", conclusion=None)],
                wait_seconds=0,
            )

    def test_waits_for_missing_and_pending_run(self):
        fetch = Mock(
            side_effect=[
                [],
                [run(status="queued", conclusion=None)],
                [run(status="in_progress", conclusion=None)],
                [run()],
            ]
        )
        sleep = Mock()
        self.assertEqual(self.wait(fetch, clock=lambda: 0, sleep=sleep)["id"], 1)
        self.assertEqual(sleep.call_count, 3)

    def test_timeout_and_api_error_block(self):
        with self.assertRaises(GateError):
            self.wait(lambda: [], clock=Mock(side_effect=[0, 901]), sleep=Mock())
        error = HTTPError("https://api.github.com", 403, "Forbidden", {}, None)
        self.addCleanup(error.close)
        with self.assertRaises(HTTPError):
            self.wait(Mock(side_effect=error))

    def test_rerun_of_same_id_must_finish_successfully(self):
        fetch = Mock(
            side_effect=[
                [run(run_attempt=2, status="in_progress", conclusion=None)],
                [run(run_attempt=2)],
            ]
        )
        self.assertEqual(
            self.wait(fetch, clock=lambda: 0, sleep=Mock())["run_attempt"], 2
        )

    def test_api_query_does_not_hide_failures(self):
        fetch = module["workflow_runs"]
        response = Mock()
        response.__enter__ = Mock(return_value=io.StringIO('{"workflow_runs": []}'))
        response.__exit__ = Mock(return_value=False)
        with patch.dict(fetch.__globals__, {"urlopen": Mock(return_value=response)}):
            self.assertEqual(fetch(REPO, SHA, "test-token"), [])
            request = fetch.__globals__["urlopen"].call_args.args[0]
            self.assertIn("branch=main", request.full_url)
            self.assertIn("event=push", request.full_url)
            self.assertIn("head_sha=" + SHA, request.full_url)
            self.assertNotIn("status=", request.full_url)
            self.assertEqual(request.get_header("Authorization"), "Bearer test-token")

    def test_annotated_tag_ancestor_and_feature_commit(self):
        with tempfile.TemporaryDirectory() as directory:

            def git(*args):
                return subprocess.check_output(
                    ["git", *args], cwd=directory, text=True, stderr=subprocess.DEVNULL
                ).strip()

            git("init", "-b", "main")
            git("config", "user.name", "Test")
            git("config", "user.email", "test@example.invalid")
            git("commit", "--allow-empty", "-m", "base")
            first = git("rev-parse", "HEAD")
            git("tag", "-a", "v1.0.0", "-m", "release")
            git("commit", "--allow-empty", "-m", "later main commit")
            git("update-ref", "refs/remotes/origin/main", "HEAD")
            git("checkout", "v1.0.0")
            self.assertEqual(module["release_commit"](directory), first)
            git("checkout", "-b", "feature")
            git("commit", "--allow-empty", "-m", "not on main")
            with self.assertRaises(GateError):
                module["release_commit"](directory)
