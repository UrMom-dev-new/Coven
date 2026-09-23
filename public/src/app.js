import { api, postBinary, postJson } from "./api.js";
import { $, clear, field, node, restoreFocus } from "./dom.js";
import { createSanctuaryGame } from "./game.js";
import { sceneDurationForMotion } from "./presentation.js";

const state = {
  profiles: [],
  selectedWitch: "morgana",
  selectedTask: null,
  tasks: [],
  status: null,
  settings: {
    cinematicsEnabled: true,
    reducedMotionMode: "tableau",
    mute: false,
    animationQuality: "balanced",
  },
  conversations: {},
  failureQueue: [],
  currentFailure: null,
  cinematicTimer: null,
  skipAllFailures: false,
  recording: null,
  voiceStatus: null,
  voiceCommands: [],
  setupStatus: null,
  voiceHoldTimer: null,
  voiceDrafts: {},
  messageDrafts: {},
  lastSpokenMessageId: null,
  compact: false,
  taskFilter: "all",
  activeView: "sanctuary",
  game: null,
  refreshTimer: null,
  refreshInFlight: false,
  refreshBackoffMs: 1500,
  assigningTask: false,
  pendingTaskKey: null,
};

const positions = {
  morgana: { left: "49%", top: "68%" },
  sybil: { left: "50%", top: "37%" },
  circe: { left: "27%", top: "58%" },
  hecate: { left: "71%", top: "58%" },
  selene: { left: "14%", top: "59%" },
  ophelia: { left: "82%", top: "54%" },
};

function profile(id = state.selectedWitch) {
  return state.profiles.find((item) => item.id === id) || state.profiles[0];
}

function setNotice(message, tone = "info") {
  const notice = $("systemNotice");
  notice.textContent = message || "";
  notice.dataset.tone = tone;
}

function renderOnboarding() {
  const host = $("onboardingChecks");
  if (!host || !state.status) return;
  clear(host);
  const items = [
    ["Mode", state.status.demoMode ? "Demo tutorial state is isolated." : "Live namespace selected."],
    ["Hermes", state.status.hermes?.operational ? "CLI installed." : "CLI not operational yet."],
    ["Hermes API", hermesApiSummary()],
    ["Ollama", state.status.ollama?.operational ? "Local service reachable." : "Local service unavailable."],
    ["OpenAI", state.status.openai?.configured ? "API key environment variable found." : "API key not configured."],
    ["Office", integrationSummary("office")],
    ["Microsoft", integrationSummary("microsoftGraph")],
    ["GovDash", integrationSummary("govdash")],
    ["Hardware", `${state.status.hardware?.system || "unknown"} ${state.status.hardware?.machine || ""}, ${state.status.hardware?.memory || "memory unknown"}`],
    ["Workspace", workspaceSummary()],
    ["Voice", voiceSummary()],
    ["Setup", setupSummary()],
  ];
  for (const [title, text] of items) {
    host.append(node("div", { className: "check-item" }, [node("b", { text: title }), node("span", { text })]));
  }
}

function integrationSummary(name) {
  const item = state.status?.integrations?.[name];
  if (!item?.configured) return "Not configured.";
  if (item.operational) return "Operational.";
  return (item.notes && item.notes[0]) || "Configured but blocked.";
}

function workspaceSummary() {
  const workspace = state.status?.integrations?.workspace;
  if (workspace?.operational) return `${workspace.allowedRoots?.length || 0} permitted root(s).`;
  return "No permitted workspace roots configured.";
}

function hermesApiSummary() {
  const apiState = state.status?.hermesApi;
  if (!apiState?.configured) return "API transport not configured.";
  if (!apiState.reachable) return "Endpoint not reachable.";
  if (!apiState.authenticated) return "Bearer token not accepted.";
  if (!apiState.taskCapable) return "Authenticated, but Runs API is not advertised.";
  return apiState.runEventsCapable ? "Runs API ready with event stream support." : "Runs API ready; event stream unavailable.";
}

function voiceSummary() {
  const voice = state.voiceStatus;
  if (!voice) return "Checking local voice.";
  if (!voice.enabled) return "Disabled.";
  if (voice.state === "ready") return `${voice.model?.label || voice.model?.profile || "Whisper model"} ready locally.`;
  return (voice.notes && voice.notes[0]) || "Local voice setup is required.";
}

function setupSummary() {
  const setup = state.setupStatus;
  if (!setup) return "Checking first-run setup.";
  if (setup.setupComplete) return "Setup complete.";
  const pending = (setup.steps || []).filter((step) => step.state !== "ready" && step.state !== "optional" && step.state !== "unverified");
  return pending.length ? `${pending.length} setup step(s) need attention.` : "Ready to finish setup.";
}

function captureUiPosition() {
  return {
    activeId: document.activeElement?.id || "",
    transcript: $("transcript")?.scrollTop || 0,
    taskList: $("taskList")?.scrollTop || 0,
    taskDetail: $("taskDetail")?.scrollTop || 0,
  };
}

function restoreUiPosition(position) {
  if (!position) return;
  if ($("transcript")) $("transcript").scrollTop = position.transcript;
  if ($("taskList")) $("taskList").scrollTop = position.taskList;
  if ($("taskDetail")) $("taskDetail").scrollTop = position.taskDetail;
  restoreFocus(position.activeId);
}

function isTypingSensitive() {
  const active = document.activeElement;
  return active instanceof HTMLInputElement || active instanceof HTMLTextAreaElement || active instanceof HTMLSelectElement;
}

async function refreshStatus(force = false) {
  state.status = force ? await postJson("/api/status/refresh", {}) : await api("/api/status");
  $("connectionState").textContent = state.status.connection;
  $("settingsConnectionState").textContent = state.status.connection;
  $("workspaceMode").textContent = state.status.demoMode ? "Demo workspace" : "Live workspace";
  $("demoBadge").hidden = !state.status.demoMode;
  $("runtimeRoute").textContent = state.status.routing.taskRuntime;
  $("providerRoute").textContent = `${state.status.routing.localModel} / ${state.status.routing.apiModel}`;
  $("taskingState").textContent = state.status.demoMode ? "Explicit demo mode" : (state.status.hermesApi?.taskCapable ? "Hermes Runs API ready" : "Hermes Runs API unavailable");
  document.body.dataset.connection = state.status.connection;
  if (!state.status.demoMode && !state.status.hermesApi?.taskCapable) {
    setNotice("Hermes is not ready for live task dispatch. Check endpoint, bearer token, capabilities, and model setup.", "warn");
  } else if (state.status.demoMode) {
    setNotice("Demo mode is active. Fixture tasks are isolated from the future live Hermes namespace.", "warn");
  } else {
    setNotice("Hermes Runs API is available. Live tasks are submitted as recoverable remote runs.", "info");
  }
  renderOnboarding();
}

async function refreshSetupStatus() {
  const payload = await api("/api/setup/status");
  state.setupStatus = payload.setup;
  renderSetupWizard();
  renderOnboarding();
}

async function refreshVoiceStatus() {
  const [statusPayload, commandsPayload] = await Promise.all([
    api("/api/voice/status"),
    state.voiceCommands.length ? Promise.resolve({ commands: state.voiceCommands }) : api("/api/voice/commands"),
  ]);
  state.voiceStatus = statusPayload.voice;
  state.voiceCommands = commandsPayload.commands || [];
  renderVoiceCommands();
  updateVoiceAvailability();
  renderOnboarding();
}

function renderSetupWizard() {
  const setup = state.setupStatus;
  const list = $("setupSteps");
  if (!setup || !list) return;
  clear(list);
  $("setupPrivacy").textContent = setup.privacy || "";
  for (const step of setup.steps || []) {
    list.append(node("li", { className: `setup-step setup-${step.state || "unknown"}` }, [
      node("b", { text: step.label || step.id }),
      node("span", { text: step.summary || "" }),
      node("em", { text: statusLabel(step.state || "unknown") }),
    ]));
  }
  document.body.dataset.setupComplete = String(Boolean(setup.setupComplete));
}

async function chooseSetupMode(mode) {
  try {
    const payload = await postJson("/api/setup/mode", { mode });
    state.setupStatus = payload.setup;
    renderSetupWizard();
    setNotice(mode === "demo" ? "Demo exploration is enabled. Live execution still requires setup." : "Live setup selected.", "info");
  } catch (error) {
    setNotice(error.message, "error");
  }
}

async function saveProviderCredential(event) {
  event.preventDefault();
  try {
    const payload = await postJson("/api/setup/provider", {
      model: $("providerModel").value.trim(),
      apiKey: $("providerApiKey").value,
    });
    $("providerApiKey").value = "";
    state.setupStatus = payload.setup;
    renderSetupWizard();
    setNotice("Credential saved outside renderer storage. Run the connection test before assigning live work.", "info");
  } catch (error) {
    setNotice(error.message, "error");
  }
}

async function removeProviderCredential() {
  try {
    const payload = await postJson("/api/setup/provider/remove", {});
    state.setupStatus = payload.setup;
    renderSetupWizard();
    setNotice("Provider credential removed.", "info");
  } catch (error) {
    setNotice(error.message, "error");
  }
}

async function chooseWorkspaceFolder() {
  if (window.pywebview?.api?.choose_folder) {
    const selected = await window.pywebview.api.choose_folder();
    if (selected) $("workspacePath").value = selected;
    return;
  }
  setNotice("Folder picker is available in the Windows desktop shell. Paste a folder path here in browser mode.", "warn");
}

async function saveWorkspace(event) {
  event.preventDefault();
  try {
    const payload = await postJson("/api/setup/workspace", { path: $("workspacePath").value.trim() });
    state.setupStatus = payload.setup;
    renderSetupWizard();
    setNotice("Work folder saved and verified writable.", "info");
  } catch (error) {
    setNotice(error.message, "error");
  }
}

async function repairComponents() {
  try {
    const payload = await postJson("/api/setup/repair", {});
    state.setupStatus = payload.setup;
    renderSetupWizard();
    setNotice("Repair requested. Coven will re-check app-owned components on the next Windows setup run.", "info");
  } catch (error) {
    setNotice(error.message, "error");
  }
}

async function exportSupportBundle() {
  try {
    const payload = await postJson("/api/setup/support-bundle", {});
    setNotice(`Diagnostics exported: ${payload.support?.path || "support bundle created"}`, "info");
  } catch (error) {
    setNotice(error.message, "error");
  }
}

function checkForUpdates() {
  const page = state.setupStatus?.release?.downloadPage || "https://github.com/UrMom-dev-new/HermesAvatar/releases";
  window.open(page, "_blank", "noopener");
}

async function completeSetup() {
  try {
    const payload = await postJson("/api/setup/complete", {});
    state.setupStatus = payload.setup;
    renderSetupWizard();
    setNotice(
      state.setupStatus.setupComplete ? "Setup complete. Welcome to the Sanctuary." : "Setup is saved, but some live prerequisites still need attention.",
      state.setupStatus.setupComplete ? "info" : "warn",
    );
  } catch (error) {
    setNotice(error.message, "error");
  }
}

async function refreshSettings() {
  const payload = await api("/api/settings");
  state.settings = payload.settings;
  applySettings();
}

function applySettings() {
  $("toggleMute").checked = Boolean(state.settings.mute);
  $("toggleCinematics").checked = Boolean(state.settings.cinematicsEnabled);
  $("motionMode").value = state.settings.reducedMotionMode;
  $("qualityMode").value = state.settings.animationQuality;
  $("soundSummary").textContent = state.settings.mute ? "Off" : "On";
  $("motionSummary").textContent = statusLabel(state.settings.reducedMotionMode);
  $("failureSummary").textContent = state.settings.cinematicsEnabled ? "On" : "Off";
  document.body.classList.toggle("quality-low", state.settings.animationQuality === "low");
  document.body.classList.toggle("muted", Boolean(state.settings.mute));
  state.game?.setQuality(state.settings.animationQuality);
}

async function updateSettings(updates) {
  const payload = await postJson("/api/settings", updates);
  state.settings = payload.settings;
  applySettings();
}

async function refreshProfiles() {
  const payload = await api("/api/profiles");
  state.profiles = payload.witches;
  renderRoster();
  renderHotspots();
  selectWitch(state.selectedWitch, { fetchConversation: false });
}

async function refreshTasks() {
  const payload = await api("/api/tasks");
  state.tasks = payload.tasks;
  state.game?.setTasks(state.tasks);
  renderTasks();
}

async function refreshConversation(witchId = state.selectedWitch) {
  const payload = await api(`/api/conversations/${encodeURIComponent(witchId)}`);
  state.conversations[witchId] = payload.messages;
  if (witchId === state.selectedWitch) renderTranscript();
}

async function refreshFailures() {
  const payload = await api("/api/failure-events");
  for (const event of payload.events) {
    if (!state.settings.cinematicsEnabled || state.skipAllFailures) {
      await markCinematic(event.eventId, "skipped");
      continue;
    }
    const alreadyQueued = state.failureQueue.some((item) => item.eventId === event.eventId);
    const current = state.currentFailure?.eventId === event.eventId;
    if (!alreadyQueued && !current) state.failureQueue.push(event);
  }
  maybePlayFailure();
}

function runtimeStateFor(witchId) {
  const active = state.tasks.filter((task) => task.assignee === witchId && ["queued", "running", "needs input", "needs_input", "waiting_for_approval", "stopping", "unknown", "disconnected"].includes(task.status)).length;
  const failed = state.tasks.filter((task) => task.assignee === witchId && task.status === "failed").length;
  if (failed) return `${failed} failed`;
  if (active) return `${active} active`;
  return "available";
}

function renderRoster() {
  const roster = $("roster");
  clear(roster);
  state.profiles.forEach((witch) => {
    const button = node("button", {
      className: "roster-button",
      type: "button",
      dataset: { selected: witch.id === state.selectedWitch },
    }, [
      node("span", {
        className: "portrait-crop",
        dataset: { witch: witch.id },
        attrs: { role: "img", "aria-label": `${witch.name} portrait` },
      }),
      node("span", { text: witch.name }),
      node("small", { text: witch.title }),
      node("b", { text: runtimeStateFor(witch.id) }),
    ]);
    button.addEventListener("click", () => selectWitch(witch.id));
    roster.append(button);
  });
}

function renderHotspots() {
  const host = $("hotspots");
  clear(host);
  state.profiles.forEach((witch) => {
    const position = positions[witch.id] || { left: "50%", top: "50%" };
    const button = node("button", {
      className: "hotspot",
      type: "button",
      title: `${witch.name}: ${witch.station}`,
      ariaLabel: `${witch.name}, ${witch.station}`,
      dataset: { selected: witch.id === state.selectedWitch },
      text: witch.name,
    });
    button.style.left = position.left;
    button.style.top = position.top;
    button.addEventListener("click", () => selectWitch(witch.id));
    host.append(button);
  });
}

function selectWitch(id, options = { fetchConversation: true }) {
  const witch = profile(id);
  if (!witch) return;
  rememberMessageDraft(state.selectedWitch);
  state.selectedWitch = id;
  $("selectedWitchName").textContent = witch.name;
  $("dialogueTitle").textContent = witch.name;
  $("witchTitle").textContent = witch.title;
  $("witchRole").textContent = witch.responsibilities;
  $("providerLabel").textContent = witch.providerLabel;
  $("portrait").dataset.witch = witch.id;
  $("portrait").setAttribute("aria-label", `${witch.name} portrait`);
  document.documentElement.style.setProperty("--witch-accent", witch.accent);
  state.game?.setSelected(witch.id);
  renderRoster();
  renderHotspots();
  restoreMessageDraft(id);
  if (options.fetchConversation) refreshConversation(id).catch((error) => setNotice(error.message, "error"));
  else renderTranscript();
}

function rememberMessageDraft(witchId) {
  const input = $("messageInput");
  if (!input || !witchId) return;
  state.messageDrafts[witchId] = input.value;
}

function restoreMessageDraft(witchId) {
  const input = $("messageInput");
  if (!input) return;
  const preservedVoice = state.voiceDrafts[witchId];
  if (preservedVoice) {
    const existing = state.messageDrafts[witchId] || "";
    state.messageDrafts[witchId] = existing ? `${existing.trim()} ${preservedVoice}` : preservedVoice;
    delete state.voiceDrafts[witchId];
    setNotice(`Recovered a voice transcript for ${profile(witchId)?.name || witchId}. Review it before sending.`, "info");
  }
  input.value = state.messageDrafts[witchId] || "";
}

function renderTranscript() {
  const list = $("transcript");
  clear(list);
  const messages = state.conversations[state.selectedWitch] || [];
  if (!messages.length) {
    list.append(node("li", {
      className: "empty-state",
      text: "No messages yet. Conversation is durable local text; task assignment remains separate.",
    }));
    return;
  }
  for (const message of messages) {
    const author = message.author === "user" ? "You" : profile(message.author)?.name || message.author;
    const delivery = message.delivery?.state || "delivered";
    const children = [
      node("b", { text: author }),
      node("p", { text: message.text }),
      node("time", { text: new Date(message.timestamp).toLocaleString() }),
    ];
    if (delivery !== "delivered") {
      const detail = message.delivery?.error || message.delivery?.code || "";
      children.push(node("small", { className: "delivery-state", text: `${statusLabel(delivery)}${detail ? `: ${detail}` : ""}` }));
    }
    list.append(node("li", { className: message.author === "user" ? "message user" : "message witch" }, children));
  }
  list.scrollTop = list.scrollHeight;
}

function statusLabel(status) {
  return String(status || "unknown").replace(/_/g, " ");
}

function renderTasks() {
  $("taskCount").textContent = String(state.tasks.length);
  renderTaskFilters();
  const list = $("taskList");
  const previousScroll = list.scrollTop;
  clear(list);
  const visibleTasks = state.tasks.filter((task) => taskMatchesFilter(task, state.taskFilter));
  if (visibleTasks.length && !visibleTasks.some((task) => task.id === state.selectedTask)) {
    state.selectedTask = visibleTasks[0].id;
  }
  if (!visibleTasks.length) {
    list.append(node("p", { className: "empty-state", text: "No tasks recorded yet." }));
  }
  visibleTasks.forEach((task) => {
    const assignee = profile(task.assignee);
    const button = node("button", {
      className: "task-row",
      type: "button",
      dataset: { status: task.status, selected: task.id === state.selectedTask },
    }, [
      node("span", {
        className: "portrait-crop",
        dataset: { witch: assignee?.id || "morgana" },
        attrs: { "aria-hidden": "true" },
      }),
      node("div", { className: "task-copy" }, [
        node("span", { text: task.title }),
        node("small", { text: `${assignee?.name || task.assignee} - ${statusLabel(task.status)}` }),
      ]),
      node("b", { className: task.mode === "demo" ? "task-mode-badge" : "", text: task.mode === "demo" ? "Demo" : task.priority }),
    ]);
    button.addEventListener("click", () => {
      state.selectedTask = task.id;
      renderTasks();
      renderTaskDetail(task);
    });
    list.append(button);
  });
  list.scrollTop = previousScroll;
  renderRoster();
  if (state.selectedTask) {
    const selected = state.tasks.find((task) => task.id === state.selectedTask);
    if (selected) renderTaskDetail(selected);
  }
}

function taskMatchesFilter(task, filter) {
  if (filter === "active") return ["queued", "running", "needs input", "needs_input", "waiting_for_approval", "stopping", "unknown", "disconnected", "failed"].includes(task.status);
  if (filter === "needs") return ["needs input", "needs_input", "waiting_for_approval"].includes(task.status);
  if (filter === "completed") return task.status === "completed";
  if (filter === "failed") return task.status === "failed";
  return true;
}

function renderTaskFilters() {
  document.querySelectorAll(".journal-tab").forEach((button) => {
    button.setAttribute("aria-selected", String(button.dataset.filter === state.taskFilter));
  });
}

function renderTaskDetail(task) {
  const detail = $("taskDetail");
  const previousScroll = detail.scrollTop;
  clear(detail);
  detail.append(node("h3", { text: task.title }));
  detail.append(node("dl", {}, [
    field("Assignee", profile(task.assignee)?.name || task.assignee),
    field("State", statusLabel(task.status)),
    field("Attempt", task.attemptId || "unknown"),
    field("Mode", task.mode),
    field("Requested runtime", runtimeLabel(task.requestedRuntime)),
    field("Served runtime", runtimeLabel(task.runtime)),
    field("Hermes run", task.hermes?.runId || "unavailable"),
    field("Usage", usageLabel(task.usage)),
    field("Latest update", task.latestUpdate),
  ]));
  if (task.hermes?.idempotencyKey) appendSection(detail, "Recovery", node("p", { text: `Idempotency key retained for uncertain submission recovery: ${task.hermes.idempotencyKey}` }));
  appendSection(detail, "Instructions", node("p", { text: task.instructions || "No additional instructions." }));
  appendSection(detail, "Blockers", listOf(task.blockers, "No blockers."));
  appendSection(detail, "Evidence", listOf(task.evidence, "No evidence recorded yet."));
  appendSection(detail, "Artifacts", artifactList(task.artifacts));
  appendSection(detail, "Timeline", timelineOf(task.timeline));
  if (task.result) appendSection(detail, "Result", node("p", { text: task.result }));
  const actions = taskActions(task);
  if (actions.length) {
    detail.append(node("div", { className: "task-actions" }, actions));
  }
  detail.scrollTop = previousScroll;
}

function taskActions(task) {
  const actions = [];
  const active = ["queued", "running", "waiting_for_approval", "stopping", "unknown", "disconnected"].includes(task.status);
  if (task.mode === "live" && !task.hermes?.runId && ["queued", "unknown", "disconnected"].includes(task.status)) {
    const recover = node("button", { type: "button", text: "Recover submission" });
    recover.addEventListener("click", () => recoverSubmission(task.id));
    actions.push(recover);
  }
  if (task.mode === "live" && Array.isArray(task.artifacts) && task.artifacts.length) {
    const validate = node("button", { type: "button", className: "secondary-button", text: "Validate artifacts" });
    validate.addEventListener("click", () => validateArtifacts(task.id));
    actions.push(validate);
  }
  if (task.mode === "live" && active && task.hermes?.runId && task.status !== "stopping") {
    const stop = node("button", { type: "button", text: "Request stop" });
    stop.addEventListener("click", () => stopTask(task.id));
    actions.push(stop);
  }
  const approvalState = task.approval?.state || "";
  if (task.mode === "live" && (task.status === "waiting_for_approval" || approvalState === "pending")) {
    const approve = node("button", { type: "button", text: "Approve once" });
    approve.addEventListener("click", () => resolveApproval(task.id, "once"));
    const deny = node("button", { type: "button", className: "secondary-button", text: "Deny" });
    deny.addEventListener("click", () => resolveApproval(task.id, "deny"));
    actions.push(approve, deny);
  }
  if (task.status === "failed") {
    const retry = node("button", { type: "button", text: "Retry as new attempt" });
    retry.addEventListener("click", () => retryTask(task.id));
    actions.push(retry);
  }
  return actions;
}

function appendSection(parent, title, content) {
  parent.append(node("h4", { text: title }));
  parent.append(content);
}

function listOf(items, emptyText) {
  const list = node("ul");
  const values = Array.isArray(items) && items.length ? items : [emptyText];
  values.forEach((item) => list.append(node("li", { text: item })));
  return list;
}

function artifactList(items) {
  const list = node("ul");
  const values = Array.isArray(items) && items.length ? items : [];
  if (!values.length) {
    list.append(node("li", { text: "No verified artifact references recorded yet." }));
    return list;
  }
  values.forEach((item) => {
    if (typeof item === "string") {
      list.append(node("li", { text: item }));
      return;
    }
    if (item && typeof item === "object") {
      const path = item.path || item.uri || item.name || "artifact";
      const verified = item.state || (item.exists === true || item.verified === true ? "reported by runtime" : "reported");
      const extra = item.sha256 ? `, sha256 ${item.sha256.slice(0, 12)}` : "";
      list.append(node("li", { text: `${path} (${verified}${extra})` }));
      return;
    }
    list.append(node("li", { text: String(item) }));
  });
  return list;
}

function runtimeLabel(runtime) {
  if (!runtime || typeof runtime !== "object") return "unknown";
  const provider = runtime.provider || runtime.servedProvider || runtime.requestedProvider || "";
  const model = runtime.model || runtime.servedModel || runtime.requestedModel || "";
  const route = runtime.routeMode || runtime.route || "";
  const reason = runtime.reason ? ` - ${runtime.reason}` : "";
  const parts = [route, provider, model].filter(Boolean);
  return `${parts.join(" / ") || "unknown"}${reason}`;
}

function usageLabel(usage) {
  if (!usage || typeof usage !== "object") return "unavailable";
  const parts = [];
  for (const key of ["input_tokens", "output_tokens", "total_tokens", "cost_usd"]) {
    if (usage[key] !== undefined && usage[key] !== null) parts.push(`${key}: ${usage[key]}`);
  }
  return parts.length ? parts.join(", ") : "unavailable";
}

function timelineOf(items) {
  const list = node("ol");
  for (const item of items || []) {
    list.append(node("li", {}, [
      node("b", { text: item.kind }),
      node("span", { text: item.message }),
      node("time", { text: new Date(item.timestamp).toLocaleString() }),
    ]));
  }
  return list;
}

async function sendMessage(event) {
  event.preventDefault();
  const witchId = state.selectedWitch;
  const input = $("messageInput");
  const message = input.value.trim();
  if (!message) return;
  try {
    const payload = await postJson(`/api/conversations/${encodeURIComponent(witchId)}`, { message });
    state.conversations[payload.witchId || witchId] = payload.messages;
    if (state.selectedWitch === witchId) {
      input.value = "";
      state.messageDrafts[witchId] = "";
      renderTranscript();
      speakLatestWitchMessage(payload.messages);
    }
  } catch (error) {
    setNotice(error.message, "error");
  }
}

async function assignTask(event) {
  event.preventDefault();
  if (state.assigningTask) return;
  const assignee = state.selectedWitch;
  state.assigningTask = true;
  state.pendingTaskKey = state.pendingTaskKey || newOperationKey();
  const submitButton = event.submitter || document.querySelector("#taskForm button[type='submit']");
  if (submitButton) submitButton.disabled = true;
  try {
    const payload = await postJson("/api/tasks", {
      assignee,
      title: $("taskTitle").value,
      instructions: $("taskInstructions").value,
      priority: $("taskPriority").value,
      routeMode: $("routeMode").value,
      provider: $("taskProvider").value,
      model: $("taskModel").value,
      idempotencyKey: state.pendingTaskKey,
    });
    replaceTask(payload.task);
    $("taskTitle").value = "";
    $("taskInstructions").value = "";
    $("taskProvider").value = "";
    $("taskModel").value = "";
    renderTasks();
    setNotice("Task queued. The journal will update as runtime events arrive.", "info");
    state.pendingTaskKey = null;
  } catch (error) {
    setNotice(error.message, "error");
  } finally {
    state.assigningTask = false;
    if (submitButton) submitButton.disabled = false;
  }
}

function newOperationKey() {
  if (window.crypto?.randomUUID) return `coven-${window.crypto.randomUUID()}`;
  return `coven-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

async function retryTask(taskId) {
  try {
    const payload = await postJson(`/api/tasks/${encodeURIComponent(taskId)}/retry`, {});
    state.tasks.unshift(payload.task);
    state.selectedTask = payload.task.id;
    renderTasks();
    closeFailureOverlay();
    setNotice("Retry was created as a separate tracked attempt.", "info");
  } catch (error) {
    setNotice(error.message, "error");
  }
}

async function stopTask(taskId) {
  try {
    const payload = await postJson(`/api/tasks/${encodeURIComponent(taskId)}/stop`, {});
    replaceTask(payload.task);
    renderTasks();
    setNotice("Stop requested. Coven will keep reconciling the run until Hermes confirms the terminal state.", "info");
  } catch (error) {
    setNotice(error.message, "error");
  }
}

async function recoverSubmission(taskId) {
  try {
    const payload = await postJson(`/api/tasks/${encodeURIComponent(taskId)}/recover-submission`, {});
    replaceTask(payload.task);
    renderTasks();
    setNotice("Submission recovery replayed the original request with the retained idempotency key.", "info");
  } catch (error) {
    setNotice(error.message, "error");
  }
}

async function validateArtifacts(taskId) {
  try {
    const payload = await postJson(`/api/tasks/${encodeURIComponent(taskId)}/validate-artifacts`, {});
    replaceTask(payload.task);
    renderTasks();
    setNotice("Artifact claims were inspected against configured workspace roots.", "info");
  } catch (error) {
    setNotice(error.message, "error");
  }
}

async function resolveApproval(taskId, decision) {
  try {
    const payload = await postJson(`/api/tasks/${encodeURIComponent(taskId)}/approval`, { decision });
    replaceTask(payload.task);
    renderTasks();
    setNotice(`Approval decision sent: ${decision}.`, "info");
  } catch (error) {
    setNotice(error.message, "error");
  }
}

function replaceTask(task) {
  if (!task) return;
  const index = state.tasks.findIndex((item) => item.id === task.id);
  if (index >= 0) state.tasks.splice(index, 1, task);
  else state.tasks.unshift(task);
  state.selectedTask = task.id;
}

async function startVoiceCapture() {
  if (state.recording) return;
  if (state.voiceStatus?.state !== "ready") {
    setNotice(voiceSummary(), "warn");
    return;
  }
  stopSpeech();
  const started = await postJson("/api/voice/start", {
    witchId: state.selectedWitch,
    inputMode: $("voiceMode").value,
    view: state.activeView,
  });
  const session = started.session;
  const recording = {
    sessionId: session.id,
    generation: session.generation,
    witchId: session.witchId,
    inputMode: session.inputMode,
    chunks: [],
    sampleRate: 0,
    startedAt: Date.now(),
    busy: true,
    cancelled: false,
    label: `Listening for ${profile(session.witchId)?.name || session.witchId}`,
    stream: null,
    audioContext: null,
    source: null,
    processor: null,
    timer: null,
    pollTimer: null,
  };
  state.recording = recording;
  updateVoiceAvailability();
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true }, video: false });
    if (state.recording !== recording || recording.cancelled) {
      stream.getTracks().forEach((track) => track.stop());
      return;
    }
    const AudioContext = window.AudioContext || window.webkitAudioContext;
    const audioContext = new AudioContext();
    const source = audioContext.createMediaStreamSource(stream);
    const processor = audioContext.createScriptProcessor(4096, 1, 1);
    processor.onaudioprocess = (event) => {
      if (state.recording !== recording || recording.cancelled) return;
      const input = event.inputBuffer.getChannelData(0);
      recording.chunks.push(new Float32Array(input));
      event.outputBuffer.getChannelData(0).fill(0);
    };
    source.connect(processor);
    processor.connect(audioContext.destination);
    Object.assign(recording, {
      stream,
      audioContext,
      source,
      processor,
      sampleRate: audioContext.sampleRate,
      busy: false,
    });
    recording.timer = window.setInterval(() => updateVoiceElapsed(recording), 250);
    window.setTimeout(() => {
      if (state.recording === recording && !recording.cancelled) finishVoiceCapture().catch((error) => setNotice(error.message, "error"));
    }, (state.voiceStatus?.maxDurationSeconds || 60) * 1000);
    updateVoiceElapsed(recording);
    setNotice("Recording locally. Release or press Finish when ready.", "info");
  } catch (error) {
    await cancelVoiceInput("Microphone capture failed or was denied.");
    setNotice(`Microphone capture failed: ${error.message || error}.`, "error");
  } finally {
    updateVoiceAvailability();
  }
}

async function finishVoiceCapture() {
  const recording = state.recording;
  if (!recording || recording.busy) return;
  recording.busy = true;
  recording.label = "Transcribing locally...";
  updateVoiceAvailability();
  cleanupVoiceCapture(recording, { keepChunks: true });
  const durationMs = Date.now() - recording.startedAt;
  if (durationMs < 250 || !recording.chunks.length) {
    await cancelVoiceInput("Recording was too short.");
    setNotice("Recording was too short to transcribe.", "warn");
    return;
  }
  const wav = encodeWav(recording.chunks, recording.sampleRate || 48000, 16000);
  try {
    await postBinary(`/api/voice/sessions/${encodeURIComponent(recording.sessionId)}/audio`, wav, {
      "Content-Type": "audio/wav",
      "X-Coven-Voice-Generation": String(recording.generation),
    });
    recording.chunks = [];
    pollVoiceResult(recording);
  } catch (error) {
    if (state.recording === recording) state.recording = null;
    setNotice(error.message, "error");
    updateVoiceAvailability();
  }
}

async function cancelVoiceInput(reason = "Voice input cancelled.") {
  const recording = state.recording;
  if (!recording) return;
  recording.cancelled = true;
  cleanupVoiceCapture(recording);
  state.recording = null;
  updateVoiceAvailability();
  try {
    await postJson(`/api/voice/sessions/${encodeURIComponent(recording.sessionId)}/cancel`, { generation: recording.generation });
  } catch (_error) {
    // Cancellation is best effort after local invalidation.
  }
  setNotice(reason, "warn");
}

function cleanupVoiceCapture(recording, { keepChunks = false } = {}) {
  if (recording.timer) window.clearInterval(recording.timer);
  if (recording.pollTimer) window.clearTimeout(recording.pollTimer);
  if (recording.processor) recording.processor.disconnect();
  if (recording.source) recording.source.disconnect();
  if (recording.stream) recording.stream.getTracks().forEach((track) => track.stop());
  if (recording.audioContext) recording.audioContext.close().catch(() => {});
  if (!keepChunks) recording.chunks = [];
  $("voiceElapsed").textContent = "00:00";
}

function updateVoiceElapsed(recording) {
  if (state.recording !== recording) return;
  const seconds = Math.floor((Date.now() - recording.startedAt) / 1000);
  const minutes = Math.floor(seconds / 60);
  $("voiceElapsed").textContent = `${String(minutes).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;
}

async function pollVoiceResult(recording) {
  if (state.recording !== recording || recording.cancelled) return;
  try {
    const payload = await api(`/api/voice/sessions/${encodeURIComponent(recording.sessionId)}`);
    const session = payload.session;
    if (state.recording !== recording || session.generation !== recording.generation) return;
    recording.label = statusLabel(session.state);
    updateVoiceAvailability();
    if (session.state === "transcript_ready") {
      state.recording = null;
      applyVoiceResult(session);
      updateVoiceAvailability();
      return;
    }
    if (session.state === "cancelled" || session.state === "error") {
      state.recording = null;
      setNotice(session.error?.message || "Voice input did not produce a transcript.", "warn");
      updateVoiceAvailability();
      return;
    }
    recording.pollTimer = window.setTimeout(() => pollVoiceResult(recording), 800);
  } catch (error) {
    if (state.recording === recording) {
      state.recording = null;
      setNotice(error.message, "error");
      updateVoiceAvailability();
    }
  }
}

function applyVoiceResult(session) {
  const result = session.result || {};
  const transcript = result.transcript || "";
  const command = result.command || { action: "draft_message", text: transcript };
  if (command.action === "select_witch" && command.witchId) {
    selectWitch(command.witchId);
    setNotice(command.reason || "Selected witch.", "info");
    return;
  }
  if (command.action === "open_view" && command.view) {
    setActiveView(command.view);
    setNotice(command.reason || "Opened view.", "info");
    return;
  }
  if (command.action === "show_tasks") {
    selectWitch(command.witchId || session.witchId);
    setActiveView("journal");
    const task = state.tasks.find((item) => item.assignee === (command.witchId || session.witchId));
    if (task) state.selectedTask = task.id;
    renderTasks();
    setNotice(command.reason || "Opened tasks.", "info");
    return;
  }
  if (command.action === "stop_speaking") {
    stopSpeech();
    setNotice(command.reason || "Stopped speech.", "info");
    return;
  }
  if (command.action === "draft_task" || $("voiceMode").value === "task") {
    const witchId = command.witchId || session.witchId;
    if (witchId && witchId !== state.selectedWitch) selectWitch(witchId);
    $("taskTitle").value = command.title || transcript.slice(0, 88) || "Voice task draft";
    $("taskInstructions").value = command.instructions || transcript;
    setActiveView("sanctuary");
    setNotice(`${command.reason || "Prepared editable task draft."}${command.integration ? ` ${statusLabel(command.integration)} readiness is shown in Settings.` : ""}`, "info");
    $("taskTitle").focus();
    return;
  }
  receiveVoiceTranscript(session.witchId, command.text || transcript);
  setNotice(command.reason || "Transcript is ready for review.", "info");
}

function encodeWav(chunks, sourceRate, targetRate) {
  const samples = flattenAudio(chunks);
  const resampled = resample(samples, sourceRate, targetRate);
  const dataBytes = resampled.length * 2;
  const buffer = new ArrayBuffer(44 + dataBytes);
  const view = new DataView(buffer);
  writeString(view, 0, "RIFF");
  view.setUint32(4, 36 + dataBytes, true);
  writeString(view, 8, "WAVE");
  writeString(view, 12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, targetRate, true);
  view.setUint32(28, targetRate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  writeString(view, 36, "data");
  view.setUint32(40, dataBytes, true);
  let offset = 44;
  for (const sample of resampled) {
    const clamped = Math.max(-1, Math.min(1, sample));
    view.setInt16(offset, clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff, true);
    offset += 2;
  }
  return new Blob([buffer], { type: "audio/wav" });
}

function flattenAudio(chunks) {
  const length = chunks.reduce((total, chunk) => total + chunk.length, 0);
  const output = new Float32Array(length);
  let offset = 0;
  for (const chunk of chunks) {
    output.set(chunk, offset);
    offset += chunk.length;
  }
  return output;
}

function resample(samples, sourceRate, targetRate) {
  if (sourceRate === targetRate) return samples;
  const ratio = sourceRate / targetRate;
  const length = Math.floor(samples.length / ratio);
  const output = new Float32Array(length);
  for (let index = 0; index < length; index += 1) {
    const sourceIndex = index * ratio;
    const before = Math.floor(sourceIndex);
    const after = Math.min(before + 1, samples.length - 1);
    const weight = sourceIndex - before;
    output[index] = samples[before] * (1 - weight) + samples[after] * weight;
  }
  return output;
}

function writeString(view, offset, text) {
  for (let index = 0; index < text.length; index += 1) {
    view.setUint8(offset + index, text.charCodeAt(index));
  }
}

function renderVoiceCommands() {
  const list = $("voiceCommandList");
  if (!list) return;
  clear(list);
  for (const command of state.voiceCommands) {
    list.append(node("li", {}, [node("b", { text: command.phrase }), node("span", { text: command.action })]));
  }
}

function updateVoiceAvailability() {
  const ready = state.voiceStatus?.state === "ready";
  const captureAvailable = Boolean(navigator.mediaDevices?.getUserMedia && (window.AudioContext || window.webkitAudioContext));
  $("recordButton").disabled = !ready || !captureAvailable || Boolean(state.recording?.busy);
  $("recordButton").textContent = state.recording ? "Finish recording" : (ready && captureAvailable ? "Push to talk" : "Voice unavailable");
  $("cancelVoiceButton").disabled = !state.recording;
  $("voiceState").textContent = state.recording?.label || voiceSummary();
  $("stopSpeakingButton").disabled = !("speechSynthesis" in window);
}

async function toggleRecording() {
  if (state.recording) {
    await finishVoiceCapture();
    return;
  }
  await startVoiceCapture();
}

function receiveVoiceTranscript(witchId, transcript) {
  const text = transcript.trim();
  if (!text) return;
  if (witchId === state.selectedWitch) {
    const input = $("messageInput");
    input.value = input.value ? `${input.value.trim()} ${text}` : text;
    input.focus();
    $("voiceState").textContent = "Transcript ready for review";
    return;
  }
  state.voiceDrafts[witchId] = state.voiceDrafts[witchId] ? `${state.voiceDrafts[witchId]} ${text}` : text;
  setNotice(`Voice transcript was preserved for ${profile(witchId)?.name || witchId}; switch back to review it.`, "warn");
}

function stopSpeech() {
  if ("speechSynthesis" in window) window.speechSynthesis.cancel();
  $("voiceState").textContent = "Speech stopped";
}

function speakLatestWitchMessage(messages) {
  if (state.settings.mute || !("speechSynthesis" in window)) return;
  const latest = [...(messages || [])].reverse().find((message) => message.author !== "user");
  if (!latest?.text) return;
  if (latest.id && state.lastSpokenMessageId === latest.id) return;
  state.lastSpokenMessageId = latest.id || null;
  window.speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(latest.text);
  utterance.rate = 0.94;
  utterance.pitch = 0.92;
  utterance.addEventListener("end", () => {
    if ($("voiceState").textContent === "Speaking") $("voiceState").textContent = "Speech complete";
  });
  utterance.addEventListener("error", () => {
    $("voiceState").textContent = "Speech unavailable";
  });
  window.speechSynthesis.speak(utterance);
  $("voiceState").textContent = "Speaking";
}

function clearCinematicTimer() {
  if (state.cinematicTimer) {
    window.clearTimeout(state.cinematicTimer);
    state.cinematicTimer = null;
  }
}

function maybePlayFailure() {
  if (state.currentFailure || state.skipAllFailures || !state.settings.cinematicsEnabled) return;
  if (document.hidden || state.recording || isTypingSensitive()) return;
  const event = state.failureQueue.shift();
  if (!event) return;
  state.currentFailure = event;
  openFailureOverlay(event);
}

function openFailureOverlay(event) {
  clearCinematicTimer();
  const overlay = $("failureOverlay");
  const scene = $("riverScene");
  const report = $("failureReport");
  const mode = state.settings.reducedMotionMode;
  overlay.hidden = false;
  report.hidden = true;
  scene.hidden = false;
  scene.className = "river-scene";
  $("failureTitle").textContent = event.title;
  $("failedAssignee").textContent = profile(event.assignee)?.name || event.assignee;
  $("failedError").textContent = event.error || "No error supplied by the runtime event.";
  $("failedStep").textContent = event.lastSuccessfulStep || "No checkpoint supplied.";

  if (mode === "off") {
    finishFailureScene("skipped", event.eventId);
    return;
  }
  if (mode === "tableau" || window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
    scene.classList.add("tableau");
    state.cinematicTimer = window.setTimeout(() => finishFailureScene("shown", event.eventId), sceneDurationForMotion(mode, true));
    return;
  }
  scene.classList.add("playing");
  state.cinematicTimer = window.setTimeout(() => finishFailureScene("shown", event.eventId), sceneDurationForMotion(mode, false));
}

async function markCinematic(eventId, disposition) {
  return postJson("/api/cinematics", { eventId, disposition });
}

async function finishFailureScene(disposition, eventId = state.currentFailure?.eventId) {
  if (!state.currentFailure || eventId !== state.currentFailure.eventId) return;
  clearCinematicTimer();
  $("riverScene").hidden = true;
  $("failureReport").hidden = false;
  try {
    await markCinematic(eventId, disposition);
  } catch (error) {
    setNotice(error.message, "error");
  }
}

function closeFailureOverlay() {
  clearCinematicTimer();
  $("failureOverlay").hidden = true;
  const lastTask = state.currentFailure?.taskId;
  state.currentFailure = null;
  if (lastTask) {
    const selected = document.querySelector(`[data-status][data-selected="true"]`) || $("taskDetail");
    selected?.focus?.({ preventScroll: true });
  }
  maybePlayFailure();
}

function inspectCurrentFailure() {
  if (!state.currentFailure) return;
  state.selectedTask = state.currentFailure.taskId;
  const task = state.tasks.find((item) => item.id === state.selectedTask);
  if (task) renderTaskDetail(task);
  closeFailureOverlay();
}

async function skipAllFailures() {
  state.skipAllFailures = true;
  const currentId = state.currentFailure?.eventId;
  if (currentId) await finishFailureScene("skipped", currentId);
  const queued = state.failureQueue.splice(0);
  await Promise.allSettled(queued.map((event) => markCinematic(event.eventId, "skipped")));
}

function reassignCurrentFailure() {
  selectWitch("morgana");
  closeFailureOverlay();
  setNotice("Morgana is selected. Reassignment remains advisory until live Hermes dispatch is wired.", "info");
}

function setActiveView(view) {
  state.activeView = view;
  document.querySelectorAll(".tab-button").forEach((button) => {
    button.setAttribute("aria-selected", String(button.dataset.view === view));
  });
  $("settingsPanel").hidden = view !== "settings";
  if (view === "journal") {
    $("journalTitle").scrollIntoView({ block: "start", behavior: "smooth" });
  } else if (view === "sanctuary") {
    $("sanctuaryTitle").scrollIntoView({ block: "start", behavior: "smooth" });
  } else if (view === "settings") {
    $("settingsTitle").scrollIntoView({ block: "start", behavior: "smooth" });
  }
}

function bindEvents() {
  $("messageForm").addEventListener("submit", sendMessage);
  $("messageInput").addEventListener("input", () => rememberMessageDraft(state.selectedWitch));
  $("taskForm").addEventListener("submit", assignTask);
  $("recordButton").addEventListener("click", (event) => {
    if (event.currentTarget.dataset.pointerConsumed === "true") {
      event.currentTarget.dataset.pointerConsumed = "";
      return;
    }
    toggleRecording().catch((error) => setNotice(error.message, "error"));
  });
  $("recordButton").addEventListener("pointerdown", (event) => {
    if (event.pointerType === "mouse" && event.button !== 0) return;
    if (state.recording || isTypingSensitive()) return;
    event.currentTarget.dataset.pointerStarted = "pending";
    const button = event.currentTarget;
    state.voiceHoldTimer = window.setTimeout(() => {
      if (button.dataset.pointerStarted !== "pending") return;
      button.dataset.pointerStarted = "active";
      startVoiceCapture().catch((error) => setNotice(error.message, "error"));
    }, 220);
  });
  $("recordButton").addEventListener("pointerup", (event) => {
    if (state.voiceHoldTimer) window.clearTimeout(state.voiceHoldTimer);
    if (event.currentTarget.dataset.pointerStarted === "active") {
      event.currentTarget.dataset.pointerConsumed = "true";
      if (state.recording) finishVoiceCapture().catch((error) => setNotice(error.message, "error"));
    }
    event.currentTarget.dataset.pointerStarted = "";
  });
  $("recordButton").addEventListener("pointerleave", (event) => {
    if (state.voiceHoldTimer) window.clearTimeout(state.voiceHoldTimer);
    if (event.currentTarget.dataset.pointerStarted === "active" && state.recording) {
      event.currentTarget.dataset.pointerStarted = "";
      cancelVoiceInput("Voice input cancelled.").catch((error) => setNotice(error.message, "error"));
    }
  });
  $("cancelVoiceButton").addEventListener("click", () => cancelVoiceInput("Voice input cancelled.").catch((error) => setNotice(error.message, "error")));
  $("stopSpeakingButton").addEventListener("click", stopSpeech);
  $("compactToggle").addEventListener("click", () => {
    state.compact = !state.compact;
    $("workspace").classList.toggle("compact", state.compact);
    $("compactToggle").textContent = state.compact ? "Sanctuary view" : "Compact view";
  });
  document.querySelectorAll(".tab-button").forEach((button) => {
    button.addEventListener("click", () => setActiveView(button.dataset.view || "sanctuary"));
  });
  $("dismissOnboarding").addEventListener("click", () => document.querySelector(".onboarding-panel")?.classList.add("dismissed"));
  $("refreshSetupButton").addEventListener("click", () => refreshSetupStatus().catch((error) => setNotice(error.message, "error")));
  $("exploreDemoButton").addEventListener("click", () => chooseSetupMode("demo"));
  $("liveSetupButton").addEventListener("click", () => chooseSetupMode("live"));
  $("providerSetupForm").addEventListener("submit", saveProviderCredential);
  $("removeProviderButton").addEventListener("click", removeProviderCredential);
  $("workspaceSetupForm").addEventListener("submit", saveWorkspace);
  $("chooseWorkspaceButton").addEventListener("click", () => chooseWorkspaceFolder().catch((error) => setNotice(error.message, "error")));
  $("repairComponentsButton").addEventListener("click", repairComponents);
  $("checkUpdatesButton").addEventListener("click", checkForUpdates);
  $("supportBundleButton").addEventListener("click", exportSupportBundle);
  $("completeSetupButton").addEventListener("click", completeSetup);
  document.querySelectorAll(".journal-tab").forEach((button) => {
    button.addEventListener("click", () => {
      state.taskFilter = button.dataset.filter || "all";
      renderTasks();
    });
  });
  $("toggleMute").addEventListener("change", (event) => updateSettings({ mute: event.target.checked }).catch((error) => setNotice(error.message, "error")));
  $("toggleCinematics").addEventListener("change", (event) => updateSettings({ cinematicsEnabled: event.target.checked }).catch((error) => setNotice(error.message, "error")));
  $("motionMode").addEventListener("change", (event) => updateSettings({ reducedMotionMode: event.target.value }).catch((error) => setNotice(error.message, "error")));
  $("qualityMode").addEventListener("change", (event) => updateSettings({ animationQuality: event.target.value }).catch((error) => setNotice(error.message, "error")));
  $("journalMuteToggle").addEventListener("click", () => updateSettings({ mute: !state.settings.mute }).catch((error) => setNotice(error.message, "error")));
  $("journalFailureToggle").addEventListener("click", () => updateSettings({ cinematicsEnabled: !state.settings.cinematicsEnabled }).catch((error) => setNotice(error.message, "error")));
  $("journalMotionToggle").addEventListener("click", () => {
    const modes = ["full", "tableau", "off"];
    const next = modes[(modes.indexOf(state.settings.reducedMotionMode) + 1) % modes.length] || "tableau";
    updateSettings({ reducedMotionMode: next }).catch((error) => setNotice(error.message, "error"));
  });
  $("skipSceneButton").addEventListener("click", () => finishFailureScene("skipped"));
  $("skipAllButton").addEventListener("click", () => skipAllFailures().catch((error) => setNotice(error.message, "error")));
  $("inspectFailureButton").addEventListener("click", inspectCurrentFailure);
  $("retryFailureButton").addEventListener("click", () => state.currentFailure && retryTask(state.currentFailure.taskId));
  $("reassignFailureButton").addEventListener("click", reassignCurrentFailure);
  $("returnFailureButton").addEventListener("click", closeFailureOverlay);
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !$("failureOverlay").hidden) {
      finishFailureScene("skipped");
    }
  });
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) clearCinematicTimer();
    scheduleRefresh(document.hidden ? 10000 : 0);
    if (!document.hidden) maybePlayFailure();
  });
}

async function refreshAll({ forceRuntime = false } = {}) {
  if (state.refreshInFlight) return;
  state.refreshInFlight = true;
  const position = captureUiPosition();
  try {
    await refreshStatus(forceRuntime);
    await refreshSetupStatus();
    await refreshVoiceStatus();
    await refreshSettings();
    await refreshTasks();
    await refreshFailures();
    state.refreshBackoffMs = 1500;
  } catch (error) {
    setNotice(error.message, "error");
    state.refreshBackoffMs = Math.min(state.refreshBackoffMs * 1.6, 12000);
  } finally {
    state.refreshInFlight = false;
    restoreUiPosition(position);
    scheduleRefresh();
  }
}

function scheduleRefresh(delay) {
  if (state.refreshTimer) window.clearTimeout(state.refreshTimer);
  const nextDelay = delay ?? (document.hidden ? 10000 : state.refreshBackoffMs);
  state.refreshTimer = window.setTimeout(() => refreshAll(), nextDelay);
}

async function init() {
  bindEvents();
  updateVoiceAvailability();
  const prompt = $("interactionPrompt");
  state.game = createSanctuaryGame($("sanctuaryCanvas"), {
    onPrompt(message) {
      if (!prompt) return;
      prompt.hidden = !message;
      prompt.textContent = message;
    },
  });
  $("sanctuaryCanvas").addEventListener("coven-select-witch", (event) => selectWitch(event.detail.id));
  await refreshStatus();
  await refreshSetupStatus();
  await refreshVoiceStatus();
  await refreshSettings();
  await refreshProfiles();
  await refreshConversation();
  await refreshTasks();
  await refreshFailures();
  scheduleRefresh();
}

init().catch((error) => setNotice(error.message, "error"));
