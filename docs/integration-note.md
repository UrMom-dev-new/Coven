# Integration Note

Checked on 2026-09-20 against the current public documentation and the local development environment.

## Local Inspection

- Repository started empty with no commits and no remote configured.
- `hermes` was not installed on PATH in the development environment.
- `ollama` was installed, but the local service could not be reached from the sandboxed development shell.
- Node/npm were not on PATH. The app therefore uses Python stdlib plus static browser assets, avoiding a build step and dependency install.

## Documentation Findings

- Hermes Platform Support lists Windows 10/11 on x86_64 and aarch64 as Tier 1 through Hermes Desktop and `install.ps1`, while noting that a few features are unavailable on Windows. Source: https://hermes-agent.nousresearch.com/docs/getting-started/platform-support
- Hermes Kanban is documented as a durable task board backed by `~/.hermes/kanban.db`, with task rows, comments, worker identities, CLI/dashboard access, and `kanban_*` tools. Source: https://hermes-agent.nousresearch.com/docs/user-guide/features/kanban/
- Hermes configuration precedence puts CLI arguments first, `~/.hermes/config.yaml` next, `~/.hermes/.env` for secrets, and built-in defaults last. The docs say secrets belong in `.env`. Source: https://hermes-agent.nousresearch.com/docs/user-guide/configuration/
- Ollama documents `ollama launch hermes` and the OpenAI-compatible local endpoint `http://127.0.0.1:11434/v1`, with no API key required for local Ollama. Source: https://docs.ollama.com/integrations/hermes
- OpenAI's current API models page recommends using a configured model appropriate to cost and capability rather than hardcoding a stale assumption. Source: https://developers.openai.com/api/docs/models

## Chosen Adapter Path

The current repo did not contain a Hermes dashboard extension or any app stack to preserve, and Hermes was unavailable locally. The smallest reversible architecture is:

1. Static browser UI for the sanctuary, dialogue, journal, controls, and failure scene.
2. Python loopback adapter server that owns secrets, runtime inspection, durable local presentation state, and future Hermes API/CLI integration.
3. Explicit demo fixture mode for interface and failure-scene testing, isolated from live runtime work.

The browser never receives provider secrets and cannot execute arbitrary shell commands. Live task dispatch fails visibly until the Hermes adapter is completed and verified.

## Live Adapter Contract

The future Hermes adapter should expose structured events with at least:

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

## Gaps

- Documented Hermes dashboard plugin routes and any conversation/session interface must be rechecked against the exact installed Hermes version on Windows before live dispatch is wired.
- Authentication behavior for dashboard/plugin routes must be verified; loopback alone is not an authentication boundary.
- Local transcription must be selected after target hardware inspection and benchmark.
- OpenAI API model identifiers must remain configuration values.
