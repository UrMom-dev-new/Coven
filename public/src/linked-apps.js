import { api, postJson } from "./api.js";
import { $ } from "./dom.js";

export function createLinkedApps() {
  let settings = null;
  let hydrated = false;
  let officeDirty = false;
  let govdashDirty = false;
  let officeBusy = false;
  let govdashBusy = false;
  const ids = { word: "Word", excel: "Excel", powerpoint: "Powerpoint" };
  function feedback(id, message, error = false) {
    $(id).textContent = message;
    $(id).dataset.tone = error ? "error" : "info";
  }
  function hydrateOffice() {
    $("officeLinksEnabled").checked = settings.office.enabled;
    for (const app of settings.office.apps) $("office" + ids[app.id] + "Path").value = app.path;
    officeDirty = false;
  }
  function hydrateGovdash() {
    const g = settings.govdash;
    $("govdashAddress").value = g.url;
    $("govdashBrowser").value = g.browser;
    $("govdashBrowserPath").value = g.executable;
    govdashDirty = false;
  }
  function render() {
    // Keep initial loading and save responses from replacing edits made in flight.
    $("officeLinksForm").querySelectorAll("input, button").forEach((el) => { el.disabled = !settings || officeBusy; });
    if (!settings) {
      $("govdashLinkFields").disabled = true;
      $("govdashLinksForm").querySelectorAll(".action-row button").forEach((el) => { el.disabled = true; });
      return;
    }
    for (const app of settings.office.apps) {
      $("office" + ids[app.id] + "Status").textContent = app.linked ? "Linked" : app.available ? "Found — save to link" : "Not found";
      $("openOffice" + ids[app.id]).disabled = officeBusy || !app.linked;
    }
    const g = settings.govdash;
    const active = !["closed", "error"].includes(g.session.state);
    $("govdashLinkFields").disabled = active || govdashBusy;
    $("openGovdash").disabled = govdashBusy || !g.enabled || !g.browserAvailable || (active && g.session.state !== "open");
    $("openGovdash").textContent = g.session.state === "open" ? "Show GovDash window" : "Open GovDash / sign in";
    $("closeGovdash").disabled = govdashBusy || !["open", "opening"].includes(g.session.state);
    $("forgetGovdash").disabled = govdashBusy || active || !g.session.savedProfile;
    $("unlinkGovdash").disabled = govdashBusy || active || !g.enabled;
    $("openGovdashDownloads").disabled = govdashBusy;
    $("govdashSessionState").textContent = g.session.message;
    if (settings.error) feedback("officeLinkFeedback", settings.error, true);
  }
  async function refresh() {
    settings = (await api("/api/setup/apps")).apps;
    if (!hydrated) { hydrateOffice(); hydrateGovdash(); hydrated = true; }
    render();
  }
  async function action(group, fn) {
    const output = group === "office" ? "officeLinkFeedback" : "govdashLinkFeedback";
    if (group === "office" ? officeBusy : govdashBusy) return;
    if (group === "office") officeBusy = true; else govdashBusy = true;
    render();
    feedback(output, "Working…");
    try { await fn(output); }
    catch (error) { feedback(output, error.message, true); }
    finally {
      if (group === "office") officeBusy = false; else govdashBusy = false;
      try { await refresh(); } catch (error) { feedback(output, error.message, true); }
      render();
    }
  }
  async function browse(input, title, output) {
    try {
      if (!window.pywebview?.api?.choose_executable) {
        feedback(output, "Paste the full program path here. Browse is available in the Coven desktop app.");
        $(input).focus();
        return;
      }
      const selected = await window.pywebview.api.choose_executable(title);
      if (selected) { $(input).value = selected; $(input).dispatchEvent(new Event("input", { bubbles: true })); }
    } catch { feedback(output, "Could not open the file picker. Try again or paste the program path.", true); }
  }
  return {
    refresh,
    bind() {
      render();
      $("officeLinksForm").addEventListener("input", () => { officeDirty = true; });
      $("govdashLinksForm").addEventListener("input", () => { govdashDirty = true; });
      for (const [app, id] of Object.entries(ids)) {
        $("browseOffice" + id).addEventListener("click", () => browse("office" + id + "Path", `Choose the installed ${id} program`, "officeLinkFeedback"));
        $("openOffice" + id).addEventListener("click", () => action("office", async (output) => {
          if (officeDirty) { feedback(output, "Save your Office selections before opening an app.", true); return; }
          const result = await postJson("/api/setup/apps/office/open", { app });
          feedback(output, result.message);
        }));
      }
      $("officeLinksForm").addEventListener("submit", (event) => {
        event.preventDefault();
        action("office", async (output) => {
          const paths = Object.fromEntries(Object.entries(ids).map(([app, id]) => [app, $("office" + id + "Path").value.trim()]));
          settings = (await postJson("/api/setup/apps/office", { enabled: $("officeLinksEnabled").checked, paths })).apps;
          hydrateOffice();
          feedback(output, "Office links saved. Open an app to check your Microsoft account; its sign-in stays managed by Office.");
        });
      });
      $("unlinkOfficeApps").addEventListener("click", () => action("office", async (output) => {
        settings = (await postJson("/api/setup/apps/office/unlink", {})).apps;
        hydrateOffice();
        feedback(output, "Office unlinked from Coven. Your Office account remains signed in.");
      }));
      $("detectOfficeApps").addEventListener("click", () => action("office", async (output) => {
        settings = (await postJson("/api/setup/apps/detect", {})).apps;
        let found = 0;
        for (const [app, id] of Object.entries(ids)) {
          const path = settings.detected[app];
          if (path) { found++; if (!$("office" + id + "Path").value) $("office" + id + "Path").value = path; }
        }
        $("officeLinksEnabled").checked = found > 0;
        officeDirty = true;
        feedback(output, found ? `Found ${found} Office app(s). Review the paths and save your links.` : "No desktop Office apps found. Install Office or Browse to its program files.", !found);
      }));
      $("browseGovdashBrowser").addEventListener("click", () => browse("govdashBrowserPath", "Choose msedge.exe or chrome.exe", "govdashLinkFeedback"));
      $("govdashBrowser").addEventListener("change", () => {
        $("govdashBrowserPath").value = settings?.detected[$("govdashBrowser").value] || "";
        govdashDirty = true;
      });
      $("govdashLinksForm").addEventListener("submit", (event) => {
        event.preventDefault();
        action("govdash", async (output) => {
          settings = (await postJson("/api/setup/apps/govdash", { enabled: true, url: $("govdashAddress").value.trim(),
            browser: $("govdashBrowser").value, executable: $("govdashBrowserPath").value.trim() })).apps;
          hydrateGovdash();
          feedback(output, "GovDash connection saved. Open GovDash and sign in using its own login page.");
        });
      });
      $("openGovdash").addEventListener("click", () => action("govdash", async (output) => {
        if (govdashDirty) { feedback(output, "Save your GovDash selections before opening the connection.", true); return; }
        await postJson("/api/setup/apps/govdash/open", {});
        feedback(output, "Opening the separate GovDash window. Complete any sign-in or MFA there.");
      }));
      $("closeGovdash").addEventListener("click", () => action("govdash", async (output) => {
        await postJson("/api/setup/apps/govdash/close", {});
        feedback(output, "Closing the GovDash window. Its saved session will be kept.");
      }));
      $("openGovdashDownloads").addEventListener("click", () => action("govdash", async (output) => {
        const result = await postJson("/api/setup/apps/govdash/downloads", {});
        feedback(output, result.message);
      }));
      $("unlinkGovdash").addEventListener("click", () => action("govdash", async (output) => {
        settings = (await postJson("/api/setup/apps/govdash/unlink", {})).apps;
        hydrateGovdash();
        feedback(output, "GovDash unlinked. Its browser profile is kept; choose Forget saved sign-in to remove it.");
      }));
      $("forgetGovdash").addEventListener("click", () => {
        if (!window.confirm("Remove this Coven GovDash connection’s cookies and browser data from this computer? You will need to sign in again. Your everyday browser and Office accounts will stay signed in.")) return;
        action("govdash", async (output) => {
          await postJson("/api/setup/apps/govdash/forget", {});
          feedback(output, "Removing the saved GovDash sign-in…");
        });
      });
    },
  };
}
