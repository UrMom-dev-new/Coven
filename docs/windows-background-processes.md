# Background windows on Windows

## Cause and fix

Coven refreshes runtime readiness periodically. The runtime inspector caches a
snapshot for 15 seconds, then may run `hermes --version` and `ollama list` again.
Previously these commands captured output without setting Windows process
creation flags. A console executable launched from the windowed Coven app could
therefore open and immediately close a console, often displaying an AppData path.

Runtime probes and the whisper.cpp server now use `CREATE_NO_WINDOW` through a
shared background-process policy. Runtime probes also use null standard input;
their captured results, error messages, and timeouts remain available. No global
window-hiding policy is applied to the application, file pickers, or other user UI.

The desktop entry point now calls `multiprocessing.freeze_support()` before app
imports and argument parsing. This lets a packaged voice worker run its intended
child-process code instead of re-entering the desktop command parser or app.

## Regression checks

- Unit tests exercise Windows launch options at both runtime-probe and speech-
  server call sites, including executable/model paths containing spaces, error
  reporting, timeouts, and reuse of an already-running speech server.
- A Windows-only test launches a real console child, checks that
  `GetConsoleWindow()` returns no console, and confirms standard input is closed.
- The existing packaged `--self-test` now starts the real voice worker and waits
  for a known error response to an intentionally incomplete job. This validates
  frozen multiprocessing and queue communication without a model, microphone,
  or external executable. It is not a transcription-quality test.
- Both portable and installer smoke workflows already run this self-test.

## Interactive acceptance

On Windows, install the build containing this fix and leave Coven open for at
least one minute with Hermes/Ollama installed. Observe several readiness refreshes
and confirm no console windows flash or take focus. With local voice configured,
record twice and confirm the speech server starts without a console and the
second recording reuses it. Check that genuine runtime failures still appear as
status errors and that the folder picker opens normally when explicitly requested.

This source change does not establish that every possible window reported on a
user's machine has the same cause. If File Explorer windows or full Coven windows
continue to appear after updating, capture the window title and when it happens
to distinguish another launch path from these console and worker defects.
