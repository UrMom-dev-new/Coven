# Validation

## Automated

Run:

```bash
python3 -m unittest discover -s tests
```

Current tests cover:

- Terminal failure cinematic trigger requires structured `failed + terminal + retryPolicyExhausted`.
- Duplicate failure events do not retrigger playback once marked shown or skipped.
- Transient tool errors and cancellations do not trigger the scene.
- Demo failures persist diagnostic evidence before presentation.
- Retry creates a separate tracked attempt.

## Manual Browser Checks

Run in explicit demo mode:

```bash
COVEN_DEMO_MODE=1 python3 -m coven.server --host 127.0.0.1 --port 8765 --open
```

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

## Not Verified In This Environment

- Live Hermes dispatch and event streaming.
- Windows launcher on the Dell target.
- 1366x768 and 200 percent browser zoom on the target display.
- Ollama local model smoke test, because the local service did not answer from this sandbox.
- OpenAI live API test, because no credential was available.
- Local transcription benchmark and installed Windows voices.
