# Validation

## Automated

Run:

```bash
python3 -m unittest discover -s tests
/Users/nefarioususer/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node --check public/src/app.js
/Users/nefarioususer/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node --check public/src/auth.js
/Users/nefarioususer/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node --check public/src/api.js
/Users/nefarioususer/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node --check public/src/dom.js
/Users/nefarioususer/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node --check public/src/game.js
/Users/nefarioususer/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node --check public/src/presentation.js
python3 -m compileall coven tests
python3 -m coven.desktop --self-test
```

Current tests cover:

- Terminal failure cinematic trigger requires structured `failed + terminal + retryPolicyExhausted`.
- Duplicate failure events do not retrigger playback once marked shown or skipped.
- Transient tool errors and cancellations do not trigger the scene.
- Demo failures persist diagnostic evidence before presentation.
- Retry creates a separate tracked attempt.
- String booleans such as `"false"` do not count as `true`.
- Unknown failed events do not trigger Ophelia's scene.
- One-time auth bootstrap, session cookies and wrong-origin rejection.
- Demo/live namespace isolation and v1 state migration with backup.
- Live task persistence for Hermes run/session IDs, idempotency keys, requested/served runtime, usage, artifacts and bounded timeline events.
- Seeded approved-reference demo task fixtures that stay static during demo advancement.
- Persisted presentation preference validation.
- Static frontend checks for no dynamic `innerHTML` in the app controller and explicit `[hidden]` overlay CSS.
- Demo and Hermes adapter behavior, including empty-response rejection, long-output persistence, pre-dispatch validation, uncertain delivery recovery, live Runs API submission/reconciliation shape, and session reuse.
- Live submission recovery behavior, including stored run payloads, duplicate-safe idempotency reuse, idempotency conflict rejection and stale-terminal-update protection.
- Independent artifact validation under configured workspace roots, including fail-closed handling for untrusted model claims and malformed expected metadata.
- Office, Microsoft Graph and GovDash integration status boundaries, including fail-closed Office operations when no Windows bridge is available.
- Integration config validation for Graph cloud, GovDash route and environment-provided workspace roots.
- Authenticated Hermes API readiness probing through capabilities rather than CLI-version readiness.
- Asset manifest/package scaffold existence and static server cache/HEAD behavior.
- Canvas sanctuary module visibility pause and station interaction event wiring.
- Desktop unlock visibility after the pywebview API-ready event.
- Desktop bridge one-time token behavior, packaged self-test source markers, Windows build self-test hook, installer artifact workflow hook and PyInstaller WebView backend collection.
- Local voice runtime/model readiness boundaries.
- Local voice command routing, editable task/message draft behavior, WAV validation, cancellation, and stale transcription result handling.

Most recent run in this environment:

```text
python3 -m unittest discover -s tests
Ran 75 tests in 0.046s - OK

/Users/nefarioususer/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node --check public/src/app.js / auth.js / api.js / dom.js / game.js / presentation.js
python3 -m compileall coven tests
python3 -m coven.desktop --self-test --self-test-log /private/tmp/coven-desktop-self-test-local-voice.log
OK
```

## Manual Browser Checks

Run in explicit demo mode:

```bash
COVEN_DEMO_MODE=1 python3 -m coven.server --host 127.0.0.1 --port 8765 --open
```

The server prints a one-time development unlock token. Enter it in the browser unlock page to create an authenticated local session.

Verify:

1. Sanctuary loads as the first screen.
2. Roster and station hotspots select each witch with keyboard and mouse.
3. Send message updates the selected witch's transcript without creating a task.
4. Assign task creates a journal entry only through the task form.
5. A normal demo task transitions queued -> running -> completed.
6. A task containing `fail` transitions queued -> running -> failed.
7. The Ophelia scene appears once for the failed terminal event and opens the failure report.
8. Escape or Skip dismisses the scene and preserves the failure report.
9. Retry creates a new task attempt rather than mutating the original failed record.
10. Turning failure scenes off prevents playback while the journal still shows the failed task.

Authenticated API smoke performed on macOS development host after the adapter/desktop/game pass:

```text
COVEN_DEMO_MODE=1 python3 -u -m coven.server --host 127.0.0.1 --port 8892 --data-dir .coven-data/final-smoke --auth-token smoke-token-2
GET /api/tasks without cookie -> 401 auth_required
POST /api/auth/session with token -> 201 and session cookie
GET /api/status with cookie -> 200 demo runtime
POST /api/tasks with cookie -> 201
GET /api/failure-events after demo failure -> structured terminal_failure event
GET /api/voice/status with cookie -> 200 structured local whisper.cpp setup status
```

Authenticated browser visual smoke performed on macOS development host after the approved-reference UI pass:

```text
COVEN_DEMO_MODE=1 python3 -u -m coven.server --host 127.0.0.1 --port 8896 --data-dir .coven-data/production-visual-smoke-2 --auth-token visual-smoke-token-2
Unlocked in the browser with the one-time token.
Approved sanctuary art, portrait crops, seeded Morgana conversation, seeded Quest Journal, All/Active/Done filters and quick-control footer rendered visibly.
Hotspots remained accessible without duplicate visible labels over the approved artwork.
```

Authenticated local working-app smoke performed on macOS development host after the static server/auth reliability pass:

```text
COVEN_DEMO_MODE=1 python3 -u -m coven.server --host 127.0.0.1 --port 8898 --data-dir .coven-data/working-app-smoke --auth-token working-smoke-token
POST /api/auth/session -> 201 authenticated
GET / -> 200 text/html app shell, including sanctuary-art, portrait-crop, journal-tabs, settingsPanel, demoBadge and workspaceMode markers
GET /api/tasks -> 200 seeded demo Quest Journal tasks
GET /api/conversations/morgana -> 200 seeded approved-reference conversation
HEAD /assets/reference/coven-approved-reference.png -> 200 image/png, Cache-Control: public, max-age=3600
HEAD /styles.css -> 200 text/css, Cache-Control: no-store
```

Desktop self-test smoke performed on macOS development host after the Windows packaging pass:

```text
python3 -m coven.desktop --self-test --self-test-log /private/tmp/coven-desktop-self-test-local-voice.log
GET /api/health -> 200
POST /api/auth/session -> 201
GET / -> 200
GET /api/tasks -> 200
GET /api/voice/status -> 200
HEAD /assets/reference/coven-approved-reference.png -> 200
HEAD /styles.css -> 200
Coven desktop self-test passed.
```

## Not Verified In This Environment

- Live Hermes execution against an installed API server, including real provider/model evidence.
- Persistent SSE event streaming from `/v1/runs/{run_id}/events`.
- Windows launcher on the Dell target.
- 1366x768 and 200 percent browser zoom on the target display.
- Ollama local model smoke test, because the local service did not answer from this sandbox.
- OpenAI live API test, because no credential was available.
- Local transcription benchmark, microphone permission, installed Windows voices, and target-machine WebView2 audio capture.
- WebView2/Windows visual inspection after the approved-reference UI rewrite. macOS browser visual smoke passed, but Windows rendering remains unverified.
- PyInstaller/pywebview bundle creation on Windows. The workflow/build script now runs `Coven.exe --self-test`, but that Windows runner has not been executed in this environment.
- Inno Setup installer compile/install/upgrade/uninstall validation. The workflow now compiles an unsigned installer artifact after the portable smoke gate, but that workflow has not been executed from this environment.
- Canvas frame timing and high-DPI layout on Windows.
