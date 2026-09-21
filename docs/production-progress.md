# Production Progress

Last updated: 2026-09-21

Base commit for this continuation pass: `59ef4d3`

## Implemented In This Pass

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
- Added browser/WebView speech recognition support when `SpeechRecognition`/`webkitSpeechRecognition` is available, plus speech synthesis for witch replies when unmuted.
- Changed local static cache policy so HTML/CSS/JS/JSON are `no-store`; heavy image assets remain cacheable.
- Added static `HEAD` support so browser/preload/package smoke checks can validate assets without downloading bodies.
- Suppressed benign static-response `BrokenPipeError`/`ConnectionResetError` noise when a browser aborts a large asset request.
- Made the desktop unlock button refresh after the pywebview API-ready event instead of only checking during initial page script execution.
- Added a headless desktop `--self-test` path that boots the local service, creates an authenticated session, checks approved-reference UI markers, verifies seeded Quest Journal data, and validates bundled static asset headers.
- Updated the Windows build script and GitHub Actions workflow to run the packaged `Coven.exe --self-test` and fail if the executable cannot boot its desktop service surface.
- Expanded the PyInstaller spec to collect pywebview platform backend modules.

## Verified

- `python3 -m unittest discover -s tests` ran 33 tests and passed.
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
  - `python3 -m coven.desktop --self-test --data-dir .coven-data/desktop-self-test --auth-token desktop-self-test-token`
  - local desktop service booted
  - session bootstrap returned `201`
  - authenticated app shell returned approved-reference UI markers
  - seeded demo tasks were available
  - approved reference PNG and CSS `HEAD` checks passed

## Still Blocked Or Incomplete

- Windows/WebView2 runtime rendering and high-DPI visual acceptance have not been verified in this macOS workspace.
- Live Hermes task creation, retry, cancellation, approvals and artifact reconciliation remain blocked on an authoritative installed Hermes task/run API contract.
- Voice is implemented only through browser/WebView speech APIs when available; microphone permission, Windows/WebView2 speech recognition and hardware transcription quality remain unverified here.
- PyInstaller bundle, Inno Setup installer, update flow, signing and Windows CI artifacts remain unverified in this environment. The Windows workflow now includes a packaged executable self-test, but it has not been executed from this macOS workspace.
- Full production acceptance requires a Windows machine with WebView2, Hermes, microphone access, provider credentials and the target Dell-class hardware.
