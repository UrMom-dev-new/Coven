# Product Contract

This contract is persistent project context for later implementation prompts.

- Windows remains the primary OS on a Dell Inspiron 15 3000. Exact CPU, RAM, GPU, storage and peripheral hardware are still unverified.
- HermesAvatar/Coven remains separate from UWORL and all other infrastructure. It uses its own configuration, credentials, workspaces, memory and runtime home. Do not discover, import or reuse UWORL credentials, mounts, network connections, endpoints or repositories.
- Preserve the lightweight foundation: Python backend and modular vanilla JavaScript frontend. Planned desktop stack is pywebview with WebView2 and PyInstaller. The game world should use Canvas 2D with accessible HTML controls.
- Six roles remain configurable in `config/witches.json`: Morgana coordinator, Sybil researcher, Circe builder, Hecate reviewer, Selene archivist and Ophelia failure analyst. Permissions must be enforced by backend/runtime code independently of personality text.
- Real execution belongs to Hermes. Demo fixtures must be explicitly selected and isolated from live state. Coven may store UI preferences, presentation receipts and runtime-ID mappings.
- Local models and OpenAI API models are configuration choices. Default to one local inference job at a time; six witches are roles/sessions, not six loaded models.
- Gameplay and Ophelia's river-death cinematic present task events. They never determine actual execution outcomes, grant permissions, delete data or mutate authoritative task records.
- Browser access to private state requires a short-lived authenticated local session. Development-browser unlock uses a one-time token printed by the server; future desktop bootstrap should mint the session internally without placing reusable secrets in URLs, command lines, logs or browser persistence.
