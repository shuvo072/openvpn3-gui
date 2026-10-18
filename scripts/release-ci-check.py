#!/usr/bin/python3
"""Require successful main push CI for the exact checked-out release commit."""

import argparse
import json
import os
import re
import subprocess
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class GateError(RuntimeError):
    pass


def release_commit(root="."):
    """HEAD peels annotated tags; main's complete history must be fetched."""
    sha = subprocess.check_output(
        ["git", "rev-parse", "HEAD^{commit}"], cwd=root, text=True
    ).strip()
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", sha, "refs/remotes/origin/main"],
        cwd=root,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise GateError(
            "The tagged commit is not in origin/main, or main's history is missing. "
            "Merge the release through a pull request before tagging."
        )
    return sha


def workflow_runs(repository, sha, token=""):
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise GateError("Set GITHUB_REPOSITORY to owner/repository.")
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise GateError("Expected a full commit SHA.")
    query = urlencode(
        {"branch": "main", "event": "push", "head_sha": sha, "per_page": 100}
    )
    # Do not filter by success: a newer failed/pending run must block release.
    url = f"https://api.github.com/repos/{repository}/actions/workflows/check.yml/runs?{query}"
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "openvpn3-gui-release-gate",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    with urlopen(Request(url, headers=headers), timeout=30) as response:
        payload = json.load(response)
    runs = payload.get("workflow_runs")
    if not isinstance(runs, list):
        raise GateError("GitHub did not return a workflow run list.")
    return runs


def latest_main_run(runs, repository, sha):
    matching = [
        run
        for run in runs
        if run.get("head_sha") == sha
        and run.get("head_branch") == "main"
        and run.get("event") == "push"
        and run.get("path") == ".github/workflows/check.yml"
        and (run.get("head_repository") or {}).get("full_name", "").lower()
        == repository.lower()
    ]
    return max(matching, key=lambda run: run["id"], default=None)


def wait_for_ci(
    fetch,
    repository,
    sha,
    wait_seconds=900,
    clock=time.monotonic,
    sleep=time.sleep,
    report=print,
):
    deadline = clock() + wait_seconds
    while True:
        run = latest_main_run(fetch(), repository, sha)
        if run and run.get("status") == "completed":
            if run.get("conclusion") != "success":
                raise GateError(
                    f"Main CI finished with {run.get('conclusion')!r}: {run.get('html_url')}. "
                    "Fix or rerun that CI before rerunning this release."
                )
            report(f"Verified main push CI for {sha}: {run['html_url']}", flush=True)
            return run
        remaining = deadline - clock()
        if remaining <= 0:
            raise GateError(
                f"No completed successful main push CI for {sha} within {wait_seconds}s. "
                "Wait for main CI to pass, then rerun the release workflow's failed jobs."
            )
        status = run.get("status") if run else "not created yet"
        report(f"Waiting for main CI ({status}) for {sha}…", flush=True)
        sleep(min(15, remaining))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wait-seconds", type=int, default=900)
    args = parser.parse_args()
    if args.wait_seconds < 0:
        parser.error("--wait-seconds must be nonnegative")
    try:
        sha = release_commit()
        repository = os.environ.get("GITHUB_REPOSITORY", "")
        token = os.environ.get("GITHUB_TOKEN", "")
        wait_for_ci(
            lambda: workflow_runs(repository, sha, token),
            repository,
            sha,
            args.wait_seconds,
        )
    except (
        GateError,
        OSError,
        ValueError,
        KeyError,
        subprocess.SubprocessError,
    ) as error:
        parser.exit(1, f"Release blocked: {error}\n")


if __name__ == "__main__":
    main()
