# Release Notes

## 0.3.0-beta

- Adds the first-run Guided setup panel for Windows beta users.
- Adds user-scoped protected provider credential storage on Windows through DPAPI-backed blobs.
- Adds setup status APIs for computer checks, WebView2, app-owned Hermes readiness, provider credentials, workspace selection, voice, repair, diagnostics, and update links.
- Adds native startup notices before WebView exists for missing WebView2, duplicate launch, and startup failures.
- Renames the primary installer artifact to `Coven-Setup-x64.exe` and writes `Coven-Setup-x64.exe.sha256`.
- Adds a manual draft-release workflow for a selected ref and an unattended installer install/self-test/uninstall smoke.
- Keeps portable build artifacts as an advanced/developer option.

Unsigned beta status: Authenticode signing is prepared as a release gate but no signing credential was available in this workspace.
