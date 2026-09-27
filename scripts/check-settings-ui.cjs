// Real browser layout/settings checks. ASR itself is tested by smoke-voice-windows.py.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { spawn } = require("node:child_process");
const { chromium } = require("playwright");

async function main() {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "coven-ui-"));
  const config = path.join(root, "config.json");
  fs.writeFileSync(config, JSON.stringify({ runtime: { mode: "demo" } }));
  const output = path.resolve("dist/ui-checks");
  fs.mkdirSync(output, { recursive: true });
  const port = 18765;
  const base = `http://127.0.0.1:${port}`;
  const server = spawn(process.env.PYTHON || "python", ["-m", "coven.server", "--port", String(port), "--config", config,
    "--data-dir", path.join(root, "data"), "--auth-token", "ui-check-token"], { stdio: "ignore" });
  let browser, page;
  const errors = [];
  try {
    for (let attempt = 0; attempt < 100; attempt++) {
      try { if ((await fetch(`${base}/api/health`)).ok) break; } catch {}
      if (attempt === 99) throw new Error("Test server did not start");
      await new Promise((resolve) => setTimeout(resolve, 100));
    }
    browser = await chromium.launch({ headless: true, ...(process.platform === "win32" ? { channel: "msedge" } : {}),
      args: ["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream"] });
    const context = await browser.newContext({ viewport: { width: 1366, height: 900 }, permissions: ["microphone"] });
    const auth = await context.request.post(`${base}/api/auth/session`, {
      headers: { "X-Coven-Intent": "ui-action" }, data: { token: "ui-check-token" },
    });
    assert.equal(auth.status(), 201);
    await context.request.post(`${base}/api/settings`, { headers: { "X-Coven-Intent": "ui-action" },
      data: { cinematicsEnabled: false, mute: true } });
    page = await context.newPage();
    page.on("pageerror", (error) => errors.push(error.message));
    await page.goto(base);
    await page.waitForFunction(() => document.querySelectorAll(".roster-button").length === 6);
    await page.screenshot({ path: path.join(output, "sanctuary.png"), fullPage: true });
    for (const [width, height] of [[1920, 1080], [1366, 768], [1280, 820], [980, 680], [800, 650], [640, 720]]) {
      await page.setViewportSize({ width, height });
      const overflow = await page.evaluate(() => {
        const long = "C:\\Users\\A-very-long-name\\Documents\\" + "long_unbroken_project_name_".repeat(10);
        for (const selector of ["#providerLabel", "#witchRole", ".task-copy span", ".message p", "#systemNotice"])
          document.querySelectorAll(selector).forEach((el) => { el.textContent = long; });
        const problems = [];
        if (document.documentElement.scrollWidth > innerWidth + 1) problems.push("page");
        document.querySelectorAll(".dialogue-panel button, .dialogue-panel p, .dialogue-panel h2, .journal-panel button, .task-copy, #systemNotice").forEach((el) => {
          if (!el.getClientRects().length) return;
          const rect = el.getBoundingClientRect();
          const panel = el.closest("section").getBoundingClientRect();
          if (el.scrollWidth > el.clientWidth + 2 || rect.right > panel.right + 1 || rect.left < panel.left - 1)
            problems.push(el.id || el.className || el.tagName);
        });
        return problems;
      });
      assert.deepEqual(overflow, [], `Text overflow at ${width}x${height}`);
    }
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.locator('[data-view="settings"]').click();
    assert.equal(await page.locator("#workspace").isVisible(), false);
    await page.locator("#hermesExecutable").fill("unsaved draft path");
    await page.locator("#refreshSetupButton").click();
    await page.waitForTimeout(1800);
    assert.equal(await page.locator("#hermesExecutable").inputValue(), "unsaved draft path");
    await page.locator("#hermesExecutable").fill("");
    await page.locator("#hermesAddress").fill("http://example.com:8642");
    await page.locator('#hermesSetupForm button[type="submit"]').click();
    await page.waitForFunction(() => document.querySelector("#hermesFeedback").textContent.includes("local Hermes address"));
    await page.locator("#hermesAddress").fill("http://127.0.0.1:8642");
    await page.locator("#hermesSetupForm").scrollIntoViewIfNeeded();
    await page.screenshot({ path: path.join(output, "hermes-settings.png") });

    await page.locator("#voiceEnabled").uncheck();
    await page.locator("#voiceProfile").selectOption("tiny.en-q5_1");
    await page.locator('#voiceSetupForm button[type="submit"]').click();
    await page.waitForFunction(() => document.querySelector("#voiceSetupFeedback").textContent.startsWith("Voice settings saved"));
    await page.reload();
    await page.locator('[data-view="settings"]').click();
    await page.waitForFunction(() => document.querySelector("#voiceProfile").value === "tiny.en-q5_1");
    assert.equal(await page.locator("#voiceEnabled").isChecked(), false);
    await page.locator("#voiceSetupForm").scrollIntoViewIfNeeded();
    await page.screenshot({ path: path.join(output, "voice-settings.png") });
    const settingsOverflow = await page.evaluate(() => [...document.querySelectorAll(".setup-card")]
      .filter((el) => el.scrollWidth > el.clientWidth + 2).map((el) => el.id));
    assert.deepEqual(settingsOverflow, []);

    // App paths and links persist through reload. Office is a file fixture here;
    // Office account/license checks require an actual Office installation.
    const officeFixture = path.join(root, "Office with spaces", "WINWORD.EXE");
    fs.mkdirSync(path.dirname(officeFixture), { recursive: true });
    fs.writeFileSync(officeFixture, "fixture only; never executed");
    await page.locator("#officeWordPath").fill(officeFixture);
    await page.locator("#officeLinksEnabled").check();
    await page.locator('#officeLinksForm button[type="submit"]').click();
    await page.waitForFunction(() => document.querySelector("#officeLinkFeedback").textContent.startsWith("Office links saved"));
    await page.locator("#govdashAddress").fill("https://dashboard.govdash.us.evil.test/");
    await page.locator('#govdashLinksForm button[type="submit"]').click();
    await page.waitForFunction(() => document.querySelector("#govdashLinkFeedback").textContent.includes("official transition dashboard"));
    await page.locator("#govdashAddress").fill("https://dashboard.govdash.us/");
    await page.locator('#govdashLinksForm button[type="submit"]').click();
    await page.waitForFunction(() => document.querySelector("#govdashLinkFeedback").textContent.startsWith("GovDash connection saved"));
    await page.reload();
    await page.locator('[data-view="settings"]').click();
    await page.waitForFunction(() => document.querySelector("#officeWordStatus").textContent === "Linked");
    // Python resolves Windows short names (RUNNER~1) to their full paths.
    assert.equal(fs.realpathSync.native(await page.locator("#officeWordPath").inputValue()), fs.realpathSync.native(officeFixture));
    assert.equal(await page.locator("#openGovdash").isEnabled(), true);
    assert.equal(await page.locator("#forgetGovdash").isEnabled(), false);
    await page.locator("#officeLinksForm").scrollIntoViewIfNeeded();
    await page.screenshot({ path: path.join(output, "office-links.png") });
    await page.locator("#govdashLinksForm").scrollIntoViewIfNeeded();
    await page.screenshot({ path: path.join(output, "govdash-link.png") });
    await page.locator("#officeWordPath").fill("unsaved Office path");
    await page.locator("#refreshSetupButton").click();
    await page.waitForTimeout(1800);
    assert.equal(await page.locator("#officeWordPath").inputValue(), "unsaved Office path");
    await page.locator("#unlinkOfficeApps").click();
    await page.waitForFunction(() => document.querySelector("#officeLinkFeedback").textContent.startsWith("Office unlinked"));
    assert.equal(fs.realpathSync.native(await page.locator("#officeWordPath").inputValue()), fs.realpathSync.native(officeFixture));
    await page.locator("#unlinkGovdash").click();
    await page.waitForFunction(() => document.querySelector("#govdashLinkFeedback").textContent.startsWith("GovDash unlinked"));
    assert.equal(await page.locator("#openGovdash").isEnabled(), false);
    for (const width of [1280, 980, 640]) {
      await page.setViewportSize({ width, height: 900 });
      const overflow = await page.evaluate(() => [...document.querySelectorAll(".setup-card")]
        .filter((el) => el.scrollWidth > el.clientWidth + 2).map((el) => el.id));
      assert.deepEqual(overflow, [], `Settings overflow at ${width}px`);
    }
    await page.setViewportSize({ width: 1280, height: 900 });

    // Capture permissions/audio are real fake-device browser input; only the ASR
    // response is a fixture. Ensure microphone testing never executes a command.
    await page.route("**/api/voice/status", async (route) => {
      const original = await (await route.fetch()).json();
      original.voice.state = "ready";
      original.voice.enabled = true;
      await route.fulfill({ json: original });
    });
    const session = { id: "ui-mic-test", generation: 1, witchId: "morgana", inputMode: "dictation", state: "listening" };
    await page.route("**/api/voice/start", (route) => route.fulfill({ json: { session } }));
    await page.route("**/api/voice/sessions/ui-mic-test/audio", (route) => route.fulfill({ json: { session } }));
    await page.route("**/api/voice/sessions/ui-mic-test", (route) => route.fulfill({ json: {
      session: { ...session, state: "transcript_ready", result: { transcript: "Select Circe", command: { action: "select_witch", witchId: "circe" } } },
    } }));
    await page.waitForFunction(() => !document.querySelector("#testMicrophone").disabled);
    const selected = await page.locator("#selectedWitchName").textContent();
    let dispatches = 0;
    page.on("request", (request) => {
      if (request.method() === "POST" && /\/api\/(tasks|conversations)(\/|$)/.test(new URL(request.url()).pathname)) dispatches++;
    });
    await page.locator("#testMicrophone").click();
    await page.waitForFunction(() => !document.querySelector("#testMicrophone").disabled && document.querySelector("#testMicrophone").textContent === "Finish test");
    await page.waitForTimeout(600);
    await page.locator("#testMicrophone").click();
    await page.waitForFunction(() => document.querySelector("#microphoneTestResult").textContent.includes("Heard: Select Circe"));
    assert.equal(await page.locator("#selectedWitchName").textContent(), selected);
    assert.equal(dispatches, 0);
    assert.deepEqual(errors, []);
    console.log("Settings and Office/GovDash link persistence, unlinking, dirty-form preservation, endpoint validation, microphone test isolation, and six viewport layouts passed.");
  } catch (error) {
    if (page) await page.screenshot({ path: path.join(output, "failure.png"), fullPage: true }).catch(() => {});
    throw error;
  } finally {
    if (browser) await browser.close();
    server.kill();
    await new Promise((resolve) => server.once("exit", resolve));
    fs.rmSync(root, { recursive: true, force: true });
  }
}

main().catch((error) => { console.error(error); process.exitCode = 1; });
