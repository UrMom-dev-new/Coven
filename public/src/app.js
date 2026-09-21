import { api, postJson } from "./api.js";
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
  compact: false,
  taskFilter: "all",
  activeView: "sanctuary",
  game: null,
  refreshTimer: null,
  refreshInFlight: false,
  refreshBackoffMs: 1500,
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
    ["Hermes", state.status.hermes?.operational ? "CLI operational." : "Not operational yet."],
    ["Hermes API", state.status.hermesApi?.configured ? "API transport configured." : "API transport not configured."],
    ["Ollama", state.status.ollama?.operational ? "Local service reachable." : "Local service unavailable."],
    ["OpenAI", state.status.openai?.configured ? "API key environment variable found." : "API key not configured."],
    ["Hardware", `${state.status.hardware?.system || "unknown"} ${state.status.hardware?.machine || ""}, ${state.status.hardware?.memory || "memory unknown"}`],
    ["Workspace", "Workspace selection is pending the full desktop onboarding flow."],
    ["Voice", "Text-first path active; voice setup is a later gate."],
  ];
  for (const [title, text] of items) {
    host.append(node("div", { className: "check-item" }, [node("b", { text: title }), node("span", { text })]));
  }
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
  $("taskingState").textContent = state.status.demoMode ? "Explicit demo mode" : "Live Hermes required";
  document.body.dataset.connection = state.status.connection;
  if (!state.status.demoMode && state.status.connection === "disconnected") {
    setNotice("Hermes is not operational for this app namespace. Live task dispatch is disabled until configured.", "warn");
  } else if (state.status.demoMode) {
    setNotice("Demo mode is active. Fixture tasks are isolated from the future live Hermes namespace.", "warn");
  } else {
    setNotice("Hermes was detected. Live dispatch remains an adapter gate in this foundation build.", "info");
  }
  renderOnboarding();
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
  const active = state.tasks.filter((task) => task.assignee === witchId && ["queued", "running", "needs input", "awaiting authorization"].includes(task.status)).length;
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
  if (options.fetchConversation) refreshConversation(id).catch((error) => setNotice(error.message, "error"));
  else renderTranscript();
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
    list.append(node("li", { className: message.author === "user" ? "message user" : "message witch" }, [
      node("b", { text: author }),
      node("p", { text: message.text }),
      node("time", { text: new Date(message.timestamp).toLocaleString() }),
    ]));
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
  if (filter === "active") return ["queued", "running", "needs input", "needs_input", "awaiting authorization", "awaiting_authorization", "failed"].includes(task.status);
  if (filter === "needs") return ["needs input", "needs_input", "awaiting authorization", "awaiting_authorization"].includes(task.status);
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
    field("Mode", task.mode),
    field("Latest update", task.latestUpdate),
  ]));
  appendSection(detail, "Instructions", node("p", { text: task.instructions || "No additional instructions." }));
  appendSection(detail, "Blockers", listOf(task.blockers, "No blockers."));
  appendSection(detail, "Evidence", listOf(task.evidence, "No evidence recorded yet."));
  appendSection(detail, "Timeline", timelineOf(task.timeline));
  if (task.result) appendSection(detail, "Result", node("p", { text: task.result }));
  if (task.status === "failed") {
    const retry = node("button", { type: "button", text: "Retry as new attempt" });
    retry.addEventListener("click", () => retryTask(task.id));
    detail.append(retry);
  }
  detail.scrollTop = previousScroll;
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
      renderTranscript();
      speakLatestWitchMessage(payload.messages);
    }
  } catch (error) {
    setNotice(error.message, "error");
  }
}

async function assignTask(event) {
  event.preventDefault();
  const assignee = state.selectedWitch;
  try {
    const payload = await postJson("/api/tasks", {
      assignee,
      title: $("taskTitle").value,
      instructions: $("taskInstructions").value,
      priority: $("taskPriority").value,
    });
    state.tasks.unshift(payload.task);
    state.selectedTask = payload.task.id;
    $("taskTitle").value = "";
    $("taskInstructions").value = "";
    renderTasks();
    setNotice("Task queued. The journal will update as runtime events arrive.", "info");
  } catch (error) {
    setNotice(error.message, "error");
  }
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

function updateVoiceAvailability() {
  const Recognition = speechRecognitionConstructor();
  $("recordButton").disabled = !Recognition;
  $("recordButton").textContent = Recognition ? "Push to talk" : "Voice unavailable";
  $("voiceState").textContent = Recognition ? "Voice ready" : "Voice unavailable in this WebView";
  $("stopSpeakingButton").disabled = !("speechSynthesis" in window);
}

function speechRecognitionConstructor() {
  return window.SpeechRecognition || window.webkitSpeechRecognition || null;
}

function toggleRecording() {
  if (state.recording) {
    state.recording.stop();
    return;
  }
  const Recognition = speechRecognitionConstructor();
  if (!Recognition) {
    setNotice("This browser/WebView does not expose speech recognition. Text workflows are fully available.", "warn");
    return;
  }
  const recognition = new Recognition();
  recognition.lang = "en-US";
  recognition.continuous = false;
  recognition.interimResults = false;
  recognition.maxAlternatives = 1;
  state.recording = recognition;
  $("recordButton").textContent = "Listening...";
  $("voiceState").textContent = "Listening";
  recognition.addEventListener("result", (event) => {
    const transcript = Array.from(event.results)
      .map((result) => result[0]?.transcript || "")
      .join(" ")
      .trim();
    if (transcript) {
      const input = $("messageInput");
      input.value = input.value ? `${input.value.trim()} ${transcript}` : transcript;
      input.focus();
      $("voiceState").textContent = "Transcript ready";
    }
  });
  recognition.addEventListener("error", (event) => {
    setNotice(`Voice recognition failed: ${event.error || "unknown error"}.`, "warn");
  });
  recognition.addEventListener("end", () => {
    state.recording = null;
    $("recordButton").textContent = "Push to talk";
    if ($("voiceState").textContent === "Listening") $("voiceState").textContent = "Voice ready";
  });
  recognition.start();
}

function stopSpeech() {
  if (state.recording) state.recording.stop();
  if ("speechSynthesis" in window) window.speechSynthesis.cancel();
  $("voiceState").textContent = "Speech stopped";
}

function speakLatestWitchMessage(messages) {
  if (state.settings.mute || !("speechSynthesis" in window)) return;
  const latest = [...(messages || [])].reverse().find((message) => message.author !== "user");
  if (!latest?.text) return;
  window.speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(latest.text);
  utterance.rate = 0.94;
  utterance.pitch = 0.92;
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
  $("taskForm").addEventListener("submit", assignTask);
  $("recordButton").addEventListener("click", toggleRecording);
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
  await refreshSettings();
  await refreshProfiles();
  await refreshConversation();
  await refreshTasks();
  await refreshFailures();
  scheduleRefresh();
}

init().catch((error) => setNotice(error.message, "error"));
