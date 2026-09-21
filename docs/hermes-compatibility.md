# Hermes Compatibility

Checked during this implementation on 2026-09-21 from public documentation. Hermes was not installed in this environment, so live compatibility remains unverified.

## Verified Documentation Surface

- Hermes sessions are documented as durable conversation records in `~/.hermes/state.db`, including session metadata, message history and model configuration.
- The documented API-server surface exposes `/v1/capabilities`, `/health`, `/health/detailed`, session endpoints under `/api/sessions/*`, and a Runs API gated by bearer authentication.
- The documented Runs API includes `POST /v1/runs`, `GET /v1/runs/{run_id}`, `GET /v1/runs/{run_id}/events`, `POST /v1/runs/{run_id}/stop`, and `POST /v1/runs/{run_id}/approval`.
- The documented idempotency contract uses the `Idempotency-Key` header for `POST /v1/runs`; matching retries return the original run within the runtime retention window.
- Provider-aware model discovery is documented at `/api/model/options`; `/v1/models` is not treated as a complete provider inventory.
- Sources checked:
  - https://hermes-agent.nousresearch.com/docs/user-guide/features/api-server/
  - https://hermes-agent.nousresearch.com/docs/user-guide/integrations/programmatic/

## Coven Adapter Behavior

- Demo mode uses `DemoAdapter` and the isolated demo namespace.
- Live mode uses `HermesAdapter` only when `runtime.hermesApiBaseUrl` and `runtime.hermesApiKeyEnvironmentVariable` are configured.
- Live chat validates input before dispatch, stores outgoing delivery state, and treats empty or unfamiliar responses as failures.
- Live task creation requires `/v1/capabilities` to advertise `run_submission` and `run_status`; stop and approval controls use the corresponding advertised endpoints when available.
- Live task records retain local task ID, attempt ID, Hermes run/session IDs, idempotency key, requested runtime, served runtime, usage, approval, artifact references, evidence and bounded timeline history.
- Reconciliation uses `GET /v1/runs/{run_id}` on task-list refresh. Structured events included in run payloads are summarized in the Quest Journal. Persistent SSE consumption from `/events` still requires live Hermes validation before it can be claimed.

## Required Live Gate

1. Install a pinned Hermes release on Windows.
2. Enable its API server with an app-specific `API_SERVER_KEY`.
3. Confirm `/v1/capabilities` advertises `run_submission`, `run_status`, and any optional `run_events_sse`, `run_stop`, and `run_approval` features used in the UI.
4. Run one real chat and one scoped file-writing task in a disposable authorized workspace.
5. Confirm idempotent retry of an uncertain submission reuses the same run rather than creating duplicate side effects.
6. Record exact Hermes version, endpoint, provider/model, results and artifact paths in `docs/windows-beta-acceptance.md`.
