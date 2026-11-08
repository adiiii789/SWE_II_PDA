// Avatar des Assistenten: runde, animierte Kugel (Canvas), die zeigt, was der Assistent gerade tut.
// Rein optisch - popup.js meldet nur den Zustand (Avatar.setState), appearance.js Farben und Stil.
//
// Zustände: idle (steht still), thinking (kreist), listening (Spracheingabe, pulsiert wie eine Stimme),
// transcribing (wird erkannt), speaking (liest vor).
// Stile: nebula (fließende Farben), waves (Wellen), core (Kern mit Ringen).
//
// Sparsam, weil dieselbe Seite die Python-Aufrufe abwickelt: Im Ruhezustand wird nur ein einzelnes
// Bild gezeichnet; sonst höchstens 30 Bilder pro Sekunde und nur, solange die Seite sichtbar ist.

const Avatar = (() => {
  const TAU = Math.PI * 2;
  const FRAME_MS = 1000 / 30;
  const STATES = {
    idle:         {energy: 0.12, speed: 0,   voice: 0, label: "Bereit"},
    thinking:     {energy: 0.5,  speed: 1.6, voice: 0, label: "Denkt nach …"},
    listening:    {energy: 0.45, speed: 0.7, voice: 1, label: "Hört zu …"},
    transcribing: {energy: 0.4,  speed: 1.2, voice: 0, label: "Erkennt Sprache …"},
    speaking:     {energy: 0.5,  speed: 0.8, voice: 1, label: "Spricht …"},
  };

  const instances = new Set();
  let style = "nebula";
  let colors = ["#7C83F2", "#4FB3E8", "#C77DDB"];
  let base = "#14152A";
  // vom Design (appearance.js): pixel = grob gerastert (Gameboy), gloss = Glanzlicht (3D),
  // still = nie animieren, nur bei Zustandswechsel ein neues Bild (Nachhaltig)
  let look = {pixel: false, gloss: false, still: false};
  let state = "idle";
  const live = {energy: 0.12, speed: 0, voice: 0, phase: 0.6, level: 0, levelTarget: 0, nextLevelAt: 0, boost: 0};
  let lastTime = 0;
  let running = false;

  // "#RRGGBB" -> "rgba(r, g, b, a)"
  function rgba(hex, alpha) {
    const value = parseInt(hex.slice(1), 16);
    return `rgba(${(value >> 16) & 255}, ${(value >> 8) & 255}, ${value & 255}, ${Math.max(0, Math.min(1, alpha))})`;
  }

  function mount(canvas, options = {}) {
    instances.add({canvas, ctx: canvas.getContext("2d"), size: options.size || canvas.clientWidth || 32,
      style: options.style || null});
    redraw();
  }

  // Kleines Canvas erzeugen und anmelden, z. B. für "denkt nach …"; verschwindet es aus dem DOM, endet es von selbst.
  function create(size, className = "orb") {
    const canvas = document.createElement("canvas");
    canvas.className = className;
    canvas.style.width = canvas.style.height = `${size}px`;
    mount(canvas, {size});
    return canvas;
  }

  function setState(next) {
    if (!STATES[next] || next === state) return;
    state = next;
    document.body.dataset.agent = state;
    const status = document.getElementById("agent-status");
    if (status) status.textContent = STATES[state].label;
    redraw();
  }

  // Kurzes Aufleuchten, z. B. wenn sich der Assistent von selbst meldet.
  function flash() {
    live.boost = 1;
    redraw();
  }

  function setStyle(next) { style = next; redraw(); }
  function setColors(next, nextBase, nextLook = {}) {
    colors = next;
    base = nextBase || base;
    look = {pixel: Boolean(nextLook.pixel), gloss: Boolean(nextLook.gloss), still: Boolean(nextLook.still)};
    redraw();
  }

  // Zeichnen anstoßen; läuft weiter, solange sich etwas bewegt, und hört dann von selbst auf.
  function redraw() {
    if (running) return;
    running = true;
    lastTime = performance.now();
    requestAnimationFrame(frame);
  }

  function moving() {
    if (look.still) return false;
    const target = STATES[state];
    return target.speed > 0 || live.boost > 0.01 || Math.abs(live.energy - target.energy) > 0.01
      || live.voice > 0.01;
  }

  function step(now) {
    const dt = Math.min(0.1, (now - lastTime) / 1000);
    lastTime = now;
    const target = STATES[state];
    const ease = Math.min(1, dt * 4);
    live.energy += (target.energy - live.energy) * ease;
    live.speed += (target.speed - live.speed) * ease;
    live.voice += (target.voice - live.voice) * ease;
    live.boost = Math.max(0, live.boost - dt * 0.8);
    live.phase += dt * (live.speed + live.boost);
    // Stimme nachahmen: alle ~100 ms ein neuer Zielpegel, weich angenähert
    if (now >= live.nextLevelAt) {
      live.levelTarget = Math.pow(Math.random(), 1.4);
      live.nextLevelAt = now + 80 + Math.random() * 90;
    }
    live.level += (live.levelTarget - live.level) * Math.min(1, dt * 10);
    return {phase: live.phase, amp: Math.min(1, live.energy + live.voice * live.level * 0.5 + live.boost * 0.4)};
  }

  function frame(now) {
    if (document.hidden) { running = false; return; }   // Popup zu: nichts zeichnen
    const params = step(now);
    for (const instance of instances) {
      const {canvas, ctx} = instance;
      if (!canvas.isConnected) { instances.delete(instance); continue; }
      if (canvas.offsetParent === null) continue;   // ausgeblendet
      // Pixel-Look: wenige Bildpunkte zeichnen, das CSS vergrößert sie ohne Glätten
      const pixels = look.pixel ? Math.max(8, Math.round(instance.size / 3))
        : Math.round(instance.size * (window.devicePixelRatio || 1));
      if (canvas.width !== pixels) { canvas.width = pixels; canvas.height = pixels; }
      canvas.style.imageRendering = look.pixel ? "pixelated" : "";
      ctx.setTransform(1, 0, 0, 1, 0, 0);
      ctx.clearRect(0, 0, pixels, pixels);
      (DRAW[instance.style || style] || DRAW.nebula)(ctx, pixels, params);
    }
    if (instances.size === 0 || !moving()) { running = false; return; }
    setTimeout(() => requestAnimationFrame(frame), FRAME_MS);
  }

  document.addEventListener("visibilitychange", () => { if (!document.hidden) redraw(); });

  // --- Zeichnen --------------------------------------------------------------------------------

  function sphere(c, S, R, paint) {
    c.save();
    c.beginPath();
    c.arc(S / 2, S / 2, R, 0, TAU);
    c.clip();
    c.fillStyle = base;
    c.fillRect(0, 0, S, S);
    c.globalCompositeOperation = "screen";
    paint();
    c.globalCompositeOperation = "source-over";
    if (look.gloss) {
      // Kugel-Schattierung: dunkler Rand unten rechts, Glanzlicht oben links
      const cx = S / 2, cy = S / 2;
      const shade = c.createRadialGradient(cx - R * 0.3, cy - R * 0.35, R * 0.2, cx, cy, R);
      shade.addColorStop(0, "rgba(0, 0, 0, 0)");
      shade.addColorStop(1, "rgba(0, 0, 0, 0.45)");
      c.fillStyle = shade;
      c.fillRect(0, 0, S, S);
      const shine = c.createRadialGradient(cx - R * 0.38, cy - R * 0.45, 0, cx - R * 0.38, cy - R * 0.45, R * 0.55);
      shine.addColorStop(0, "rgba(255, 255, 255, 0.55)");
      shine.addColorStop(1, "rgba(255, 255, 255, 0)");
      c.fillStyle = shine;
      c.fillRect(0, 0, S, S);
    }
    c.restore();
  }

  // weiche Farbflächen, die ineinander fließen
  function drawNebula(c, S, {phase, amp}) {
    const cx = S / 2, cy = S / 2;
    const R = S * 0.46 * (1 + amp * 0.04);
    sphere(c, S, R, () => {
      for (let i = 0; i < 3; i++) {
        const angle = phase * (0.8 + i * 0.3) * (i % 2 ? -1 : 1) + i * TAU / 3;
        const distance = R * (0.35 + 0.1 * amp);
        const x = cx + Math.cos(angle) * distance;
        const y = cy + Math.sin(angle) * distance;
        const g = c.createRadialGradient(x, y, 0, x, y, R * (0.75 + amp * 0.2));
        g.addColorStop(0, rgba(colors[i], 0.9));
        g.addColorStop(1, rgba(colors[i], 0));
        c.fillStyle = g;
        c.fillRect(0, 0, S, S);
      }
    });
  }

  // Wellen, die mit der Stimme ausschlagen
  function drawWaves(c, S, {phase, amp}) {
    const cx = S / 2, cy = S / 2;
    const R = S * 0.46;
    sphere(c, S, R, () => {
      c.lineWidth = Math.max(1.2, S * 0.035);
      c.lineCap = "round";
      for (let i = 0; i < 3; i++) {
        const height = R * (0.08 + 0.45 * amp) * (1 - i * 0.25);
        const shift = phase * (2 + i * 0.6) * (i % 2 ? -1 : 1) + i * 1.9;
        c.beginPath();
        for (let s = 0; s <= 24; s++) {
          const nx = s / 24 * 2 - 1;
          const y = cy + Math.sin(nx * (1.5 + i * 0.5) * Math.PI + shift) * height * (1 - nx * nx);
          if (s) c.lineTo(cx + nx * R, y); else c.moveTo(cx + nx * R, y);
        }
        c.strokeStyle = rgba(colors[i], 0.85);
        c.stroke();
      }
    });
  }

  // Kern mit Ringen
  function drawCore(c, S, {phase, amp}) {
    const cx = S / 2, cy = S / 2;
    const R = S * 0.46;
    c.fillStyle = colors[0];
    c.beginPath();
    c.arc(cx, cy, R * (0.36 + 0.14 * amp), 0, TAU);
    c.fill();
    c.lineCap = "round";
    c.lineWidth = Math.max(1.2, S * 0.05);
    for (let i = 0; i < 2; i++) {
      const radius = R * (0.68 + i * 0.26);
      const start = phase * (1.2 + i * 0.5) * (i ? -1 : 1) + i * 2;
      c.beginPath();
      c.arc(cx, cy, radius, start, start + Math.PI * (0.6 + 0.6 * amp));
      c.strokeStyle = rgba(colors[i + 1], 0.9);
      c.stroke();
    }
  }

  const DRAW = {nebula: drawNebula, waves: drawWaves, core: drawCore};
  const STYLES = [
    {id: "nebula", name: "Nebula", description: "Fließende Farben"},
    {id: "waves", name: "Wellen", description: "Schlägt mit der Stimme aus"},
    {id: "core", name: "Kern", description: "Kern mit Ringen"},
  ];

  return {mount, create, setState, setStyle, setColors, flash, redraw, STYLES, get state() { return state; }};
})();
