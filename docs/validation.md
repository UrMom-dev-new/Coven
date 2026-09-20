# Validation

## Automated

Run:

```bash
python3 -m unittest discover -s tests
/Users/nefarioususer/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node --check public/src/app.js
/Users/nefarioususer/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node --check public/src/auth.js
/Users/nefarioususer/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node --check public/src/game.js
python3 -m compileall coven tests
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
- Persisted presentation preference validation.
- Static frontend checks for no dynamic `innerHTML` in the app controller and explicit `[hidden]` overlay CSS.
- Demo and Hermes adapter boundary behavior.
- Asset manifest/package scaffold existence.
- Canvas sanctuary module visibility pause and station interaction event wiring.
- Voice status boundary.

Most recent run in this environment:

```text
python3 -m unittest discover -s tests
Ran 24 tests in 0.011s - OK

node --check public/src/app.js / auth.js / api.js / dom.js / game.js / presentation.js
python3 -m compileall coven tests
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
GET /api/voice/status with cookie -> 200 structured unavailable status
```

## Not Verified In This Environment

- Live Hermes dispatch and event streaming.
- Windows launcher on the Dell target.
- 1366x768 and 200 percent browser zoom on the target display.
- Ollama local model smoke test, because the local service did not answer from this sandbox.
- OpenAI live API test, because no credential was available.
- Local transcription benchmark and installed Windows voices.
- Real browser visual inspection after the Prompt 1 UI rewrite. The HTTP API was smoke-tested, and JavaScript syntax was checked, but WebView2/Windows rendering remains unverified.
- PyInstaller/pywebview bundle creation on Windows.
- Inno Setup installer validation.
- Canvas frame timing and high-DPI layout on Windows.
