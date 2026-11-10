// Ladebildschirm beim Programmstart: Liegt über allem, bis das Backend fertig ist (backend/startup.py),
// das Frontend seine Modellliste hat und die Szene (loading_scenes.js) kurz zu sehen war.
//
// Läuft als einziges Canvas mit höchstens 20 Bildern pro Sekunde und zeichnet nichts bei geschlossenem
// Popup - diese Seite wickelt auch die Python-Aufrufe ab und soll dabei nicht ins Stocken kommen.

const LoadingScreen = (() => {
  const DEFAULT_FPS = 20;
  const MIN_SHOW_MS = 2500;      // sonst blitzt die Szene bei schnellem Start nur kurz auf
  const SKIP_AFTER_MS = 12000;   // große lokale Modelle dauern: dann darf man weitermachen
  const TAGLINE_MS = 3200;
  const FADE_MS = 400;           // wie die transition von .done in loading_screen.css

  const root = document.getElementById("loading-screen");
  const stage = document.getElementById("loading-stage");
  const canvas = document.getElementById("loading-canvas");
  const ctx = canvas.getContext("2d");
  const taglineBox = document.getElementById("loading-tagline");
  const stepBox = document.getElementById("loading-step");
  const skipButton = document.getElementById("loading-skip");

  let status = {done: false, index: 0, total: 1, labels: [], label: "", skippable: false};
  let smooth = 0;                // Fortschritt, weich angenähert
  let startedAt = performance.now();
  let skippableSince = null;
  let sceneId = null, scene = null, state = null;
  let width = 0, height = 0;
  let timer = null;
  let visible = true;
  let backendFinished = false;
  let ready = false;             // Backend fertig und Frontend versorgt
  let finished = () => {};       // löst das Promise aus begin() auf
  let prepare = () => {};
  let dirty = true;              // für Szenen ohne Animation

  function info() {
    return {progress: status.done ? 1 : status.index / status.total, smooth, index: status.index, total: status.total,
      labels: status.labels, label: status.label};
  }

  // Szene zum aktuellen Design holen und Fläche anpassen (Gameboy: nur der Bildschirm).
  function fit() {
    const id = document.documentElement.dataset.theme;
    const next = LoadingScenes.get(id);
    const area = next.screen ? ProactiveAlert.displayArea()
      : {left: 0, top: 0, width: window.innerWidth, height: window.innerHeight};
    const changed = id !== sceneId || area.width !== width || area.height !== height;
    Object.assign(stage.style, {left: `${area.left}px`, top: `${area.top}px`, width: `${area.width}px`, height: `${area.height}px`});
    if (!changed || !area.width || !area.height) return;
    sceneId = id; scene = next; width = area.width; height = area.height;
    const pixel = scene.pixel || 1;
    canvas.width = Math.round(width / pixel);
    canvas.height = Math.round(height / pixel);
    canvas.style.imageRendering = scene.pixel ? "pixelated" : "";
    state = scene.start ? scene.start(canvas.width, canvas.height) : {};
    taglineBox.style.color = scene.ink || "";
    stepBox.style.color = scene.inkMuted || "";
    skipButton.style.color = scene.inkMuted || "";
    dirty = true;
  }

  function drawFrame(now) {
    if (!scene || !canvas.width) return;
    const seconds = (now - startedAt) / 1000;
    smooth += (info().progress - smooth) * 0.08;
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    scene.draw(ctx, canvas.width, canvas.height, seconds, state, info());
  }

  function updateCaption(now) {
    const lines = scene ? scene.tagline : null;
    const text = Array.isArray(lines) ? lines[Math.floor((now - startedAt) / TAGLINE_MS) % lines.length] : lines || "";
    if (taglineBox.textContent !== text) taglineBox.textContent = text;
    const step = scene && scene.showsStep ? "" : status.label ? `${status.label} …` : "Fertig";
    if (stepBox.textContent !== step) stepBox.textContent = step;
    if (status.skippable && skippableSince === null) skippableSince = now;
    if (!status.skippable) skippableSince = null;
    skipButton.hidden = !(skippableSince !== null && now - skippableSince > SKIP_AFTER_MS);
  }

  function frame(now) {
    timer = null;
    if (!root.isConnected || document.hidden) return;
    fit();
    const fps = scene && scene.fps !== undefined ? scene.fps : DEFAULT_FPS;
    try {
      if (fps > 0 || dirty) drawFrame(now);
      dirty = false;
    } catch (error) {   // eine kaputte Szene darf den Start nicht aufhalten
      console.error(error);
      scene = null;
    }
    updateCaption(now);
    // Auch ohne Animation regelmäßig schauen, ob sich Beschriftung oder Größe geändert haben.
    const waitMs = fps > 0 ? 1000 / fps : 500;
    timer = setTimeout(() => requestAnimationFrame(frame), waitMs);
  }

  function run() {
    if (timer === null && visible) timer = setTimeout(() => requestAnimationFrame(frame), 0);
  }

  function hide() {
    if (!visible) return;
    visible = false;
    clearTimeout(timer);
    root.classList.add("done");
    finished();
    setTimeout(() => root.remove(), FADE_MS);
  }

  async function backendDone() {
    if (backendFinished) return;
    backendFinished = true;
    try {
      await prepare();
    } catch (error) {
      console.error(error);
    }
    ready = true;
    setTimeout(hide, Math.max(0, MIN_SHOW_MS - (performance.now() - startedAt)));
  }

  function update(next) {
    status = next;
    dirty = true;
    if (status.done) backendDone();
  }

  // prepareFrontend: läuft, sobald das Backend fertig ist (z. B. Modellliste holen).
  // Das Promise löst sich auf, wenn der Ladebildschirm gerade verschwindet.
  function begin(prepareFrontend) {
    prepare = prepareFrontend;
    startedAt = performance.now();
    onPythonEvent("startup_progress", update);
    document.addEventListener("visibilitychange", run);
    window.addEventListener("resize", () => { dirty = true; });
    skipButton.addEventListener("click", () => { backendDone(); hide(); });
    fit();
    run();
    loading_status().then(update).catch(error => { console.error(error); backendDone(); });
    return new Promise(resolve => { finished = resolve; });
  }

  return {begin, hide, get ready() { return ready; }, get visible() { return visible; }};
})();
