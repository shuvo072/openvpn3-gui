# Verification report

Version: **0.6.0**

Date: **2026-10-18**

Architecture tested: **x86-64**

## Verified environments

| Environment | Python | Mode | Result |
| --- | --- | --- | --- |
| Ubuntu 26.04.1 desktop | 3.14 | Backend tests and installed OpenVPN 3 v27.1 capability checks | Passed |
| Ubuntu 22.04 container | 3.10 | Xvfb/D-Bus session, offline demo, backend tests, package checks | Passed |
| Ubuntu 24.04 container | 3.12 | Xvfb/D-Bus session, offline demo, backend tests, package checks | Passed |
| Debian 12 container | 3.11 | Xvfb/D-Bus session, offline demo, backend tests, package checks | Passed |
| Debian 13 container | 3.13 | Xvfb/D-Bus session, offline demo, backend tests, package checks | Passed |

The local suite has **56 tests**: 23 backend/capability checks, 6 traffic-model tests, 4 appearance/preference tests, 10 terminal-model/cancellation tests, 5 release-metadata tests, and 8 release-CI-gate tests. Containers run 55 tests and explicitly skip the installed-CLI test because OpenVPN is absent. Each container also runs a real PTY terminal suite, six GTK/VTE/tray suites, and the package checks below. The four-container matrix was rerun for 0.6.0. Host desktop flows and the real-service profile lifecycle were additionally verified for 0.3.0.

These container runs validate the application with each distribution's Python/GTK/VTE packages. They do not establish a real VPN or prove that OpenVPN's repository supports every OS/CPU combination. The table records local checks; current hosted runs are available in [GitHub Actions](https://github.com/shuvo072/openvpn3-gui/actions). The release workflow requires successful main push CI for the exact tagged commit instead of rerunning the full matrix. It still builds and verifies release packages before publishing.

## Coverage

- All 16 commands and 115 options exposed by the locally installed OpenVPN 3 v27.1, independently compared with its completion metadata.
- Every generated option form, optional argument handling, literal arguments, duplicate/repeated options, aliases, and secret redaction.
- Profile/session identity with duplicate names, renamed profiles, multiple sessions, and missing/deleted profiles.
- Real GTK/VTE username/password interaction using a fake CLI; password text is not echoed.
- Connect/resume popup auto-close, quiet pause/disconnect, retained disconnect statistics, read-only output retention, failed actions, live logs, and cancellation.
- CLI discovery failure and retry; session-service failure and recovery; disabled stale controls; empty lists and unmatched searches.
- Import/rename/delete simulation, cancellation of deletion, and preservation of the deletion target while selection changes.
- Private export permissions, replacement of existing files, symlink handling, cleanup after a failed write, and preservation of the previous file on failure.
- Subprocess timeout reporting without leaking secret arguments.
- Compact window layout, missing-CLI setup, and offline demo operation without an OpenVPN installation.
- Actual widget allocations for long paths, unbroken names, and multilingual names at 960, 1120, 1240, and 1600 logical pixels wide; no horizontal page overflow; visible action buttons; expanded metadata; full-name tooltips; and repeated transitions between stacked and side-by-side layouts.
- Earlier 0.3.2 Ubuntu 24.04 layout passes with `GDK_DPI_SCALE=1.25`, `GDK_DPI_SCALE=1.5`, and `GDK_SCALE=2`. The 2× pass also exercises the 960 × 680 minimum window size.
- Python compilation, ShellCheck, and desktop-entry validation.
- 0.4.0 light/dark dashboards, hidden sidebar, import dialog, advanced forms, disconnect details, and long-name layouts captured from mapped GTK windows using demo data and visually reviewed. The packaged app icon is compared with the project SVG.
- System appearance through a simulated Settings portal on an isolated D-Bus session, including the older nested-variant Read reply and live SettingChanged signals; explicit light/dark overrides, safe preference defaults, and saved preference permissions.
- Exact-session statistics arguments, malformed/missing counters, integer limits, elapsed-time rate calculation, counter resets, gaps, bounded history, and byte-unit formatting.
- Live GTK counters, non-overlapping polls, selection changes during a read, disconnect before a response, unavailable statistics, recovery, and a fresh rate baseline after errors. Solid/dashed chart lines distinguish directions in addition to color.
- Extracted package launcher, version/help output, offline catalog, MIT license, file permissions, manifest checksums, exclusion of VPN/key files, and repeat-build SHA-256 equality.
- Installer staging from private directories and filenames containing spaces; readable package-copy permissions without changing source permissions; sudo/root invocation; failure/cancellation exit status; cleanup; invalid-input rejection. These regression checks substitute APT and sudo and do not install system packages.

The standalone installation helper was also exercised without the source checkout with real APT in disposable Ubuntu 22.04 and Debian 13 containers: fresh 0.3.1 installation, upgrade from 0.3.0, and package removal. Installation from a private directory completed without the `_apt` unsandboxed-download notice, preserved source permissions, and removed staging files. The launcher avoids runtime bytecode writes so even root `--version` checks do not leave cache files behind after removal. An empty `openvpn3` dependency fixture kept live VPN services out of these installation-only checks; this does not validate OpenVPN repository availability or its installation scripts.

## Terminal and single-file package verification

The terminal smoke suite drives the actual application through a pseudoterminal with DISPLAY and WAYLAND_DISPLAY unset. It covers resizing below the minimum and back, profile details, disconnect, password authentication without echo, Ctrl+C during live logs, cancelled deletion, advanced option entry and execution, import, rename, deletion, private export, and clean terminal restoration. It also starts/exits with Linux-console and monochrome VT100 terminal capabilities. Model tests cover duplicate profiles, multiple/orphan sessions, Unicode widths, control-character filtering, stale snapshots, service failures, secret-field masking, and prompt termination of stalled read subprocesses on exit.

Fresh TUI-only installs were exercised with real APT in disposable Ubuntu 24.04 and Debian 13 containers, explicitly verifying that GTK and Cairo are absent. The installed `openvpn3-tui` passes the PTY suite; removal leaves no launchers or shared backend file. Desktop installation from just the GUI `.deb`, switching desktop → server → desktop, installed terminal interactions, file ownership, and removal were verified on Ubuntu 22.04/24.04 and Debian 12/13. Upgrades from GUI 0.4.0 and the earlier development 0.5.0 split packages were verified in Ubuntu 24.04. The desktop package owns both launchers and the shared backend after installation; no separate TUI package remains installed. These tests use an empty `openvpn3` dependency fixture; they do not test OpenVPN's installation scripts or a real server connection.

Both alternative packages are checked independently for repeat-build equality, file permissions, manifests, installed launchers, and runtime data. The desktop archive must include the entire terminal runtime with identical files, provide its TUI version, and declare the package relationships needed to switch editions. A release check rejects any separate TUI dependency. Installer tests cover one-file installation for either edition, renamed package paths, rejection of multiple packages, cleanup, and APT-readable staging from private directories. Lintian reports no errors or warnings for either package.

The GitHub Actions workflow includes application and single-file installation/switching checks on the four desktop distributions plus fresh headless install jobs on Ubuntu 24.04 and Debian 13. The release workflow checks the existing main CI result, then builds/verifies and publishes both packages, the helper, and checksums.

## System tray verification

The tray smoke test runs the real Ayatana library on an isolated D-Bus session with a simulated StatusNotifier watcher/host. It verifies indicator registration and exported icon/menu properties; connected, connecting, paused, disconnected and error states; exact session/profile IDs; menu activation; stale, busy and unavailable-service guards; visible authentication; quiet disconnect; and hidden-window error recovery.

Lifecycle checks cover closing into the tray, reopening through application activation without a second main window, a host becoming unavailable, the watcher disappearing/restarting, missing tray libraries, disabling close-to-tray, explicit quit, and retaining established demo sessions when quitting. Preference tests verify that appearance and close behavior persist independently with owner-only permissions. The menu screenshot uses GTK widgets and demo data; actual panels render menus in their own style.

The desktop package includes the Ayatana dependency, tray module, and all five original status icons; package checks exclude these from the standalone terminal package. The GTK/VTE/tray suite and real single-file installation/switching/removal tests passed on Ubuntu 22.04/24.04 and Debian 12/13. Real GNOME, KDE, XEmbed-only panels, compositor restarts, and shell extension versions were not exercised; host recovery here is a simulated D-Bus test. No real VPN was connected or disconnected by these tests.

## Release CI gate verification

Eight unit tests cover matching the exact workflow/repository/branch/event/commit, rejecting unsuccessful conclusions, preferring a newer failed or pending run over an older success, waiting for missing/pending runs, timeout and API failures, rerun attempts, and API filters. A temporary Git repository tests annotated tags, older commits in main history, and rejection of an unmerged feature commit. API failures block publication; no fallback bypasses the gate. Workflow syntax is checked with actionlint. These local checks do not publish a release or exercise a hosted token's permissions.

## Real-service check

`make integration` was run against the local OpenVPN 3 services for 0.3.0. It creates one randomly named, nonpersistent profile pointing to loopback, checks its exact ID, renames it, adds/removes a tag, reads its exported configuration and ACL, and removes it in a `finally` block. The later layout, packaging, and theme updates do not change this backend behavior.

**No tunnel is started.** It does not use or modify an existing VPN profile, change routes/DNS, or require server credentials. This check is opt-in and is not part of the offline CI suite.

## Limits

A real VPN-server connection was not exercised. The TUI was tested through a local PTY and installed-container PTY, not a remote SSH transport or hypervisor console. Live traffic is validated against simulated counters and the upstream JSON schema; a live-server throughput comparison was not performed. System appearance is tested with a simulated portal, not a full GNOME/KDE desktop settings matrix. Server-specific password/OTP/web authentication, certificate validation, routes, DNS behavior, reconnect after network changes, and DCO require end-to-end testing with a suitable test VPN. The simulated password flow validates the terminal integration, not every server authentication scheme.

There has been no independent security audit, comprehensive screen-reader audit, ARM validation, or full desktop-environment matrix. The host desktop and Xvfb exercise different display paths, but they do not cover every compositor/theme combination.

Older VTE versions emit a deprecation warning when the test harness reads terminal text through the legacy inspection API. That warning is limited to the harness; the application does not use that API during normal operation.

## Reproduce

```sh
make test
make check
make integration   # opt-in; requires working local OpenVPN 3 services
```

Headless checks:

```sh
dbus-run-session -- xvfb-run -a ./scripts/check.sh
```

See [CONTRIBUTING.md](../CONTRIBUTING.md) for packages to install. Screenshot generation is separate (`make screenshots`) and always uses isolated demo data.

Package reproducibility is checked for repeated builds with the same source, timestamp, and build environment. Different distribution compression/toolchain versions can produce different `.deb` bytes; cross-environment bit-for-bit equality is not claimed.
