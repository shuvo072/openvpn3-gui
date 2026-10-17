# Security and privacy

Report suspected vulnerabilities privately to **Mehadi Hasan Shuvo** at **hasanshuvo.dev@gmail.com**. Include the affected version, reproduction steps, impact, and sanitized diagnostics. Do not send VPN credentials, private keys, or working connection profiles. Please allow time to investigate before publishing exploit details. No response-time guarantee is currently offered.

## Scope and trust boundaries

The GUI runs as the desktop user and delegates VPN operations and authorization to OpenVPN 3 Linux. It does not elevate privileges, implement a VPN protocol, or replace OpenVPN's access controls. Use a trusted OpenVPN installation and trusted configuration files.

Subprocesses receive argument arrays rather than shell commands. Configuration and session actions use exact service identifiers. Deletion and permanent sealing have explicit confirmation. CLI/service failures remain visible and stale connection controls are disabled when status cannot be read.

The app does not persist credentials, terminal output, or command history. Password prompts are handled by the CLI inside a PTY. Some values explicitly supplied as CLI arguments, such as a proxy password, may be visible through local process inspection even though the form and command preview mask them. Avoid including these values in screenshots or bug reports.

Exports can contain private keys. They are written through a temporary file and atomically replaced with owner-only permissions (`0600`), without writing through an existing destination symlink. Clipboard contents and exported files are outside the app's in-memory lifecycle.

OpenVPN manages routing, DNS, cryptography, and persistent profiles. The GUI's “Connected” label reflects service-reported session state; it is not a connectivity, DNS-leak, or kill-switch test. Closing the GUI leaves established sessions running.

## Supported versions

Security fixes target the latest project release. Older development packages are not maintained separately. The independent OpenVPN, GTK, VTE, Python, and OS packages should receive their distribution/vendor security updates.
