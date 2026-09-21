# Production Progress

Last updated: 2026-09-20

Base commit for this production pass: `3680ea8`

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

## Verified

- `python3 -m unittest discover -s tests` ran 26 tests and passed.
- `python3 -m compileall coven tests` passed.
- `/Users/nefarioususer/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node --check public/src/app.js` passed.
- `/Users/nefarioususer/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node --check public/src/game.js` passed.
- `/Users/nefarioususer/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node --check public/src/auth.js` passed.
- `/Users/nefarioususer/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node --check public/src/api.js` passed.
- Authenticated local smoke on port 8893 passed:
  - one-time session unlock succeeded
  - `/api/status` returned demo routing
  - authenticated `/` served the shell with `topbar`, `settingsPanel`, `demoBadge` and `workspaceMode`
  - demo task creation returned `201`
  - demo task advanced to `completed` with evidence

## Still Blocked Or Incomplete

- Windows/WebView2 runtime rendering and high-DPI visual acceptance have not been verified in this macOS workspace.
- Live Hermes task creation, retry, cancellation, approvals and artifact reconciliation remain blocked on an authoritative installed Hermes task/run API contract.
- Voice recording, transcription and speech output remain unavailable; the UI still presents an honest disabled state.
- PyInstaller bundle, Inno Setup installer, update flow, signing and Windows CI artifacts remain unverified in this environment.
- Full production acceptance requires a Windows machine with WebView2, Hermes, microphone access, provider credentials and the target Dell-class hardware.
