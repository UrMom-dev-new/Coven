# Integration Capability Matrix

Status values: Pass, Partial, Blocked.

| Area | Implemented behavior | Verification in this environment | Status |
|---|---|---|---|
| Hermes run submission | Live tasks persist the exact run payload before dispatch, send `Idempotency-Key`, record run/session IDs, and can recover unresolved submissions without creating a second local task. | Unit tests cover successful submission, lost-response recovery, idempotency conflict rejection and stale terminal updates. Live Hermes was unavailable. | Partial |
| Hermes reconciliation | Background reconciler refreshes non-terminal live runs from cached task reads instead of blocking every task-list request. | Unit tests cover store update behavior; live polling requires Hermes. | Partial |
| Artifact evidence | Model-reported artifact claims are treated as reported until Coven independently inspects files under configured workspace roots. | Unit tests cover no-root, valid root, outside-root and bad metadata cases. | Pass |
| Workspace roots | `workspace.allowedRoots` and `COVEN_ALLOWED_WORKSPACE_ROOTS` define the only local roots used for artifact inspection. | Config and artifact tests pass. OS-level enforcement is still outside Coven. | Pass |
| Installed Office | Settings detects, saves, and opens installed Word/Excel/PowerPoint apps. Office retains its own account. Native agent automation remains unavailable without a verified bridge. | Saved links, bounded launch arguments, unlinking, and Windows Settings UI are tested. Real Office licensing/sign-in requires the user’s machine. | Partial |
| Microsoft Graph | Config maps tenant/cloud endpoints and reports credential presence separately from authentication. No Graph login or token refresh is implemented. | Unit tests cover endpoint selection and blocked status. Token presence is never treated as verified authentication. | Blocked |
| GovDash user connection | Settings opens a dedicated persistent Edge/Chrome profile, preserves sessions on restart, supports unlink/forget, and retains exports separately. Hermes browser/API automation remains unavailable. | Isolated profile lifecycle, credential-free status, host validation, unlink/forget boundaries, and Windows fixture-session persistence are tested. Real tenant authentication requires the user’s account. | Partial |
| Frontend controls | Task rows expose recover-submission and artifact-validation actions when applicable; onboarding summarizes integration readiness. | JS syntax checks passed; Python tests cover API boundaries. Windows visual QA remains. | Partial |

## External References

- Hermes API server and Runs API: https://hermes-agent.nousresearch.com/docs/user-guide/features/api-server/
- Hermes MCP/browser-control capability model: https://hermes-agent.nousresearch.com/docs/user-guide/features/mcp/
- Microsoft Office Automation overview: https://learn.microsoft.com/en-us/office/vba/language/concepts/getting-started/understanding-automation
- Microsoft unattended Office/RPA considerations: https://learn.microsoft.com/en-us/office/client-developer/integration/considerations-unattended-automation-office-microsoft-365-for-unattended-rpa
- Microsoft Graph workbook sessions: https://learn.microsoft.com/en-us/graph/api/workbook-createsession?view=graph-rest-1.0
- GovDash documentation index: https://support.govdash.com/llms.txt
- GovDash SharePoint setup: https://support.govdash.com/docs/microsoft-sharepoint-integration-setup
- GovDash connectors setup: https://support.govdash.com/docs/dash-connectors-setup-guide
- GovDash webhooks: https://support.govdash.com/docs/webhooks
- GovDash Word Assistant: https://support.govdash.com/docs/using-the-word-assistant
