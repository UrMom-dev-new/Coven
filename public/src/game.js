const stations = {
  morgana: { x: 705, y: 505, label: "Planning table" },
  sybil: { x: 700, y: 280, label: "Scrying mirror" },
  circe: { x: 385, y: 372, label: "Workbench" },
  hecate: { x: 993, y: 374, label: "Wards" },
  selene: { x: 190, y: 420, label: "Archive" },
  ophelia: { x: 1120, y: 410, label: "River portal" },
};

const walkable = { minX: 145, maxX: 1240, minY: 320, maxY: 635 };

export function createSanctuaryGame(canvas, options = {}) {
  const ctx = canvas.getContext("2d");
  const state = {
    x: 700,
    y: 615,
    targetX: 700,
    targetY: 615,
    keys: new Set(),
    selected: "morgana",
    running: true,
    last: performance.now(),
    lowEffects: false,
    taskStates: new Map(),
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
    options.onPrompt?.(station ? `Press Enter or click to talk with ${station}.` : "");
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
      ctx.globalAlpha = id === state.selected ? 1 : 0.72;
      ctx.fillStyle = status === "failed" ? "#c86b62" : status === "completed" ? "#93b87d" : "#d7b46a";
      ctx.beginPath();
      ctx.ellipse(station.x, station.y + 56, 38, 12, 0, 0, Math.PI * 2);
      ctx.fill();
      ctx.fillStyle = "#111822";
      ctx.strokeStyle = id === state.selected ? "#d7b46a" : "#596274";
      ctx.lineWidth = 4;
      ctx.beginPath();
      ctx.roundRect(station.x - 30, station.y - 78, 60, 118, 24);
      ctx.fill();
      ctx.stroke();
      ctx.fillStyle = "#ece7dc";
      ctx.font = "24px serif";
      ctx.textAlign = "center";
      ctx.fillText(id.slice(0, 1).toUpperCase(), station.x, station.y - 12);
      if (!state.lowEffects) {
        ctx.strokeStyle = "#78a8c7";
        ctx.globalAlpha *= 0.5;
        ctx.beginPath();
        ctx.arc(station.x, station.y - 20, 38 + Math.sin(performance.now() / 500) * 3, 0, Math.PI * 2);
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
