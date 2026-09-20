const state = {
  profiles: [],
  selectedWitch: "morgana",
  selectedTask: null,
  tasks: [],
  status: null,
  conversations: {},
  failureQueue: [],
  currentFailure: null,
  skipAllFailures: false,
  recording: null,
  compact: false,
};

const positions = {
  morgana: { left: "49%", top: "68%" },
  sybil: { left: "50%", top: "37%" },
  circe: { left: "27%", top: "58%" },
  hecate: { left: "71%", top: "58%" },
  selene: { left: "14%", top: "59%" },
  ophelia: { left: "82%", top: "54%" },
};

const $ = (id) => document.getElementById(id);

function profile(id = state.selectedWitch) {
  return state.profiles.find((item) => item.id === id) || state.profiles[0];
}

async function api(path, options = {}) {
  const headers = options.headers || {};
  if (options.body && !headers["Content-Type"]) headers["Content-Type"] = "application/json";
  if (options.method && options.method !== "GET") headers["X-Coven-Intent"] = "ui-action";
  const response = await fetch(path, { ...options, headers });
  const payload = await response.json();
  if (!response.ok) {
    const error = new Error(payload.error || "Request failed");
    error.payload = payload;
    error.status = response.status;
    throw error;
  }
  return payload;
}

function setNotice(message, tone = "info") {
  const notice = $("systemNotice");
  notice.textContent = message || "";
  notice.dataset.tone = tone;
}

async function refreshStatus() {
  state.status = await api("/api/status");
  $("connectionState").textContent = state.status.connection;
  $("runtimeRoute").textContent = state.status.routing.taskRuntime;
  $("providerRoute").textContent = `${state.status.routing.localModel} / ${state.status.routing.apiModel}`;
  $("taskingState").textContent = state.status.demoMode ? "Explicit demo mode" : "Live Hermes required";
  if (!state.status.demoMode && state.status.connection === "disconnected") {
    setNotice("Hermes is not available on PATH. Live task dispatch is disabled. Start with COVEN_DEMO_MODE=1 only for fixture testing.", "warn");
  } else if (state.status.demoMode) {
    setNotice("Demo mode is active. Fixture tasks are separate from Hermes and are labeled as demo data.", "warn");
  } else {
    setNotice("Hermes was detected. Live dispatch still requires completing the adapter contract.", "info");
  }
}

async function refreshProfiles() {
  const payload = await api("/api/profiles");
  state.profiles = payload.witches;
  renderRoster();
  renderHotspots();
  selectWitch(state.selectedWitch);
}

async function refreshTasks() {
  const payload = await api("/api/tasks");
  state.tasks = payload.tasks;
  renderTasks();
}

async function refreshConversation(witchId = state.selectedWitch) {
  const payload = await api(`/api/conversations/${encodeURIComponent(witchId)}`);
  state.conversations[witchId] = payload.messages;
  renderTranscript();
}

async function refreshFailures() {
  const payload = await api("/api/failure-events");
  for (const event of payload.events) {
    if (!state.failureQueue.some((item) => item.eventId === event.eventId) && state.currentFailure?.eventId !== event.eventId) {
      state.failureQueue.push(event);
    }
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
  roster.innerHTML = "";
  state.profiles.forEach((witch) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "roster-button";
    button.dataset.selected = String(witch.id === state.selectedWitch);
    button.innerHTML = `<span>${witch.name}</span><small>${witch.title}</small><b>${runtimeStateFor(witch.id)}</b>`;
    button.addEventListener("click", () => selectWitch(witch.id));
    roster.appendChild(button);
  });
}

function renderHotspots() {
  const host = $("hotspots");
  host.innerHTML = "";
  state.profiles.forEach((witch) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "hotspot";
    button.style.left = positions[witch.id].left;
    button.style.top = positions[witch.id].top;
    button.title = `${witch.name}: ${witch.station}`;
    button.ariaLabel = `${witch.name}, ${witch.station}`;
    button.dataset.selected = String(witch.id === state.selectedWitch);
    button.addEventListener("click", () => selectWitch(witch.id));
    button.textContent = witch.name[0];
    host.appendChild(button);
  });
}

function selectWitch(id) {
  state.selectedWitch = id;
  const witch = profile(id);
  if (!witch) return;
  $("selectedWitchName").textContent = witch.name;
  $("dialogueTitle").textContent = witch.name;
  $("witchTitle").textContent = witch.title;
  $("witchRole").textContent = witch.responsibilities;
  $("providerLabel").textContent = witch.providerLabel;
  $("portrait").src = witch.asset;
  $("portrait").alt = `${witch.name} portrait`;
  document.documentElement.style.setProperty("--witch-accent", witch.accent);
  renderRoster();
  renderHotspots();
  refreshConversation(id).catch((error) => setNotice(error.message, "error"));
}

function renderTranscript() {
  const list = $("transcript");
  const messages = state.conversations[state.selectedWitch] || [];
  list.innerHTML = "";
  if (!messages.length) {
    const empty = document.createElement("li");
    empty.className = "empty-state";
    empty.textContent = "No messages yet. Conversation is durable local text; task assignment remains separate.";
    list.appendChild(empty);
    return;
  }
  for (const message of messages) {
    const item = document.createElement("li");
    item.className = message.author === "user" ? "message user" : "message witch";
    const author = message.author === "user" ? "You" : profile(message.author)?.name || message.author;
    item.innerHTML = `<b>${author}</b><p></p><time>${new Date(message.timestamp).toLocaleString()}</time>`;
    item.querySelector("p").textContent = message.text;
    list.appendChild(item);
  }
  list.scrollTop = list.scrollHeight;
}

function statusLabel(status) {
  return status.replace(/_/g, " ");
}

function renderTasks() {
  $("taskCount").textContent = String(state.tasks.length);
  const list = $("taskList");
  list.innerHTML = "";
  if (!state.tasks.length) {
    const empty = document.createElement("p");
    empty.className = "empty-state";
    empty.textContent = "No tasks recorded yet.";
    list.appendChild(empty);
  }
  state.tasks.forEach((task) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "task-row";
    button.dataset.status = task.status;
    button.dataset.selected = String(task.id === state.selectedTask);
    button.innerHTML = `<span>${task.title}</span><small>${profile(task.assignee)?.name || task.assignee} - ${statusLabel(task.status)}</small><b>${task.priority}</b>`;
    button.addEventListener("click", () => {
      state.selectedTask = task.id;
      renderTasks();
      renderTaskDetail(task);
    });
    list.appendChild(button);
  });
  renderRoster();
  if (state.selectedTask) {
    const selected = state.tasks.find((task) => task.id === state.selectedTask);
    if (selected) renderTaskDetail(selected);
  }
}

function renderTaskDetail(task) {
  const detail = $("taskDetail");
  const timeline = task.timeline.map((item) => `<li><b>${item.kind}</b><span>${item.message}</span><time>${new Date(item.timestamp).toLocaleString()}</time></li>`).join("");
  const evidence = task.evidence.length ? task.evidence.map((item) => `<li>${escapeHtml(item)}</li>`).join("") : "<li>No evidence recorded yet.</li>";
  const blockers = task.blockers.length ? task.blockers.map((item) => `<li>${escapeHtml(item)}</li>`).join("") : "<li>No blockers.</li>";
  detail.innerHTML = `
    <h3>${escapeHtml(task.title)}</h3>
    <dl>
      <div><dt>Assignee</dt><dd>${escapeHtml(profile(task.assignee)?.name || task.assignee)}</dd></div>
      <div><dt>State</dt><dd>${escapeHtml(statusLabel(task.status))}</dd></div>
      <div><dt>Mode</dt><dd>${escapeHtml(task.mode)}</dd></div>
      <div><dt>Latest update</dt><dd>${escapeHtml(task.latestUpdate)}</dd></div>
    </dl>
    <h4>Instructions</h4>
    <p>${escapeHtml(task.instructions || "No additional instructions.")}</p>
    <h4>Blockers</h4>
    <ul>${blockers}</ul>
    <h4>Evidence</h4>
    <ul>${evidence}</ul>
    <h4>Timeline</h4>
    <ol>${timeline}</ol>
    ${task.result ? `<h4>Result</h4><p>${escapeHtml(task.result)}</p>` : ""}
    ${task.status === "failed" ? `<button data-retry="${task.id}" type="button">Retry as new attempt</button>` : ""}
  `;
  const retry = detail.querySelector("[data-retry]");
  if (retry) retry.addEventListener("click", () => retryTask(task.id));
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  })[char]);
}

async function sendMessage(event) {
  event.preventDefault();
  const input = $("messageInput");
  const message = input.value.trim();
  if (!message) return;
  try {
    const payload = await api(`/api/conversations/${encodeURIComponent(state.selectedWitch)}`, {
      method: "POST",
      body: JSON.stringify({ message }),
    });
    state.conversations[state.selectedWitch] = payload.messages;
    input.value = "";
    renderTranscript();
  } catch (error) {
    setNotice(error.message, "error");
  }
}

async function assignTask(event) {
  event.preventDefault();
  try {
    const payload = await api("/api/tasks", {
      method: "POST",
      body: JSON.stringify({
        assignee: state.selectedWitch,
        title: $("taskTitle").value,
        instructions: $("taskInstructions").value,
        priority: $("taskPriority").value,
      }),
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
    const payload = await api(`/api/tasks/${encodeURIComponent(taskId)}/retry`, {
      method: "POST",
      body: JSON.stringify({}),
    });
    state.tasks.unshift(payload.task);
    state.selectedTask = payload.task.id;
    renderTasks();
    closeFailureOverlay();
    setNotice("Retry was created as a separate tracked attempt.", "info");
  } catch (error) {
    setNotice(error.message, "error");
  }
}

async function maybeRecordVoice() {
  if (state.recording) {
    state.recording.stop();
    return;
  }
  if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
    setNotice("This browser does not expose local recording APIs. Text input remains available.", "warn");
    return;
  }
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const chunks = [];
    const recorder = new MediaRecorder(stream);
    const startedAt = Date.now();
    recorder.addEventListener("dataavailable", (event) => chunks.push(event.data));
    recorder.addEventListener("stop", () => {
      stream.getTracks().forEach((track) => track.stop());
      state.recording = null;
      $("recordButton").textContent = "Push to talk";
      $("voiceState").textContent = "Recording saved locally";
      const seconds = Math.max(1, Math.round((Date.now() - startedAt) / 1000));
      $("messageInput").value = `Recorded ${seconds}s of audio. Local transcription is not configured yet; type or paste the transcript here before sending.`;
    });
    recorder.start();
    state.recording = recorder;
    $("recordButton").textContent = "Stop recording";
    $("voiceState").textContent = "Recording";
  } catch (error) {
    setNotice(`Microphone unavailable: ${error.message}`, "error");
  }
}

function stopSpeech() {
  if ("speechSynthesis" in window) window.speechSynthesis.cancel();
  $("voiceState").textContent = "Speech stopped";
}

function maybePlayFailure() {
  if (state.currentFailure || state.skipAllFailures || !$("toggleCinematics").checked) return;
  if (document.hidden || state.recording) return;
  const event = state.failureQueue.shift();
  if (!event) return;
  state.currentFailure = event;
  openFailureOverlay(event);
}

function openFailureOverlay(event) {
  const overlay = $("failureOverlay");
  const scene = $("riverScene");
  const report = $("failureReport");
  const mode = $("motionMode").value;
  overlay.hidden = false;
  report.hidden = true;
  scene.hidden = false;
  scene.className = "river-scene";
  $("failureTitle").textContent = event.title;
  $("failedAssignee").textContent = profile(event.assignee)?.name || event.assignee;
  $("failedError").textContent = event.error || "No error supplied by the runtime event.";
  $("failedStep").textContent = event.lastSuccessfulStep || "No checkpoint supplied.";

  if (mode === "off") {
    finishFailureScene("skipped");
    return;
  }
  if (mode === "tableau" || window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
    scene.classList.add("tableau");
    window.setTimeout(() => finishFailureScene("shown"), 1400);
    return;
  }
  scene.classList.add("playing");
  window.setTimeout(() => finishFailureScene("shown"), 9800);
}

async function finishFailureScene(disposition) {
  if (!state.currentFailure) return;
  $("riverScene").hidden = true;
  $("failureReport").hidden = false;
  try {
    await api("/api/cinematics", {
      method: "POST",
      body: JSON.stringify({ eventId: state.currentFailure.eventId, disposition }),
    });
  } catch (error) {
    setNotice(error.message, "error");
  }
}

function closeFailureOverlay() {
  $("failureOverlay").hidden = true;
  state.currentFailure = null;
  maybePlayFailure();
}

function inspectCurrentFailure() {
  if (!state.currentFailure) return;
  state.selectedTask = state.currentFailure.taskId;
  const task = state.tasks.find((item) => item.id === state.selectedTask);
  if (task) renderTaskDetail(task);
  closeFailureOverlay();
}

function reassignCurrentFailure() {
  selectWitch("morgana");
  closeFailureOverlay();
  setNotice("Morgana is selected. Reassignment is advisory in this starter until live Hermes dispatch is wired.", "info");
}

function bindEvents() {
  $("messageForm").addEventListener("submit", sendMessage);
  $("taskForm").addEventListener("submit", assignTask);
  $("recordButton").addEventListener("click", maybeRecordVoice);
  $("stopSpeakingButton").addEventListener("click", stopSpeech);
  $("compactToggle").addEventListener("click", () => {
    state.compact = !state.compact;
    $("workspace").classList.toggle("compact", state.compact);
    $("compactToggle").textContent = state.compact ? "Sanctuary view" : "Compact work view";
  });
  $("skipSceneButton").addEventListener("click", () => finishFailureScene("skipped"));
  $("skipAllButton").addEventListener("click", () => {
    state.skipAllFailures = true;
    finishFailureScene("skipped");
  });
  $("inspectFailureButton").addEventListener("click", inspectCurrentFailure);
  $("retryFailureButton").addEventListener("click", () => state.currentFailure && retryTask(state.currentFailure.taskId));
  $("reassignFailureButton").addEventListener("click", reassignCurrentFailure);
  $("returnFailureButton").addEventListener("click", closeFailureOverlay);
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !$("failureOverlay").hidden) {
      finishFailureScene("skipped");
    }
  });
  document.addEventListener("visibilitychange", maybePlayFailure);
}

async function tick() {
  try {
    await refreshStatus();
    await refreshTasks();
    await refreshFailures();
  } catch (error) {
    setNotice(error.message, "error");
  }
}

async function init() {
  bindEvents();
  await refreshStatus();
  await refreshProfiles();
  await refreshConversation();
  await refreshTasks();
  await refreshFailures();
  window.setInterval(tick, 1500);
}

init().catch((error) => setNotice(error.message, "error"));
