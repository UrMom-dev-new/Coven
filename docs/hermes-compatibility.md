# Hermes Compatibility

Checked during this implementation on 2026-09-20 from public documentation. Hermes was not installed in this environment, so live compatibility remains unverified.

## Verified Documentation Surface

- Hermes sessions are documented as durable conversation records in `~/.hermes/state.db`, including session metadata, message history and model configuration.
- The documented API-server surface exposes `/v1/capabilities` and session endpoints under `/api/sessions/*` gated by `API_SERVER_KEY`, including session creation and synchronous/streamed chat turns.
- The reviewed public session API does not establish a complete authoritative Kanban/task/run lifecycle contract for Coven's quest journal. Live task dispatch therefore remains disabled until an exact Hermes release is installed and its task APIs are verified.

## Coven Adapter Behavior

- Demo mode uses `DemoAdapter` and the isolated demo namespace.
- Live mode uses `HermesAdapter` only when `runtime.hermesApiBaseUrl` and `runtime.hermesApiKeyEnvironmentVariable` are configured.
- Live chat uses the documented session API shape when available.
- Live task creation, retry and cancellation are disabled with explicit capability errors until the Hermes task/run interface is verified.

## Required Live Gate

1. Install a pinned Hermes release on Windows.
2. Enable its API server with an app-specific `API_SERVER_KEY`.
3. Confirm `/v1/capabilities` advertises the session and task capabilities Coven requires.
4. Run one real chat and one scoped file-writing task in a disposable authorized workspace.
5. Record exact version, endpoints, results and artifact paths in `docs/windows-beta-acceptance.md`.
