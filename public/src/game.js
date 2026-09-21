const stations = {
  morgana: { x: 705, y: 505, label: "Planning table", name: "Morgana" },
  sybil: { x: 700, y: 280, label: "Scrying mirror", name: "Sybil" },
  circe: { x: 385, y: 372, label: "Workbench", name: "Circe" },
  hecate: { x: 993, y: 374, label: "Wards", name: "Hecate" },
  selene: { x: 190, y: 420, label: "Archive", name: "Selene" },
  ophelia: { x: 1120, y: 410, label: "River portal", name: "Ophelia" },
};

const walkable = { minX: 145, maxX: 1240, minY: 320, maxY: 635 };
const POSITION_KEY = "coven.sanctuary.position.v1";

export function createSanctuaryGame(canvas, options = {}) {
  const ctx = canvas.getContext("2d");
  const savedPosition = readSavedPosition();
  const state = {
    x: savedPosition.x,
    y: savedPosition.y,
    targetX: savedPosition.x,
    targetY: savedPosition.y,
    keys: new Set(),
    selected: "morgana",
    nearStation: null,
    running: true,
    last: performance.now(),
    lowEffects: false,
    taskStates: new Map(),
    lastSavedAt: 0,
  };

  function setSelected(id) {
    state.selected = id;
  }

  function setQuality(quality) {
    state.lowEffects = quality === "low";
  }

  function setTasks(tasks) {
    state.taskStates = new Map();
    for (const task of tasks || []) {
      if (!state.taskStates.has(task.assignee)) state.taskStates.set(task.assignee, task.status);
    }
  }

  function clampPoint(x, y) {
    return {
      x: Math.max(walkable.minX, Math.min(walkable.maxX, x)),
      y: Math.max(walkable.minY, Math.min(walkable.maxY, y)),
    };
  }

  function screenToWorld(event) {
    const rect = canvas.getBoundingClientRect();
    return clampPoint(
      ((event.clientX - rect.left) / rect.width) * canvas.width,
      ((event.clientY - rect.top) / rect.height) * canvas.height,
    );
  }

  function nearestStation(x, y, radius = 88) {
    let best = null;
    let bestDistance = Infinity;
    for (const [id, station] of Object.entries(stations)) {
      const distance = Math.hypot(station.x - x, station.y - y);
      if (distance < radius && distance < bestDistance) {
        best = id;
        bestDistance = distance;
      }
    }
    return best;
  }

  function emitSelect(id) {
    canvas.dispatchEvent(new CustomEvent("coven-select-witch", { bubbles: true, detail: { id } }));
  }

  canvas.addEventListener("click", (event) => {
    const point = screenToWorld(event);
    const station = nearestStation(point.x, point.y, 95);
    if (station) emitSelect(station);
    state.targetX = point.x;
    state.targetY = point.y;
  });

  document.addEventListener("keydown", (event) => {
    if (isTyping(event.target)) return;
    const key = event.key.toLowerCase();
    if (key === "enter" && state.nearStation) {
      event.preventDefault();
      emitSelect(state.nearStation);
      return;
    }
    if (["w", "a", "s", "d", "arrowup", "arrowleft", "arrowdown", "arrowright"].includes(key)) {
      event.preventDefault();
      state.keys.add(key);
    }
  });
  document.addEventListener("keyup", (event) => state.keys.delete(event.key.toLowerCase()));
  document.addEventListener("visibilitychange", () => {
    state.running = !document.hidden;
    if (state.running) {
      state.last = performance.now();
      requestAnimationFrame(loop);
    }
  });

  function update(delta) {
    const speed = 255;
    let dx = 0;
    let dy = 0;
    if (state.keys.has("w") || state.keys.has("arrowup")) dy -= 1;
    if (state.keys.has("s") || state.keys.has("arrowdown")) dy += 1;
    if (state.keys.has("a") || state.keys.has("arrowleft")) dx -= 1;
    if (state.keys.has("d") || state.keys.has("arrowright")) dx += 1;
    if (dx || dy) {
      const length = Math.hypot(dx, dy);
      state.targetX = state.x + (dx / length) * speed * delta;
      state.targetY = state.y + (dy / length) * speed * delta;
    }
    const target = clampPoint(state.targetX, state.targetY);
    const tx = target.x - state.x;
    const ty = target.y - state.y;
    const distance = Math.hypot(tx, ty);
    if (distance > 2) {
      const step = Math.min(distance, speed * delta);
      state.x += (tx / distance) * step;
      state.y += (ty / distance) * step;
    }
    const station = nearestStation(state.x, state.y, 110);
    state.nearStation = station;
    options.onPrompt?.(station ? `Press Enter or click to talk with ${stations[station].name}.` : "");
    savePositionSoon(state);
  }

  function draw() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    drawStations();
    drawFamiliar();
  }

  function drawStations() {
    for (const [id, station] of Object.entries(stations).sort((a, b) => a[1].y - b[1].y)) {
      const status = state.taskStates.get(id) || "available";
      ctx.save();
      ctx.globalAlpha = id === state.selected ? 0.82 : 0.36;
      ctx.fillStyle = status === "failed" ? "#c86b62" : status === "completed" ? "#93b87d" : status === "available" ? "#78a8c7" : "#d7b46a";
      ctx.beginPath();
      ctx.ellipse(station.x, station.y + 56, id === state.selected ? 44 : 28, id === state.selected ? 12 : 8, 0, 0, Math.PI * 2);
      ctx.fill();
      ctx.strokeStyle = id === state.selected ? "#d7b46a" : "#596274";
      ctx.lineWidth = id === state.selected ? 3 : 1.5;
      ctx.beginPath();
      ctx.arc(station.x, station.y + 48, id === state.selected ? 34 : 22, 0, Math.PI * 2);
      ctx.stroke();
      if (!state.lowEffects && id === state.selected) {
        ctx.strokeStyle = "#78a8c7";
        ctx.globalAlpha *= 0.5;
        ctx.beginPath();
        ctx.arc(station.x, station.y + 48, 42 + Math.sin(performance.now() / 500) * 3, 0, Math.PI * 2);
        ctx.stroke();
      }
      ctx.restore();
    }
  }

  function drawFamiliar() {
    ctx.save();
    const glow = state.lowEffects ? 14 : 28 + Math.sin(performance.now() / 180) * 4;
    const gradient = ctx.createRadialGradient(state.x, state.y - 18, 4, state.x, state.y - 18, glow);
    gradient.addColorStop(0, "#fff3b4");
    gradient.addColorStop(0.35, "#d7b46a");
    gradient.addColorStop(1, "rgba(215,180,106,0)");
    ctx.fillStyle = gradient;
    ctx.beginPath();
    ctx.arc(state.x, state.y - 18, glow, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = "#2a2025";
    ctx.beginPath();
    ctx.ellipse(state.x, state.y, 16, 24, 0, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = "#fff3b4";
    ctx.beginPath();
    ctx.moveTo(state.x, state.y - 34);
    ctx.quadraticCurveTo(state.x - 10, state.y - 14, state.x, state.y - 8);
    ctx.quadraticCurveTo(state.x + 10, state.y - 14, state.x, state.y - 34);
    ctx.fill();
    ctx.restore();
  }

  function loop(now) {
    if (!state.running) return;
    const delta = Math.min((now - state.last) / 1000, 0.05);
    state.last = now;
    update(delta);
    draw();
    requestAnimationFrame(loop);
  }

  requestAnimationFrame(loop);

  return { setSelected, setTasks, setQuality };
}

function isTyping(target) {
  return target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement || target instanceof HTMLSelectElement;
}

function readSavedPosition() {
  try {
    const saved = JSON.parse(window.localStorage.getItem(POSITION_KEY) || "null");
    if (saved && Number.isFinite(saved.x) && Number.isFinite(saved.y)) {
      return clampToWalkable(saved.x, saved.y);
    }
  } catch {
    return { x: 700, y: 615 };
  }
  return { x: 700, y: 615 };
}

function savePositionSoon(state) {
  const now = performance.now();
  if (now - state.lastSavedAt < 600) return;
  state.lastSavedAt = now;
  try {
    window.localStorage.setItem(POSITION_KEY, JSON.stringify({ x: Math.round(state.x), y: Math.round(state.y) }));
  } catch {
    // Presentation state is helpful but not required for gameplay.
  }
}

function clampToWalkable(x, y) {
  return {
    x: Math.max(walkable.minX, Math.min(walkable.maxX, x)),
    y: Math.max(walkable.minY, Math.min(walkable.maxY, y)),
  };
}
