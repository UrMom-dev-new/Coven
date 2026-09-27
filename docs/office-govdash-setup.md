# Link Office and GovDash from Settings

Open **Settings → Guided setup**. These controls save links and sign-in state outside the Coven application folder, so application updates do not reset them.

## Microsoft Office on this computer

1. Click **Find installed Office**. Coven looks for Word, Excel, and PowerPoint in Windows' registered program locations and common Office installation folders. It does not launch them during detection or status polling.
2. If an app is missing from the list, **Browse** to its installed program: `WINWORD.EXE`, `EXCEL.EXE`, or `POWERPNT.EXE`.
3. Enable Office app links and click **Save Office links**.
4. Use **Open Word / sign in** (or the matching app button). Check the account in Office's own Account menu and sign in there if Office asks.

Office owns its Microsoft account, activation, and credential storage. Coven never asks for that password, exports Office tokens, or signs Office out. Closing or updating Coven preserves Office's existing sign-in. Tenant policies may still require Microsoft to ask for authentication again. **Unlink Office** disables Coven's launch links and keeps the saved paths; it does not sign out of Microsoft.

A **Linked** app means its selected program file exists and Coven can request that it open. It does not verify its license, account, COM automation, or Microsoft Graph permissions.

## GovDash

1. Keep the default `https://dashboard.govdash.us/`, or select GovDash's official transition dashboard if that is the environment your team uses. Callback URLs, arbitrary sites, and plain HTTP are rejected.
2. Choose **Microsoft Edge** (recommended) or **Google Chrome**. Both use a separate Coven profile; the user's normal browser profile is never selected. Expand **Browser location** if automatic detection did not find your installation.
3. Click **Save GovDash connection**, then **Open GovDash / sign in**.
4. Complete your normal GovDash login, Microsoft SSO, or other team-approved sign-in in that browser window, including MFA. Credentials go directly to GovDash or the identity provider.
5. Check that the expected account and organization are shown in GovDash. Coven does not infer successful authentication from a loaded page or existing cookie files.

Coven reuses this browser's profile on later launches. Persistent cookies and local storage survive closing both the browser and Coven. Actual session lifetime and refresh behavior remain controlled by GovDash and the identity provider. Organization policies may block automation-controlled browsers or require a managed device; Coven does not bypass those policies.

- **Show GovDash window** brings the existing window forward.
- **Close GovDash window** keeps its browser data. Closing Coven also closes its owned GovDash browser.
- **Unlink GovDash** disables the connection while keeping the profile for reconnection.
- **Forget saved sign-in** removes only Coven's Edge/Chrome GovDash profile folders after their window closes. The UI asks for confirmation. It does not revoke sessions server-side, remove other browser profiles, sign Office out, or delete exported documents. A file-lock or deletion failure is reported instead of claiming success.
- **Open downloads folder** opens Coven's separate folder for GovDash exports. Downloads receive unique filenames and Windows Internet-zone metadata. Move documents into your chosen Coven work folder when you want to use them in that workspace. Forgetting sign-in preserves these downloads.

The desktop installer includes the browser-control component and uses the browser already installed on Windows. No terminal command or separate driver installation is needed by the user. A browser-development checkout needs the optional desktop dependencies for this feature.

## Agent integration boundary

This feature links interactive Office apps and a persistent GovDash browser for the user. It does **not** add a native Office automation worker, authenticate Microsoft Graph, or expose the signed-in GovDash browser to Hermes. Those execution integrations require separately verified tools and tenant permissions. The backend now reports these distinctions explicitly: saved settings, a token's presence, or an installed PowerShell executable do not count as operational agent access.

GovDash receives no Coven JavaScript bridge. Cookies, tokens, browser page content, and general browser-control commands are not exposed through the Coven renderer API or passed to Hermes. The browser uses its normal sandbox and a process-owned control pipe rather than a TCP debugging port. No raw browser exception containing a possible SSO callback URL is included in API responses.

## Verification

Unit/API tests cover saved paths, path and host validation, authenticated write controls, unlinking, profile deletion boundaries, error reporting, and truthful readiness. Edge UI tests cover saved selections, reloads, unsaved edits, and responsive Settings controls. The optional packaged check `--self-test --self-test-browser` uses a disposable local fixture to verify persistent cookies/local storage across a complete browser-service restart and their removal by Forget. It never signs into GovDash or Microsoft.

Real Office account/activation, organization-specific GovDash SSO/MFA, device policies, and native file pickers must still be checked on the user's Windows machine with their accounts.

## Official references

- Microsoft Office sign-in: https://support.microsoft.com/en-us/accounts-billing/subscriptions/sign-in-to-microsoft-365
- GovDash Microsoft Entra SSO: https://support.govdash.com/docs/microsoft-entra365-single-sign-on-sso-setup
- GovDash account and connector policies: https://support.govdash.com/docs/using-dash-connectors
- Playwright persistent browser context: https://playwright.dev/python/docs/api/class-browsertype#browser-type-launch-persistent-context
- Playwright packaging support: https://playwright.dev/python/docs/library#pyinstaller
