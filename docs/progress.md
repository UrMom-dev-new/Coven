# Progress

## Prompt 1 Foundation Repair

Implemented:

- Added `docs/product-contract.md`.
- Added validated configuration loading in `coven/configuration.py`.
- Added one-time local session authentication in `coven/auth.py`.
- Protected private API reads and writes behind session auth; `X-Coven-Intent` remains only a write-intent/CSRF guard.
- Added exact loopback Host/Origin checks and CSP headers.
- Added cached runtime probing via `coven/runtime.py`; static asset requests no longer run Hermes/Ollama subprocess probes.
- Split the browser controller into ES modules and removed dynamic `innerHTML` rendering from `public/src/app.js`.
- Added an authenticated browser unlock page that uses a token printed by the local server, not a URL secret.
- Migrated store schema to separate `demo` and `live` namespaces with v1 backup.
- Persisted presentation preferences for mute, cinematic enablement, motion mode and quality mode.
- Changed event normalization so string booleans are not truthy and unknown failed events do not trigger Ophelia.
- Fixed overlay hidden styling with a global `[hidden]` rule.
- Added cancellable cinematic timers keyed to immutable event IDs.
- Replaced overlapping `setInterval` polling with a single in-flight refresh loop with backoff and visibility-aware scheduling.
- Preserved message delivery to the intended witch when switching profiles during a send.
- Removed fake voice transcript behavior; the UI now labels voice as unavailable until a real transcriber is implemented.

Tested:

- `python3 -m unittest discover -s tests`
- `node --check public/src/app.js`
- `node --check public/src/auth.js`
- Authenticated localhost smoke: unauthenticated reads rejected, token session created, demo task created, terminal failure event emitted.

Unverified:

- Windows/WebView2 behavior.
- Live Hermes execution.
- Real browser visual/layout inspection after this rewrite.
- Microphone, local transcription and speech output.
- Dell hardware performance.

## Prompts 2-8 Roadmap Implementation

Implemented in this pass:

- Desktop entry point using pywebview/WebView2 when installed: `coven/desktop.py`.
- Best-effort per-user single-instance guard.
- LocalAppData path helpers for state, runtime and WebView2 user data.
- Reproducible PyInstaller spec and Windows build script.
- Inno Setup installer skeleton and Windows CI build workflow.
- Demo/Hermes adapter boundary. At that milestone live chat used the documented Hermes session API when configured, and the live task lifecycle was still disabled; the 2026-09-21 continuation below supersedes that task status.
- First-run status/onboarding panel inside the app.
- Canvas 2D sanctuary loop with movable candle familiar and station interaction.
- Quest journal filtering.
- Asset manifest and presentation-state helper.
- Voice service boundary and honest unavailable status.
- Windows beta acceptance document with unresolved release gates.

Tested in this environment:

- `python3 -m unittest discover -s tests` ran 24 tests at that milestone.
- `python3 -m compileall coven tests`.
- `node --check` for all checked-in frontend modules.
- Authenticated local API smoke on port 8892: session, status, task creation, voice status and terminal-failure event.

Unverified gates:

- PyInstaller build on Windows.
- WebView2 rendering and high-DPI behavior.
- Real Hermes chat/task lifecycle.
- Voice recording/transcription/speech in WebView2.
- Installer installation/upgrade/uninstall behavior.
- Dell performance targets.

## 2026-09-21 Production Hardening Continuation

Implemented:

- Live Hermes task dispatch through the documented Runs API when `/v1/capabilities` advertises `run_submission` and `run_status`.
- Stop, approval and linked retry controls for live task records.
- Durable run/session/attempt/idempotency/runtime/usage/artifact/timeline state for live tasks.
- Authenticated runtime readiness checks for health, capabilities, detailed health and model options.
- Separate user-input and assistant-output limits, explicit message delivery states, and timeout-as-uncertain chat behavior.
- Quest Journal runtime detail display and per-witch typed/voice draft isolation.
- Windows installer build script plus CI upload of an unsigned Inno Setup installer artifact.

Tested:

- `python3 -m unittest discover -s tests` ran 45 tests.
- `python3 -m compileall coven tests`.
- Bundled Node `--check` passed for all frontend modules.
- `python3 -m coven.desktop --self-test --self-test-log /private/tmp/coven-desktop-self-test-final.log` passed on this macOS source tree after loopback permission was granted.

Unverified gates:

- Live Hermes execution, served-provider evidence and persistent SSE event streaming.
- Windows/WebView2 visual interaction, PyInstaller artifact generation, installer installation/upgrade/uninstall and signing.
- Microphone permissions, local/API transcription, installed Windows voices and Dell performance targets.
