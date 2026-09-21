# Production Acceptance

Status values: Pass, Partial, Fail, Blocked.

| Requirement | Implementation | Evidence | Status |
| --- | --- | --- | --- |
| Preserve the approved visual reference in the repo. | Stored as `docs/design/coven-approved-reference.png`. | File exists in repository working tree. | Pass |
| Match approved top navigation: Coven brand, Sanctuary, Journal, Settings, compact view and workspace state. | `public/index.html`, `public/styles.css` and `public/src/app.js` now provide the top bar, tabs, settings tray, compact control, demo badge and connection indicator. | JS syntax checks passed; authenticated local shell contains the expected topbar/settings markers. Visual runtime not yet inspected on Windows. | Partial |
| Keep DEMO labeling only for demo data. | Demo badge is hidden unless `/api/status` reports demo mode; task rows display a Demo badge only when `task.mode === "demo"`. | Frontend syntax checks passed; `/api/status` smoke returned demo mode. | Pass |
| Maintain 58/21/21 Sanctuary/dialogue/journal composition. | CSS grid uses `58fr 21fr 21fr` with responsive collapse under narrower widths. | CSS reviewed; browser visual acceptance still required. | Partial |
| Ensure Sanctuary map clicks are not swallowed by hotspot overlay. | `.hotspots` has `pointer-events: none`; `.hotspot` restores `pointer-events: auto`. | CSS reviewed; interactive browser smoke still required. | Partial |
| Make Enter-to-talk prompt functional. | `public/src/game.js` tracks the nearest station and dispatches witch selection on Enter when not typing. | Node syntax check passed. | Pass |
| Save adventure hub presentation state. | Candle familiar map position is stored in `localStorage` and clamped on restore. | Node syntax check passed. | Partial |
| Persist Hermes session IDs. | Store schema now includes namespaced `runtimeSessions`; `HermesAdapter` reuses persisted IDs. | `test_runtime_sessions_are_namespaced_and_persisted` and `test_hermes_adapter_reuses_persisted_session` pass. | Pass |
| Provide real live task lifecycle: task, run, attempt, approval, cancel, retry, evidence and artifacts. | Demo task lifecycle exists; live task lifecycle still raises explicit capability errors until Hermes contract is verified. | Unit tests pass for demo retry; authenticated smoke created a demo task that advanced to completed with evidence; docs state live gate. | Blocked |
| Keep Ophelia terminal-failure cinematic guarded. | Existing event normalization requires failed, terminal, retry exhausted and terminal-failure outcome before presentation. | Existing event tests pass. | Pass |
| Provide real Windows/WebView2 voice. | `coven/voice.py` and UI expose unavailable status only. | Voice is intentionally disabled. | Blocked |
| Ship verified Windows portable bundle and installer. | PyInstaller/Inno/CI scaffolding exists from prior pass. | No Windows build agent or signing verification in this workspace. | Blocked |
