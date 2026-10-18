# Contributing

Improvements to usability, accessibility, compatibility, and test coverage are welcome. Contributions are provided under this project's [MIT license](LICENSE).

## Development setup

Use the system Python so it can find distribution-provided PyGObject and VTE libraries:

```sh
sudo apt install python3-gi python3-cairo python3-gi-cairo gir1.2-gtk-3.0 gir1.2-vte-2.91 \
  adwaita-icon-theme librsvg2-common shared-mime-info fonts-dejavu-core \
  desktop-file-utils shellcheck dpkg-dev xvfb xauth dbus-x11 at-spi2-core
```

Real OpenVPN is optional for demo development. `./openvpn3-gui --demo` never accesses real profiles or services. The installed-CLI coverage test runs when `openvpn3` is available; otherwise it is explicitly skipped.

## Run the checks

```sh
make test
make check
make integration  # optional: creates/removes one temporary profile on local services; no tunnel
```

For a headless environment:

```sh
dbus-run-session -- xvfb-run -a ./scripts/check.sh
```

The suite includes backend regression tests, generated command forms, real GTK/VTE subprocess behavior using a fake VPN, fault injection, actual widget-allocation checks with long names at four window widths, desktop-file validation, ShellCheck, installer staging checks, and package validation. It does not authenticate against a real VPN server or change the host's routes or DNS.

The GitHub Actions check workflow runs these checks on four desktop distribution images plus two headless installation jobs, with read-only repository permissions. Workflow actions are pinned to a commit. Branch pushes and pull requests only run checks; pushing a version tag starts the release workflow described below.

## Architecture

- `openvpn3_gui/backend.py`: CLI discovery, subprocess execution, list parsing, exact session/profile association, private exports, and isolated demo state.
- `openvpn3_gui/app.py`: main GTK screens and action coordination; service reads run in a bounded worker pool.
- `openvpn3_gui/widgets.py`: command forms and VTE terminals for interactive prompts.
- `openvpn3_gui/tui.py`: curses UI, asynchronous reads, and interactive terminal handoff.
- `openvpn3_gui/theme.py`, `appearance.py`, `preferences.py`: palettes, system theme integration, and the local appearance preference.
- `openvpn3_gui/traffic.py`, `traffic_widget.py`: counter validation, bounded sampling, and accessible traffic graphics.
- `openvpn3_gui/data/demo-capabilities.json`: option names/argument shapes for the offline v27.1 demo. Real mode never uses this as a substitute for CLI discovery.
- `scripts/`: test runners, screenshot capture, and package build/inspection.
- `packaging/`: desktop entry, icon, Debian metadata, and manual page.

Commands must remain argument arrays, without a shell. Preserve exact D-Bus identities; do not join profiles and sessions by display name. Keep credentials out of logs, error formatting, test fixtures, and screenshots. Configuration export must remain atomic and owner-readable only.

## Changes and tests

Add focused regression coverage for behavior changes. Test failures, cancellation, and service recovery alongside successful paths. Keep common actions simple; retain advanced options in the CLI forms.

Use four-space Python indentation and the repository `.editorconfig`. Python files are formatted with Black 26.3.1 (88 columns, Python 3.9 target). It is a development tool, not an application dependency:

```sh
black --check openvpn3_gui tests scripts
```

Write pull requests around the problem, resulting behavior, and relevant validation. Avoid real VPN data in commits. The ignore rules are a convenience, not a substitute for reviewing staged files.

## Screenshots and releases

```sh
make screenshots
/usr/bin/python3 scripts/tui-screenshots.py
make deb
/usr/bin/python3 scripts/package-check.py
/usr/bin/python3 scripts/installer-check.py
```

Screenshots are captured from mapped GTK windows using only demo data. Review them after layout changes. The build includes the README, documentation, screenshots, license, desktop files, and demo catalog.

Build artifacts include the GUI and TUI `.deb` files, a standalone `install-openvpn3-gui.sh` helper, and `SHA256SUMS`. Test the helper from a directory without the source checkout. Recipients still need access to OpenVPN's repository for its runtime dependency; do not claim that the package bundles OpenVPN or configures its repository.

`make install` builds as the current user and stages the package outside private home directories before requesting `sudo apt-get install`. Keep APT's sandbox enabled and preserve home-directory permissions. The installer check substitutes APT and sudo to verify staging, cleanup, and failure handling without changing system packages.

For a release, update `openvpn3_gui/__init__.py`, `packaging/control`, `packaging/control-tui`, `packaging/changelog`, both manual versions, and versioned README install commands. The package filename and generated control version come from `__version__`. Builds use a fixed `SOURCE_DATE_EPOCH` by default; release builders can provide a source revision timestamp explicitly.

Before announcing support for a new platform, record what was tested in `docs/TESTING.md`. Real server authentication, routing, DNS, and reconnect behavior need separate end-to-end testing; passing a simulated desktop suite is not equivalent.

### Publish a GitHub release

Submit version changes on a branch and merge through a pull request after the required checks pass. Do not bypass the protection on `main`. After the release commit is merged:

```sh
git switch main
git pull --ff-only origin main
python3 scripts/release-check.py v0.5.0  # replace with the merged version
git tag -a v0.5.0 -m "OpenVPN 3 GUI 0.5.0"
git push origin v0.5.0
```

Use a new `vMAJOR.MINOR.PATCH` tag for each release; never move an already published tag. The workflow rejects tags that disagree with the source version, Debian control file, newest changelog entry, manual, or README package filename. Prerelease tags are not supported yet.

The release workflow runs the full Ubuntu/Debian check matrix, builds and validates the package on Ubuntu 24.04, checks repeat-build reproducibility and installer behavior, and runs Lintian. It then transfers the four release assets to a separate publishing job and checks their SHA-256 sums before uploading them. Only that final job has `contents: write`; it uses GitHub's built-in `GITHUB_TOKEN`, so no personal access token needs to be configured.

The release stays a draft until every asset uploads successfully. Failed checks prevent publication. Rerun failed jobs in GitHub Actions to recover from a temporary failure; a publishing rerun can finish an existing draft but refuses to overwrite a published release. If repository or organization policy restricts Actions or token permissions, an administrator must enable the workflow's declared permissions.

See [GitHub's reusable workflow documentation](https://docs.github.com/en/actions/how-tos/reuse-automations/reuse-workflows) and [release CLI documentation](https://cli.github.com/manual/gh_release_create) for the underlying mechanisms.

### Terminal and split-package checks

`python3 scripts/tui-smoke.py` drives a real PTY without DISPLAY, including terminal restoration, password hiding, log interruption, and Linux-console mode. Unit tests cover exact identities, stale snapshots, safe terminal rendering, and cancelled deletion. No GUI imports belong in the TUI/backend path.

The desktop package bundles all modules and both launchers. The standalone server package bundles only the terminal runtime. They are alternative editions: `Conflicts`/`Replaces` let APT switch editions without file collisions; the desktop package also `Provides` the matching terminal client version. Desktop installation must succeed with just its own `.deb`. Validate each archive independently and test both directions of switching with real APT in disposable containers. See [Debian's package relationship policy](https://www.debian.org/doc/debian-policy/ch-relationships.html#overwriting-files-and-replacing-packages-replaces). The curses lifecycle follows [Python's curses guide](https://docs.python.org/3/howto/curses.html), using `curses.wrapper` for terminal restoration.
