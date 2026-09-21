# Windows Beta Acceptance

No Windows VM, Dell Inspiron, WebView2 runtime, Hermes install, microphone hardware or provider credentials were available in this environment. This document records implemented artifacts and unresolved release gates rather than claiming beta acceptance.

## Implemented Artifacts

- `coven/desktop.py` desktop entry point.
- PyInstaller spec: `packaging/Coven.spec`.
- Windows build script: `scripts/build-windows.ps1`.
- Inno Setup script: `packaging/installer/Coven.iss`.
- Installer build script: `scripts/build-installer.ps1`.
- GitHub Actions Windows build workflow: `.github/workflows/windows-build.yml`.
- Authenticated development-browser fallback: `python -m coven.desktop --browser`.
- Headless desktop boot smoke: `python -m coven.desktop --self-test`.
- Portable executable smoke gate: `dist\Coven\Coven.exe --self-test` from `scripts/build-windows.ps1` and the Windows workflow.
- Unsigned installer compile gate: `scripts\build-installer.ps1` and the Windows workflow after the portable smoke gate.

## Acceptance Scenarios

| Scenario | Status | Evidence / blocker |
|---|---|---|
| Fresh install -> onboarding -> real API chat -> real scoped task -> verifiable output | Unverified | Requires Windows build, Hermes API server and provider credentials. |
| Local-model chat/task | Unverified | Local/API route selection is implemented, but Ollama and Hermes local-provider execution were not verified on Windows. |
| Sanctuary exploration and compact work view | Partially implemented | Canvas movement, station interaction and approved-reference UI shell smoke are implemented; real WebView2/Windows visual QA remains. |
| Needs-input/approval/cancel/retry/evidence preservation | Partial | Live stop, approval, retry, evidence and artifact fields are implemented against the documented Runs API and deterministic mocks; live Hermes proof remains blocked. |
| Controlled terminal failure -> one Ophelia scene -> report -> recovery | Fixture-tested at API level | Demo and live-store terminal failure de-duplication are unit-tested; browser playback on Windows remains unverified. |
| Voice round-trip | Partial | Browser/WebView speech APIs are used when exposed and transcripts are scoped by witch; microphone permission, installed Windows voices and transcription quality remain unverified. |
| Restart during run, provider disconnect/reconnect, sleep/resume, duplicate launch | Partial | Single-instance guard and run reconciliation via `GET /v1/runs/{run_id}` are implemented; real gateway interruption/retention behavior requires Hermes. |
| Missing model/key/WebView2/malformed events/hostile HTML/unauthorized local requests | Partial | Auth/origin/malformed event/HTML regressions tested; WebView2 missing path is code-only. |
| Portable executable boots authenticated app shell | Source-tested, Windows pending | `python -m coven.desktop --self-test --self-test-log /private/tmp/coven-desktop-self-test-final.log` passed on macOS source tree; Windows CI runs packaged `Coven.exe --self-test` when pushed. |
| Installer compile, fresh install, upgrade/uninstall/reinstall with retained data, paths with spaces/non-ASCII, standard user, high DPI | Partially implemented | CI now compiles an unsigned Inno Setup installer artifact; clean Windows VM install/upgrade/uninstall remains blocked. |

## Engineering Targets To Measure

- Window usable within 8 seconds on measured Windows test machine.
- Coven/WebView2 process tree under 500 MB idle, excluding Hermes/model inference.
- Responsive controls during inference.
- Stable 30 fps low-effects sanctuary.

These are targets, not claims.
