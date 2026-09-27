import { api, postJson } from "./api.js";
import { $ } from "./dom.js";

// Polling updates status only. Draft form values survive background refreshes.
export function createRuntimeSettings({ testMicrophone, cancelMicrophone, voiceChanged }) {
  let hydrated = false;
  let installation = {};
  let voiceActive = false;
  let hermesBusy = false;
  let voiceBusy = false;
  let voiceDirty = false;
  const busyInstall = () => ["downloading", "verifying", "activating"].includes(installation.state);
  const feedback = (id, text, error = false) => {
    $(id).textContent = text;
    $(id).dataset.tone = error ? "error" : "info";
  };
  function hydrateVoice(v) {
    $("voiceEnabled").checked = v.enabled;
    $("voiceProfile").value = v.modelProfile;
    $("whisperExecutable").value = v.runtimeExecutable;
    $("whisperModelDir").value = v.modelDir;
    const mic = $("voiceMicrophone");
    if (![...mic.options].some((option) => option.value === v.microphoneId)) {
      mic.add(new Option("Previously selected microphone", v.microphoneId));
    }
    mic.value = v.microphoneId;
    voiceDirty = false;
  }
  function renderInstall() {
    const busy = busyInstall();
    $("voiceSetupFields").disabled = busy || voiceActive || voiceBusy;
    $("cancelVoiceInstall").hidden = !busy || installation.state === "activating";
    $("voiceInstallStatus").textContent = installation.message || "";
    const progress = $("voiceInstallProgress");
    progress.hidden = !busy;
    if (installation.total > 0) {
      progress.max = installation.total;
      progress.value = installation.received || 0;
    } else progress.removeAttribute("value");
  }
  async function refresh() {
    const data = await api("/api/setup/connections");
    const previous = installation.state;
    installation = data.installation;
    const { hermes: h, voice: v } = data.connections;
    if (!hydrated) {
      $("hermesExecutable").value = h.executable;
      $("hermesHome").value = h.home;
      $("hermesAddress").value = h.baseUrl;
      hydrateVoice(v);
      hydrated = true;
    } else if (installation.state === "completed" && previous !== "completed") hydrateVoice(v);
    $("hermesKeyState").textContent = h.keySaved ? "Server key saved. Leave blank to keep it." : "No server key saved yet.";
    $("stopHermes").hidden = !h.startedByCoven;
    $("startHermes").disabled = hermesBusy || h.startedByCoven;
    if (data.connections.error) feedback("hermesFeedback", data.connections.error, true);
    renderInstall();
  }
  async function runHermes(action) {
    if (hermesBusy) return;
    hermesBusy = true;
    const buttons = [...$("hermesSetupForm").querySelectorAll("button")];
    buttons.forEach((button) => { button.disabled = true; });
    feedback("hermesFeedback", action === "start" ? "Starting the selected Hermes runtime…" : "Checking connection…");
    try {
      if (["save", "start"].includes(action)) {
        await postJson("/api/setup/hermes", {
          executable: $("hermesExecutable").value.trim(), home: $("hermesHome").value.trim(),
          baseUrl: $("hermesAddress").value.trim(), apiKey: $("hermesApiKey").value,
        });
        $("hermesApiKey").value = "";
      }
      if (action === "start" || action === "stop") {
        const result = await postJson(`/api/setup/hermes/${action}`, {});
        feedback("hermesFeedback", result.message);
      } else {
        const result = await postJson("/api/setup/hermes/test", {});
        feedback("hermesFeedback", result.test.message, !result.test.ready);
      }
    } catch (error) { feedback("hermesFeedback", error.message, true); }
    finally {
      hermesBusy = false;
      buttons.forEach((button) => { button.disabled = false; });
      await refresh();
    }
  }
  async function browse(id, kind, title, output) {
    const bridge = window.pywebview?.api;
    const method = kind === "folder" ? "choose_folder" : "choose_executable";
    if (!bridge?.[method]) {
      feedback(output, "Paste the full path here. Browse is available in the Coven desktop app.");
      $(id).focus();
      return;
    }
    try {
      const value = await bridge[method](title);
      if (value) { $(id).value = value; $(id).dispatchEvent(new Event("input", { bubbles: true })); }
    } catch (error) { feedback(output, `Could not open the file picker: ${error.message}`, true); }
  }
  async function saveVoice() {
    if (voiceBusy) return;
    voiceBusy = true;
    renderInstall();
    try {
      const result = await postJson("/api/setup/voice", {
        enabled: $("voiceEnabled").checked, modelProfile: $("voiceProfile").value,
        runtimeExecutable: $("whisperExecutable").value.trim(), modelDir: $("whisperModelDir").value.trim(),
        microphoneId: $("voiceMicrophone").value,
      });
      hydrateVoice(result.connections.voice);
      feedback("voiceSetupFeedback", "Voice settings saved. Test your microphone when the files are ready.");
      await voiceChanged();
    } catch (error) { feedback("voiceSetupFeedback", error.message, true); }
    finally { voiceBusy = false; renderInstall(); }
  }
  async function installVoice() {
    voiceBusy = true;
    renderInstall();
    try {
      installation = (await postJson("/api/setup/voice/install", { modelProfile: $("voiceProfile").value })).installation;
      feedback("voiceSetupFeedback", "Installing verified local speech components. You can keep using text chat.");
    } catch (error) { feedback("voiceSetupFeedback", error.message, true); }
    finally { voiceBusy = false; renderInstall(); }
  }
  async function findMicrophones() {
    try {
      if (!navigator.mediaDevices?.getUserMedia) throw new Error("Microphone capture is unavailable. Check Windows microphone permissions for Coven.");
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
      stream.getTracks().forEach((track) => track.stop());
      const devices = await navigator.mediaDevices.enumerateDevices();
      const select = $("voiceMicrophone");
      const selected = select.value;
      select.replaceChildren(new Option("Default system microphone", "default"));
      devices.filter((device) => device.kind === "audioinput" && device.deviceId !== "default").forEach((device, index) => {
        select.add(new Option(device.label || `Microphone ${index + 1}`, device.deviceId));
      });
      select.value = [...select.options].some((option) => option.value === selected) ? selected : "default";
      voiceDirty = true;
      feedback("voiceSetupFeedback", "Choose a microphone, then save voice settings.");
    } catch (error) { feedback("voiceSetupFeedback", `Microphone access failed: ${error.message}`, true); }
  }
  return {
    refresh,
    get installing() { return busyInstall(); },
    showTest(text, error = false) { feedback("microphoneTestResult", text, error); },
    updateVoice(voice, recording, captureAvailable) {
      voiceActive = Boolean(recording);
      renderInstall();
      const test = Boolean(recording?.testOnly);
      $("testMicrophone").disabled = busyInstall() || voiceBusy || voice?.state !== "ready" || !captureAvailable || Boolean(recording && (!test || recording.busy));
      $("testMicrophone").textContent = test ? (recording.busy ? "Transcribing…" : "Finish test") : "Test microphone";
      $("cancelMicrophoneTest").hidden = !test;
      $("voiceSetupReadiness").textContent = voice?.state === "ready" ? "Voice files are ready for a microphone test." :
        voice?.state === "disabled" ? "Voice is disabled. Enable it and save to use your microphone." : (voice?.notes || []).slice(0, 2).join(" ");
    },
    bind() {
      const safely = (fn) => () => Promise.resolve().then(fn).catch((error) => feedback("voiceSetupFeedback", error.message, true));
      $("hermesSetupForm").addEventListener("submit", (event) => { event.preventDefault(); runHermes("save"); });
      $("testHermes").addEventListener("click", () => runHermes("test"));
      $("startHermes").addEventListener("click", () => runHermes("start"));
      $("stopHermes").addEventListener("click", () => runHermes("stop"));
      for (const [button, input, kind, title, output] of [
        ["browseHermes", "hermesExecutable", "file", "Choose your Hermes executable", "hermesFeedback"],
        ["browseHermesHome", "hermesHome", "folder", "Choose the Hermes data folder for this project", "hermesFeedback"],
        ["browseWhisper", "whisperExecutable", "file", "Choose whisper-server.exe", "voiceSetupFeedback"],
        ["browseVoiceModel", "whisperModelDir", "folder", "Choose the Whisper model folder", "voiceSetupFeedback"],
      ]) $(button).addEventListener("click", () => browse(input, kind, title, output));
      $("voiceSetupForm").addEventListener("input", () => { voiceDirty = true; });
      $("voiceSetupForm").addEventListener("submit", (event) => { event.preventDefault(); saveVoice(); });
      $("installVoice").addEventListener("click", installVoice);
      $("cancelVoiceInstall").addEventListener("click", safely(async () => {
        installation = (await postJson("/api/setup/voice/cancel", {})).installation;
        renderInstall();
      }));
      $("findMicrophones").addEventListener("click", findMicrophones);
      $("testMicrophone").addEventListener("click", safely(async () => {
        if (voiceDirty) { feedback("voiceSetupFeedback", "Save voice settings before testing this selection.", true); return; }
        await testMicrophone();
      }));
      $("cancelMicrophoneTest").addEventListener("click", safely(cancelMicrophone));
    },
  };
}
