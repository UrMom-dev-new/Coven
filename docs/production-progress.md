# Production Progress

Last updated: 2026-09-23

Base commit for this continuation pass: `991c6010e8e543d8971aee6d5b10b86380679857`

## Implemented In The Local Voice Commands Pass

- Replaced the WebView/browser speech-recognition path with a local-only voice service boundary:
  - WebView records bounded mono WAV audio and sends it to authenticated local endpoints.
  - `coven.voice` validates RIFF/WAVE PCM input, duration, runtime availability and model SHA1 before transcription.
  - A persistent worker owner process accepts one transcription at a time and owns a private loopback `whisper-server` child process with CPU inference flags.
  - Session generation checks, cancellation and stale-result handling prevent late transcripts from affecting the current UI.
- Added deterministic local command routing:
  - explicit commands such as `Select Circe`, `Open the journal`, `Show Circe's tasks` and `Stop speaking` execute locally.
  - addressed requests such as `Circe, draft ...` become editable task drafts.
  - GovDash, Office, document and solicitation requests remain editable drafts until the user submits them.
  - free-form dictation becomes an editable message draft for the scoped witch.
- Added local voice configuration and packaging metadata:
  - `config/coven.example.json` documents the whisper.cpp runtime/model directories, duration/size limits and disabled cloud speech flags.
  - `packaging/voice/whispercpp-runtime.json` records the manual runtime import policy and verified English Q5_1 model hashes.
  - `packaging/Coven.spec` includes the voice packaging manifest.
- Added frontend controls for voice mode, push-to-talk/click-to-toggle recording, elapsed time, cancellation, local command examples and speech-stop behavior.
- Added `docs/local-voice.md`.
- Added unit/static coverage for cloud-speech rejection, local voice boundaries, command routing, cancellation/stale worker results, WAV validation and packaged voice manifest presence.

## Implemented In This Continuation Pass

- Hardened live Hermes submission reliability:
  - live task records now persist the exact `POST /v1/runs` payload before dispatch
  - repeated submissions with the same idempotency key and same payload reuse the existing local task
  - repeated submissions with the same idempotency key and different payload fail before remote dispatch
  - unresolved/lost-response submissions can be recovered through the stored payload and idempotency key
  - late non-terminal runtime updates cannot overwrite a completed/failed/interrupted task
- Moved live task reconciliation out of task-list reads:
  - `GET /api/tasks` and `GET /api/tasks/{id}` now return local cached state quickly
  - a background reconciler polls live non-terminal Hermes runs when live mode is active
  - `/api/status` reports the reconciler's last run/error snapshot
- Added independent artifact evidence inspection:
  - model-returned artifact claims are marked `reported` until Coven inspects them
  - files are inspected only under configured workspace roots
  - size/hash mismatches and malformed expected metadata fail closed
  - `/api/tasks/{id}/validate-artifacts` and `files.validate_artifacts` expose manual validation
- Added Office, Microsoft Graph and GovDash integration boundaries:
  - `config/coven.example.json` documents `workspace`, `office`, `microsoftGraph` and `govdash`
  - `/api/integrations/status` reports configured/operational/blocked state and exposed tool schemas
  - Office operation requests fail closed when the Windows bridge is unavailable
  - Microsoft Graph reports cloud endpoint, tenant/client/token readiness and does not store credentials
  - GovDash SharePoint/API/browser routes are surfaced without inventing unverified write endpoints
- Routed live chat through the same role/model-routing path used for live tasks.
- Added frontend controls for unresolved submission recovery, artifact validation and integration readiness summaries.
- Added `docs/integration-capability-matrix.md` and `docs/office-govdash-setup.md`.
- Added tests for idempotent local task reuse/conflict, lost-response recovery, stale update rejection, artifact validation, integration status boundaries and integration config validation.

## Previously Implemented In The Hermes Runs Pass

- Implemented the live Hermes Runs API task path behind capability checks:
  - `POST /v1/runs` submission with `Idempotency-Key`
  - `GET /v1/runs/{run_id}` reconciliation on task refresh
  - `POST /v1/runs/{run_id}/stop`
  - `POST /v1/runs/{run_id}/approval`
  - linked retry attempts only for confirmed failed live tasks
- Added durable live task fields for Hermes run/session identity, attempt ID, parent task, idempotency key, requested runtime, served runtime, usage, approval state, artifact references, bounded timeline events and terminal failure events.
- Replaced the `hermes --version` readiness shortcut with authenticated API checks for `/health`, `/v1/capabilities`, `/health/detailed`, and `/api/model/options`.
- Added explicit Local/API/Auto task routing fields in the UI and routed the selected provider/model into Hermes requests when configured.
- Added witch role instructions to live run submission through the supported request body.
- Added chat reliability safeguards:
  - user messages validate type and length before remote dispatch
  - outgoing messages persist delivery state
  - timeouts/connection errors are marked `uncertain`
  - empty/unrecognized assistant payloads fail instead of becoming blank successes
  - long assistant responses use a separate retained-output limit
- Expanded the Quest Journal detail view with requested/served runtime, Hermes run ID, usage, idempotency recovery note, artifact references, stop, approval and linked retry controls.
- Preserved typed and spoken drafts per witch so context switches do not mix transcripts.
- Bound speech recognition results to the witch that started recording and labeled browser speech APIs as exposed but unverified rather than production-ready. The 2026-09-23 voice pass supersedes this with a local whisper.cpp boundary.
- Added a Windows installer build script and updated the Windows workflow to compile and upload an unsigned Inno Setup installer artifact after the portable executable smoke gate.
- Updated Hermes compatibility and acceptance docs to cite the documented Runs API and mark live/Windows-only proof gates honestly.

## Previously Implemented In The Visual/Desktop Pass

- Preserved the approved visual reference at `docs/design/coven-approved-reference.png`.
- Reworked the main app chrome toward the approved Windows composition:
  - brand-led top bar with Sanctuary, Journal and Settings navigation
  - compact view control in the top bar
  - demo badge shown only when demo mode is active
  - live/disconnected workspace state indicator
  - dense three-column Sanctuary/dialogue/Quest Journal layout
  - six-card portrait roster and image-backed journal rows
  - brass framing, candle/ivory text treatment and darker navy panels
- Fixed Sanctuary pointer routing by allowing the full canvas to receive clicks while individual hotspot buttons remain clickable.
- Made the Enter-to-talk prompt functional: Enter now selects the nearby witch when the candle familiar is close to a station.
- Persisted the candle familiar's last Sanctuary position in local browser storage.
- Persisted Hermes session IDs in the Coven JSON store instead of keeping them only in adapter memory.
- Added tests covering namespaced runtime-session persistence and Hermes adapter session reuse.
- Replaced placeholder SVG scene/portrait usage with CSS crops from the approved reference render served from `public/assets/reference/coven-approved-reference.png`.
- Seeded the demo namespace with the approved-reference conversation and three Quest Journal entries: `Prepare project brief`, `Review research notes` and `Organize archive`.
- Changed the Quest Journal filter from a select box to the reference-style All/Active/Done segmented control.
- Collapsed advanced task instructions/priority behind a details disclosure so the default Assign Quest surface matches the compact reference flow.
- Added right-column quick controls for sound, motion and failure scenes, wired to persisted settings.
- Added browser/WebView speech recognition support when `SpeechRecognition`/`webkitSpeechRecognition` is available, plus speech synthesis for witch replies when unmuted. The 2026-09-23 voice pass replaced recognition with local WebView capture plus whisper.cpp transcription.
- Changed local static cache policy so HTML/CSS/JS/JSON are `no-store`; heavy image assets remain cacheable.
- Added static `HEAD` support so browser/preload/package smoke checks can validate assets without downloading bodies.
- Suppressed benign static-response `BrokenPipeError`/`ConnectionResetError` noise when a browser aborts a large asset request.
- Made the desktop unlock button refresh after the pywebview API-ready event instead of only checking during initial page script execution.
- Added a headless desktop `--self-test` path that boots the local service, creates an authenticated session, checks approved-reference UI markers, verifies seeded Quest Journal data, and validates bundled static asset headers.
- Updated the Windows build script and GitHub Actions workflow to run the packaged `Coven.exe --self-test` and fail if the executable cannot boot its desktop service surface.
- Expanded the PyInstaller spec to collect pywebview platform backend modules.

## Verified

- `python3 -m unittest discover -s tests` ran 75 tests and passed.
- `python3 -m compileall coven tests` passed.
- `/Users/nefarioususer/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node --check public/src/app.js` passed.
- `/Users/nefarioususer/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node --check public/src/game.js` passed.
- `/Users/nefarioususer/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node --check public/src/auth.js` passed.
- `/Users/nefarioususer/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node --check public/src/api.js` passed.
- `/Users/nefarioususer/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node --check public/src/dom.js` passed.
- `/Users/nefarioususer/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node --check public/src/presentation.js` passed.
- Authenticated local smoke on port 8893 passed:
  - one-time session unlock succeeded
  - `/api/status` returned demo routing
  - authenticated `/` served the shell with `topbar`, `settingsPanel`, `demoBadge` and `workspaceMode`
  - demo task creation returned `201`
  - demo task advanced to `completed` with evidence
- Authenticated local browser visual smoke on port 8896 passed:
  - one-time browser unlock succeeded
  - approved sanctuary art and portrait crops rendered visibly from the approved PNG
  - seeded Morgana conversation rendered
  - seeded Quest Journal rendered with three demo tasks
  - All/Active/Done journal control and quick-control footer rendered
  - hotspot overlay remained accessible without duplicating visible labels over the approved artwork
- Authenticated local working-app smoke on port 8898 passed:
  - one-time session unlock succeeded
  - `/` served the app shell with approved-reference UI markers
  - `/api/tasks` returned seeded demo Quest Journal tasks
  - `/api/conversations/morgana` returned the seeded approved-reference conversation
  - `HEAD /assets/reference/coven-approved-reference.png` returned `200 image/png` with cacheable image headers
  - `HEAD /styles.css` returned `200 text/css` with `Cache-Control: no-store`
- Headless desktop self-test passed from the source tree:
  - `python3 -m coven.desktop --self-test --self-test-log /private/tmp/coven-desktop-self-test-local-voice.log`
  - local desktop service booted
  - session bootstrap returned `201`
  - authenticated app shell returned approved-reference UI markers
  - seeded demo tasks were available
  - local voice status boundary returned `200`
  - approved reference PNG and CSS `HEAD` checks passed
- New targeted unit coverage includes Hermes empty chat responses, long assistant output persistence, pre-dispatch validation, uncertain delivery state, live run submission/reconciliation shape, lost-response recovery, idempotency conflict rejection, stale terminal-update protection, runtime API readiness gates, live terminal failure event de-duplication, artifact inspection, integration status/config validation and installer workflow markers.

## Still Blocked Or Incomplete

- Windows/WebView2 runtime rendering and high-DPI visual acceptance have not been verified in this macOS workspace.
- Live Hermes task creation, retry, cancellation, approvals and artifact reconciliation are implemented against the documented Runs API and deterministic mocks, but live proof remains blocked because Hermes, provider credentials and an authorized disposable workspace were not available here.
- Persistent SSE consumption from `/v1/runs/{run_id}/events` still requires live runtime validation before production acceptance.
- Native Office document mutation/export, Microsoft Graph workbook/file operations and GovDash exchange flows are now represented as configured/blocked/operational integration surfaces, but remain blocked until a Windows machine with Office, tenant credentials and GovDash entitlement is available.
- Local voice is implemented through WebView audio capture plus a whisper.cpp service boundary; runtime/model installation, microphone permission, Windows/WebView2 capture, installed voices and hardware transcription quality remain unverified here.
- PyInstaller bundle, Inno Setup installer, update flow, signing and Windows CI artifacts remain unverified in this environment. The Windows workflow now includes a packaged executable self-test and installer compile/upload, but that workflow has not been executed from this macOS workspace.
- Full production acceptance requires a Windows machine with WebView2, Hermes, microphone access, provider credentials and the target Dell-class hardware.
