# Coven Agent Workspace

Repository: `HermesAvatar`

Coven is a local gothic adventure-game shell for a Hermes Agent workspace. It starts in an approved-reference sanctuary with six configurable witch profiles, durable text conversations, a quest journal, explicit task assignment, local/API routing status, desktop/browser launch paths, and a presentation-only Ophelia river failure scene.

This implementation is intentionally dependency-light: Python 3.11+ standard library for the loopback server and static browser assets for the UI, with optional pywebview/PyInstaller dependencies for the Windows desktop shell. Live Hermes chat is routed through a clear adapter boundary when the API server is configured; live task lifecycle dispatch remains blocked until an authoritative Hermes task/run contract is verified. Demo mode is explicit and separate.

## Run

From the repository root:

```powershell
python -m coven.server --host 127.0.0.1 --port 8765 --open
```

The server prints a one-time development unlock token. Enter it in the browser page to create an authenticated local session. Private API reads and writes require that session cookie.

Windows launcher:

```powershell
.\scripts\start-coven.ps1 -Open
```

Desktop shell:

```powershell
python -m pip install -e ".[desktop]"
python -m coven.desktop
```

Desktop boot smoke without opening a GUI:

```powershell
python -m coven.desktop --self-test
```

Portable Windows build:

```powershell
.\scripts\build-windows.ps1 -Clean
```

The build script verifies that `dist\Coven\Coven.exe`, bundled public assets and the approved reference image are present, then runs `Coven.exe --self-test` unless `-SkipSmoke` is supplied.

Demo fixture mode for UI and cinematic testing:

```powershell
$env:COVEN_DEMO_MODE = "1"
python -m coven.server --host 127.0.0.1 --port 8765 --open
```

In demo mode, assign a task whose title or instructions include `fail` to trigger a confirmed terminal failure fixture after the local retry policy is exhausted. The Ophelia scene records the failure event before playback, can be skipped with Escape, and shows the real failure panel afterward.

## Test

```bash
python3 -m unittest discover -s tests
```

## What Is Built

- Loopback-only local server in `coven.server`.
- Runtime inspection for Hermes, Ollama, OpenAI env configuration, and a development-machine hardware summary.
- Six configurable profiles in `config/witches.json`.
- Approved-reference sanctuary UI with keyboard-accessible roster and hotspots.
- Separate conversation composer and task assignment form.
- Quest journal with assignee, state, latest update, timeline, blockers, evidence, result, retry action, mode labels, segmented filters, and quick controls.
- Browser/WebView speech recognition when available, plus speech synthesis for unmuted witch replies; unsupported runtimes are labeled honestly.
- Presentation controller for Ophelia's river scene that consumes immutable terminal failure events and cannot mutate task outcomes.
- Demo adapter fixtures for completed, failed, duplicate-safe, skipped, and retried task flows.
- Desktop unlock bridge for the pywebview shell, browser fallback launcher and packaged executable self-test.

## What Is Not Claimed Yet

- Live Hermes task/run lifecycle dispatch is not claimed yet.
- Hermes was not installed in the development environment used for this commit.
- The Dell Inspiron target hardware was not available, so Windows behavior, performance, local transcription benchmarking, and browser codec behavior still require validation there.
- No OpenAI API credential was available in this environment, so live API calls were not exercised.
- The main sanctuary and portrait presentation now use the approved reference bitmap. Native animation/video polish and Windows high-DPI visual acceptance still require target-machine validation.

See `docs/integration-note.md`, `docs/permission-matrix.md`, and `docs/validation.md` for the implementation contract and remaining gates.

Additional beta docs:

- `docs/product-contract.md`
- `docs/desktop-build.md`
- `docs/hermes-compatibility.md`
- `docs/windows-beta-acceptance.md`
