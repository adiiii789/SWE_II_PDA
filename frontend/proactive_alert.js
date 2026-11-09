// Große Einblendung bei proaktiven Meldungen (backend/proactive.py), zusätzlich zur Chat-Nachricht:
//   1. großes Ausrufezeichen in der Mitte
//   2. die Fläche wächst auf, darin Titel und Inhalt der Meldung (ca. 10 Sekunden, Klick beendet früher)
//   3. die Fläche schrumpft auf die Nachricht im Chat, die erst dann erscheint
// Liegt über Ansicht und Verlauf, das Eingabefeld bleibt frei. Das Aussehen pro Design steht in
// proactive_alert.css; hier nur der Ablauf.
//
// Der Ablauf hängt an Timern statt an animationend, weil "Nachhaltig" alle Animationen abschaltet.

const ProactiveAlert = (() => {
  const MARK_MS = 1300;       // nur das Ausrufezeichen
  const READ_MS = 10000;      // Meldung lesen
  const LEAVE_MS = 600;       // wie die transition von .leaving in proactive_alert.css
  const SLIDE_IN_MS = 500;    // POPUP_ANIMATION_MS in backend/config.py: erst zeigen, wenn das Popup steht
  const MIN_TARGET_PX = 24;   // Mindesthöhe des Ziels, falls die Nachricht außerhalb des Verlaufs liegt

  let overlay = null;
  let shown = null;           // Nachricht zur laufenden Einblendung
  let timer = null;
  let waiting = null;         // kam an, während das Popup zu war

  function element(tag, className, text) {
    const node = document.createElement(tag);
    node.className = className;
    if (text) node.textContent = text;
    return node;
  }

  function reveal(message) {
    if (message && message.dataset.alert === "pending") delete message.dataset.alert;
  }

  function stop() {
    clearTimeout(timer);
    if (overlay) overlay.remove();
    overlay = null;
    reveal(shown);
    shown = null;
  }

  // Fläche genau über Ansicht und Verlauf legen - innerhalb ihrer Rahmen (Gameboy: nur der Bildschirm).
  function place() {
    if (!overlay) return;
    const view = document.getElementById("view-frame");
    const chat = document.getElementById("chat-scroll");
    const viewBox = view.getBoundingClientRect();
    const chatBox = chat.getBoundingClientRect();
    const chatTop = chatBox.top + chat.clientTop;
    const top = viewBox.height > 0 ? viewBox.top + view.clientTop : chatTop;
    overlay.style.left = `${chatBox.left + chat.clientLeft}px`;
    overlay.style.top = `${top}px`;
    overlay.style.width = `${chat.clientWidth}px`;
    overlay.style.height = `${chatTop + chat.clientHeight - top}px`;
    // Passt der Inhalt nicht, läuft er aus und verweist auf den Chat.
    const body = overlay.querySelector(".alert-body");
    const clipped = body.scrollHeight > body.clientHeight + 1;
    body.classList.toggle("clipped", clipped);
    overlay.querySelector(".alert-more").hidden = !clipped;
  }

  // Ziel der Fläche: die Nachricht. Liest man gerade weiter oben, liegt sie außerhalb des Verlaufs -
  // dann zum nächsten sichtbaren Rand, nicht aus dem Chat heraus.
  function shrinkTo(message) {
    const panel = overlay.querySelector(".alert-panel").getBoundingClientRect();
    const target = message.getBoundingClientRect();
    const history = document.getElementById("chat-history").getBoundingClientRect();
    const top = Math.max(history.top, Math.min(target.top, history.bottom - MIN_TARGET_PX));
    const bottom = Math.min(history.bottom, Math.max(target.bottom, top + MIN_TARGET_PX));
    overlay.style.setProperty("--to-x", `${target.left - panel.left}px`);
    overlay.style.setProperty("--to-y", `${top - panel.top}px`);
    overlay.style.setProperty("--to-sx", `${target.width / panel.width}`);
    overlay.style.setProperty("--to-sy", `${(bottom - top) / panel.height}`);
    overlay.classList.add("leaving");
  }

  function leave() {
    if (!overlay || overlay.classList.contains("leaving")) return;
    clearTimeout(timer);
    shrinkTo(shown);
    shown.dataset.alert = "landed";   // blendet sich ein, während die Fläche ankommt
    timer = setTimeout(stop, LEAVE_MS);
  }

  function build(title, text) {
    const root = element("div", "");
    root.id = "proactive-alert";
    root.setAttribute("aria-hidden", "true");   // der Inhalt steht ohnehin im Chat
    const panel = element("div", "alert-panel");
    const content = element("div", "alert-content");
    const body = element("div", "alert-body assistant");
    body.innerHTML = renderMarkdown(text);      // bereinigt durch DOMPurify, wie im Chat
    const more = element("div", "alert-more", "Weiter im Chat");
    more.hidden = true;
    content.append(element("div", "alert-title", title), body, more);   // Titel nur als Text, nie als HTML
    panel.appendChild(content);
    root.append(element("div", "alert-mark", "!"), panel);
    // Klick beendet die Einblendung; preventDefault, damit Links das Popup nicht wegnavigieren.
    root.addEventListener("click", event => { event.preventDefault(); leave(); });
    return root;
  }

  function play({message, title, text}) {
    stop();
    overlay = build(title, text);
    shown = message;
    document.body.appendChild(overlay);
    place();
    timer = setTimeout(() => {
      overlay.classList.add("open");
      timer = setTimeout(leave, READ_MS);
    }, MARK_MS);
  }

  // Bei geschlossenem Popup sähe niemand die Einblendung - dann beim Öffnen nachholen.
  function show(message, title, text) {
    message.dataset.alert = "pending";
    if (waiting) reveal(waiting.message);       // Es wird nur die neueste nachgeholt, alle stehen im Chat.
    if (document.hidden || waiting) waiting = {message, title, text};
    else play({message, title, text});
  }

  document.addEventListener("visibilitychange", () => {
    if (document.hidden || !waiting) return;
    clearTimeout(timer);
    timer = setTimeout(() => {
      const next = waiting;
      waiting = null;
      play(next);
    }, SLIDE_IN_MS);
  });

  // "Chat groß" oder größeres Fenster während der Einblendung
  new ResizeObserver(place).observe(document.getElementById("chat-scroll"));

  return {show};
})();
