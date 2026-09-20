# Windows Beta Acceptance

No Windows VM, Dell Inspiron, WebView2 runtime, Hermes install, microphone hardware or provider credentials were available in this environment. This document records implemented artifacts and unresolved release gates rather than claiming beta acceptance.

## Implemented Artifacts

- `coven/desktop.py` desktop entry point.
- PyInstaller spec: `packaging/Coven.spec`.
- Windows build script: `scripts/build-windows.ps1`.
- Inno Setup script: `packaging/installer/Coven.iss`.
- GitHub Actions Windows build workflow: `.github/workflows/windows-build.yml`.
- Authenticated development-browser fallback: `python -m coven.desktop --browser`.

## Acceptance Scenarios

| Scenario | Status | Evidence / blocker |
|---|---|---|
| Fresh install -> onboarding -> real API chat -> real scoped task -> verifiable output | Unverified | Requires Windows build, Hermes API server and provider credentials. |
| Local-model chat/task | Unverified | Ollama availability was not verified on Windows; Hermes task tools are unverified. |
| Sanctuary exploration and compact work view | Partially implemented | Canvas movement and station interaction are implemented; real browser/Windows visual QA remains. |
| Needs-input/approval/cancel/retry/evidence preservation | Partial | Demo retry/evidence exists; live approval/cancel require Hermes task contract. |
| Controlled terminal failure -> one Ophelia scene -> report -> recovery | Fixture-tested at API level | Browser playback on Windows remains unverified. |
| Voice round-trip | Unverified | Voice service boundary exists; transcription/speech providers are not configured. |
| Restart during run, provider disconnect/reconnect, sleep/resume, duplicate launch | Partial | Single-instance guard implemented; live run reconciliation requires Hermes. |
| Missing model/key/WebView2/malformed events/hostile HTML/unauthorized local requests | Partial | Auth/origin/malformed event/HTML regressions tested; WebView2 missing path is code-only. |
| Upgrade/uninstall/reinstall with retained data, paths with spaces/non-ASCII, standard user, high DPI | Unverified | Requires clean Windows VM and installer run. |

## Engineering Targets To Measure

- Window usable within 8 seconds on measured Windows test machine.
- Coven/WebView2 process tree under 500 MB idle, excluding Hermes/model inference.
- Responsive controls during inference.
- Stable 30 fps low-effects sanctuary.

These are targets, not claims.
