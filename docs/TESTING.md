# Verification report

Version: **0.4.0**

Date: **2026-10-17**

Architecture tested: **x86-64**

## Verified environments

| Environment | Python | Mode | Result |
| --- | --- | --- | --- |
| Ubuntu 26.04.1 desktop | 3.14 | Backend tests and installed OpenVPN 3 v27.1 capability checks | Passed |
| Ubuntu 22.04 container | 3.10 | Xvfb/D-Bus session, offline demo, backend tests, package checks | Passed |
| Ubuntu 24.04 container | 3.12 | Xvfb/D-Bus session, offline demo, backend tests, package checks | Passed |
| Debian 12 container | 3.11 | Xvfb/D-Bus session, offline demo, backend tests, package checks | Passed |
| Debian 13 container | 3.13 | Xvfb/D-Bus session, offline demo, backend tests, package checks | Passed |

The local suite has **36 tests**: 23 backend/capability checks, 6 traffic-model tests, 3 appearance/preference tests, and 4 release-metadata tests. Containers run 35 tests and explicitly skip the installed-CLI test because OpenVPN is absent. Each container also runs five GTK/VTE suites and the package checks below. The four-container matrix was rerun for 0.4.0. Host desktop flows and the real-service profile lifecycle were additionally verified for 0.3.0.

These container runs validate the application with each distribution's Python/GTK/VTE packages. They do not establish a real VPN or prove that OpenVPN's repository supports every OS/CPU combination. The table records local checks; current hosted runs are available in [GitHub Actions](https://github.com/shuvo072/openvpn3-gui/actions). The release workflow reruns the full matrix before publishing a version tag.

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

## Real-service check

`make integration` was run against the local OpenVPN 3 services for 0.3.0. It creates one randomly named, nonpersistent profile pointing to loopback, checks its exact ID, renames it, adds/removes a tag, reads its exported configuration and ACL, and removes it in a `finally` block. The later layout, packaging, and theme updates do not change this backend behavior.

**No tunnel is started.** It does not use or modify an existing VPN profile, change routes/DNS, or require server credentials. This check is opt-in and is not part of the offline CI suite.

## Limits

A real VPN-server connection was not exercised. Live traffic is validated against simulated counters and the upstream JSON schema; a live-server throughput comparison was not performed. System appearance is tested with a simulated portal, not a full GNOME/KDE desktop settings matrix. Server-specific password/OTP/web authentication, certificate validation, routes, DNS behavior, reconnect after network changes, and DCO require end-to-end testing with a suitable test VPN. The simulated password flow validates the terminal integration, not every server authentication scheme.

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
