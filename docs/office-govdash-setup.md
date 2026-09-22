# Office, Graph And GovDash Setup

This branch adds configuration and fail-closed boundaries for the Windows integrations. It does not claim live Office, Microsoft tenant or GovDash execution from this macOS workspace.

## Configuration

Copy `config/coven.example.json` and set only the integrations that are available on the target Windows machine:

```json
{
  "workspace": {
    "allowedRoots": [
      "%USERPROFILE%/Documents/CovenWork"
    ]
  },
  "office": {
    "enabled": true,
    "bridgeExecutable": "",
    "operationTimeoutSeconds": 60
  },
  "microsoftGraph": {
    "enabled": true,
    "cloud": "commercial",
    "tenantId": "your-tenant-id",
    "clientId": "your-public-client-id",
    "tokenEnvironmentVariable": "COVEN_GRAPH_ACCESS_TOKEN"
  },
  "govdash": {
    "enabled": true,
    "route": "sharepoint",
    "sharePointRoot": "%USERPROFILE%/Documents/CovenWork/GovDash",
    "browserProfileDir": "%LOCALAPPDATA%/Coven/GovDashBrowser"
  }
}
```

`COVEN_ALLOWED_WORKSPACE_ROOTS` may add extra artifact-inspection roots. Separate entries with the platform path separator.

## Office Gate

Installed Office automation is intended only for an interactive signed-in Windows session. Coven reports Office as blocked when it is not running on Windows or when no PowerShell/bridge executable is available. The current portable backend exposes the operation schemas and fails closed for native mutation until a Windows bridge worker is installed and verified.

Minimum acceptance on Windows:

1. Start Coven with `office.enabled=true`.
2. Confirm `/api/integrations/status` reports Office configured and operational.
3. Use a disposable `.docx`, `.xlsx` and `.pptx` inside `workspace.allowedRoots`.
4. Inspect, mutate a review copy, render/export output, and validate the output artifact with `files.validate_artifacts`.
5. Record exact Office version, Windows build, document paths and hashes in `docs/windows-beta-acceptance.md`.

## Microsoft Graph Gate

Coven currently checks configuration and the presence of a token environment variable. It does not mint tokens or store tenant secrets. Graph workbook-session work requires delegated work/school access on the tenant, and any selected SharePoint/OneDrive locations must be scoped outside the renderer.

Minimum acceptance with tenant access:

1. Set `microsoftGraph.enabled=true`, `tenantId`, `clientId`, `cloud` and `COVEN_GRAPH_ACCESS_TOKEN`.
2. Confirm `/api/integrations/status` reports the expected Graph endpoint.
3. Browse only selected locations, open a workbook session, perform a bounded read or review output upload, then close the session.
4. Record permissions, scopes and evidence without committing tokens.

## GovDash Gate

GovDash is treated as a tenant-bound external system. The implemented routes are:

- `sharepoint`: exchange files through a configured SharePoint-selected root.
- `browser`: reserved for a dedicated browser profile and visible verification.
- `api`: blocked until a tenant-specific write endpoint is verified.

Minimum acceptance:

1. Configure the actual tenant route and selected workspace location.
2. Verify GovDash access outside Coven first.
3. Run a disposable opportunity/document exchange.
4. Record whether the exchange used SharePoint, browser verification or a verified API, and include resulting artifact hashes.
