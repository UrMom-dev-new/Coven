# Coven Agent Workspace

Coven is a local gothic adventure-game shell for a Hermes Agent workspace. It starts in an illustrated sanctuary with six configurable witch profiles, durable text conversations, a quest journal, explicit task assignment, local/API routing status, and a presentation-only Ophelia river failure scene.

This first implementation is intentionally dependency-light: Python 3.11+ standard library for the loopback server and static browser assets for the UI. Live Hermes dispatch is gated behind a clear adapter boundary and currently fails visibly unless Hermes is available and the adapter is completed. Demo mode is explicit and separate.

## Run

From the repository root:

```powershell
python -m coven.server --host 127.0.0.1 --port 8765 --open
```

Windows launcher:

```powershell
.\scripts\start-coven.ps1 -Open
```

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
- Static sanctuary UI with keyboard-accessible roster and hotspots.
- Separate conversation composer and task assignment form.
- Quest journal with assignee, state, latest update, timeline, blockers, evidence, result, retry action, and mode labels.
- Push-to-talk recording control that uses browser microphone permission and leaves transcript editing to the user when local transcription is not configured.
- Presentation controller for Ophelia's river scene that consumes immutable terminal failure events and cannot mutate task outcomes.
- Demo adapter fixtures for completed, failed, duplicate-safe, skipped, and retried task flows.

## What Is Not Claimed Yet

- Live Hermes chat/task dispatch is not implemented in this starter.
- Hermes was not installed in the development environment used for this commit.
- The Dell Inspiron target hardware was not available, so Windows behavior, performance, local transcription benchmarking, and browser codec behavior still require validation there.
- No OpenAI API credential was available in this environment, so live API calls were not exercised.
- The bundled art is original lightweight SVG, not final generated bitmap/video production art.

See `docs/integration-note.md`, `docs/permission-matrix.md`, and `docs/validation.md` for the implementation contract and remaining gates.
