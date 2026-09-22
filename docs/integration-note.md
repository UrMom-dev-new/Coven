# Integration Note

Checked on 2026-09-22 against public documentation and the local development environment.

## Local Inspection

- Repository now contains the Coven Python/static-web desktop app on top of the approved-reference visual pass.
- `hermes` was not installed on PATH in the development environment.
- `ollama` was installed, but the local service could not be reached from the sandboxed development shell.
- Node/npm were not on the default PATH. Syntax checks use the bundled Codex Node runtime when available. The app still uses Python stdlib plus static browser assets, avoiding an app build step.

## Documentation Findings

- Hermes Platform Support lists Windows 10/11 on x86_64 and aarch64 as Tier 1 through Hermes Desktop and `install.ps1`, while noting that a few features are unavailable on Windows. Source: https://hermes-agent.nousresearch.com/docs/getting-started/platform-support
- Hermes Kanban is documented as a durable task board backed by `~/.hermes/kanban.db`, with task rows, comments, worker identities, CLI/dashboard access, and `kanban_*` tools. Source: https://hermes-agent.nousresearch.com/docs/user-guide/features/kanban/
- Hermes configuration precedence puts CLI arguments first, `~/.hermes/config.yaml` next, `~/.hermes/.env` for secrets, and built-in defaults last. The docs say secrets belong in `.env`. Source: https://hermes-agent.nousresearch.com/docs/user-guide/configuration/
- Ollama documents `ollama launch hermes` and the OpenAI-compatible local endpoint `http://127.0.0.1:11434/v1`, with no API key required for local Ollama. Source: https://docs.ollama.com/integrations/hermes
- OpenAI's current API models page recommends using a configured model appropriate to cost and capability rather than hardcoding a stale assumption. Source: https://developers.openai.com/api/docs/models

## Chosen Adapter Path

Hermes, Office, Microsoft Graph and GovDash access were unavailable locally, so Coven keeps each external surface behind an explicit adapter/status boundary:

1. Static browser UI for the sanctuary, dialogue, journal, controls, and failure scene.
2. Python loopback adapter server that owns secrets, runtime inspection, durable local presentation state, Hermes API calls, and integration readiness checks.
3. Explicit demo fixture mode for interface and failure-scene testing, isolated from live runtime work.
4. Configured workspace roots for artifact inspection; model-reported file claims are never accepted as verified evidence without local inspection.

The browser never receives provider secrets and cannot execute arbitrary shell commands. Live task dispatch fails visibly unless Hermes is configured and advertises the required Runs API capabilities.

## Live Adapter Contract

The Hermes adapter persists and exposes structured task state with at least:

- `id`
- `taskId`
- `attemptId`
- `title`
- `assignee`
- `status`
- `terminal`
- `retryPolicyExhausted`
- `outcomeKind`
- `error`
- `lastSuccessfulStep`
- `timestamp`

The Ophelia scene may trigger only when `status == failed`, `terminal == true`, `retryPolicyExhausted == true`, and `outcomeKind == terminal_failure`. Recoverable tool errors, user cancellations, pending approvals, needs-input states, missing configuration, and disconnections are non-terminal presentation states.

## External Integration Contract

- Office automation is disabled by default and may only become operational in an interactive Windows session with a configured bridge. Native mutations fail closed when the bridge is unavailable.
- Microsoft Graph configuration reports cloud endpoint, tenant ID, client ID and token-env readiness. Coven does not mint or store tokens in this branch.
- GovDash supports explicit route states for SharePoint exchange, browser verification and blocked API writes until tenant-specific endpoints are verified.
- Tool schemas are advertised as capability metadata; they are not evidence that a live external system was exercised.

## Gaps

- Documented Hermes dashboard/plugin routes and any conversation/session interface must be rechecked against the exact installed Hermes version on Windows before production acceptance.
- Authentication behavior for dashboard/plugin routes must be verified; loopback alone is not an authentication boundary.
- Local transcription must be selected after target hardware inspection and benchmark.
- OpenAI API model identifiers must remain configuration values.
- Native Office, Microsoft Graph and GovDash flows require target-machine/tenant validation before release claims.
