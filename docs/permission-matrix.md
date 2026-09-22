# Permission Matrix

| Surface | Default capability | Explicitly not allowed |
|---|---|---|
| Browser UI | Read presentation state, send conversation text, request task creation through the backend adapter, update presentation settings | Provider secrets, arbitrary shell commands, filesystem access, permission escalation |
| Coven backend | Serve local UI, persist Coven presentation state, inspect runtime availability, normalize task events | Public or LAN binding, unrestricted proxying, credential logging, destructive file operations |
| Demo adapter | Create clearly labeled fixture tasks, deterministic completion/failure events, retry as a separate attempt | Pretending to be Hermes, touching external systems, mutating real task outcomes |
| Hermes live adapter | Dispatch runs through advertised Hermes API capabilities, reconcile status in the background, persist run identity/request payloads, recover uncertain submissions, and expose stop/approval/retry controls | Invented endpoints, silent synthetic success, duplicate side effects after lost responses, profile self-privilege expansion, workspace-policy enforcement beyond configured Hermes/runtime boundaries |
| Workspace/artifact inspector | Inspect local artifact claims only under configured roots and report hash/size evidence | Trusting model-reported existence flags, reading arbitrary paths, treating uninspected artifacts as verified |
| Office bridge | Inspect or mutate review copies through a configured interactive Windows bridge when explicitly enabled | Running unattended Office automation, mutating files outside permitted roots, claiming native Office success without bridge evidence |
| Microsoft Graph | Report configuration/auth readiness and use selected delegated tenant scopes when configured | Storing tokens in the repo, assuming app-only access, browsing unrestricted tenant content |
| GovDash route | Exchange through a configured SharePoint route or visible browser profile after entitlement verification | Inventing unverified tenant API writes, storing GovDash credentials, bypassing GovDash permissions |
| Morgana | Coordination, planning, dependency tracking | Granting permissions or authorizing sensitive actions |
| Sybil | Read-oriented research and evidence gathering | Sending, purchasing, publishing, or unsourced claims |
| Circe | Scoped code/artifact work in authorized workspaces | Blanket admin access or writes outside authorized roots |
| Hecate | Review, verification, permission checks | Disabling enforcement or approving her own permission increase |
| Selene | Project notes and retrievable memory | Storing credentials or resisting user correction/deletion |
| Ophelia | Failure diagnostics and recovery suggestions | Automatic retry, deletion, credential changes, task outcome mutation |

Runtime enforcement belongs in the backend and operating system controls, not in character personality text.
