// Alle Funktionen aus backend/api.py sind hier direkt aufrufbar - immer mit "await".
// Ereignisse aus backend/events.py kommen über onPythonEvent(name, handler) an.

const viewFrame = document.getElementById("view-frame");
const chatHistory = document.getElementById("chat-history");
const inputForm = document.getElementById("input-form");
const messageInput = document.getElementById("message-input");
const modelSelect = document.getElementById("model-select");
const recordButton = document.getElementById("record-button");
const chatPanel = document.getElementById("chat-panel");
const splitter = document.getElementById("splitter");
const chatMaxButton = document.getElementById("chat-max-button");
const enlargeButton = document.getElementById("enlarge-button");
const scrollDownButton = document.getElementById("scroll-down-button");
const chatScroll = document.getElementById("chat-scroll");

// Sprache (backend/speech.py): was verfügbar ist, kommt von speech_support().
let speech = {input: false, output: false};
let recordState = "idle";   // "idle" | "recording" | "transcribing"
let replyPending = false;   // Bridge-Aufrufe laufen nacheinander - während chat() keine Aufnahme starten

// Layout: Chat über die ganze Höhe (ohne Ansicht) und vergrößertes Fenster (backend/desktop/popup_window.py)
let chatMaximized = false;
let popupEnlarged = false;
let stickToBottom = true;   // war der Verlauf zuletzt ganz unten? Dann bleibt er es auch bei Größenänderungen
// Unterkante des sichtbaren Ausschnitts (gemessen ab Anfang des Verlaufs) und Höhe des Verlaufs beim
// letzten Scrollen - damit bleibt bei Größenänderungen der Text am Eingabefeld stehen (onChatResize).
let visibleBottom = 0;
let chatHeight = 0;
let resizedScrollTop = null;

const NEAR_BOTTOM_PX = 40;
const VIEW_MIN_PX = 60;     // Mindesthöhen beim Ziehen am #splitter
const CHAT_MIN_PX = 190;   // wie min-height von #chat-panel in popup.css (automatische Aufteilung)
const SNAP_PX = 32;        // so nah an der Eingabe rastet die Ansicht ganz unten ein
// Wunschhöhe der Ansicht {min, ideal, max}, meldet das Template (frontend/templates/view_size.js).
// Solange der Nutzer nicht selbst am Splitter gezogen hat, richtet sich die Aufteilung danach.
let viewSize = null;
let manualSplit = false;

let speaking = false;       // liest gerade vor (nur für den Avatar)
let viewHtml = "";          // zuletzt gezeigte Ansicht - bei Design-Wechsel neu eingefärbt
let viewTaskState = {};     // in dieser Ansicht abgehakt/geöffnet: Aufgaben-ID -> erledigt
let viewUiState = null;     // Reiter und Scrollpositionen der Ansicht - bleiben beim Aktualisieren erhalten
let viewVersion = 0;        // zählt jede neue Ansicht; eine ältere Aktualisierung überschreibt keine neuere
let viewShownAt = 0;
const VIEW_REFRESH_MS = 60000;      // Anzeige höchstens so oft im Hintergrund neu laden
const VIEW_REDRAW_MS = 10 * 60000;  // spätestens dann auch ohne geänderte Daten (Jetzt-Linie)

// Zeigt fertig gerendertes HTML (aus frontend/templates/, vom Backend gerendert) im iframe an,
// in den Farben des gewählten Designs (appearance.js). Neues HTML = neue Ansicht, frische Daten.
// refreshed: dieselbe Ansicht mit frischen Daten - Reiter und Scrollpositionen bleiben.
function showView(html, refreshed = false) {
  if (html !== viewHtml) {
    viewTaskState = {};
    viewSize = null;   // bis die neue Ansicht ihre Höhe meldet, bleibt die bisherige Aufteilung
    if (!refreshed) viewUiState = null;
  }
  viewHtml = html;
  viewVersion++;
  viewShownAt = Date.now();
  viewFrame.srcdoc = withViewState(Appearance.themedHtml(html));
}

// Abgehakte Aufgaben bleiben abgehakt, wenn die Ansicht neu gezeichnet wird (Design-Wechsel),
// Reiter und Scrollpositionen auch nach dem Aktualisieren.
function withViewState(html) {
  const state = {};
  if (Object.keys(viewTaskState).length) state.EVE_TASK_STATE = viewTaskState;
  if (viewUiState) state.EVE_UI_STATE = viewUiState;
  if (!Object.keys(state).length) return html;
  const assignments = Object.entries(state)
    .map(([name, value]) => `window.${name} = ${JSON.stringify(value).replace(/</g, "\\u003c")};`).join(" ");
  const script = `<script>${assignments}</script>`;
  return /<\/head>/i.test(html) ? html.replace(/<\/head>/i, `${script}</head>`) : script + html;
}

// Ohne Jetzt-Linie vergleichen: die wandert jede Minute, die Daten deshalb nicht.
function viewContent(html) {
  return html.replace(/<div class="tl-now"[^>]*><\/div>/g, "");
}

// Anzeige oben auf den neuesten Stand bringen (Kalender, Aufgaben, Mails), ohne Sprachmodell.
// Läuft, wenn das Popup in den Vordergrund kommt, und regelmäßig, solange es offen ist.
async function refreshView() {
  if (replyPending || !viewHtml.includes('class="dashboard"') || Date.now() - viewShownAt < VIEW_REFRESH_MS) return;
  const version = viewVersion;
  const shownAt = viewShownAt;
  viewShownAt = Date.now();   // auch bei Fehlern nicht gleich wieder versuchen
  let html;
  try {
    html = await refresh_view();
  } catch (error) {
    return;   // z. B. offline: bisherige Anzeige bleibt
  }
  if (!html || version !== viewVersion || replyPending) return;
  if (viewContent(html) !== viewContent(viewHtml) || Date.now() - shownAt > VIEW_REDRAW_MS) showView(html, true);
}

// Klicks in der Ansicht (frontend/templates/dashboard.html.j2): Das iframe ist abgeschottet und
// meldet sie per postMessage. Nur Nachrichten aus dem eigenen iframe und nur diese Aktionen.
async function onViewMessage(event) {
  const message = event.data;
  if (event.source !== viewFrame.contentWindow || !message || message.source !== "eve-view") return;
  if (message.action === "ui_state") {
    const tab = Number(message.tab);
    const side = Number(message.side || 0);
    const scrolls = Array.isArray(message.scrolls) ? message.scrolls.slice(0, 20).map(Number) : [];
    const index = (value) => Number.isInteger(value) && value >= 0 && value < 20;
    if (index(tab) && index(side) && scrolls.every((value) => Number.isFinite(value) && value >= 0)) {
      viewUiState = {tab, side, scrolls};
    }
    return;
  }
  if (message.action === "size") {
    const size = [message.min, message.ideal, message.max].map((value) => Number(value));
    if (size.every((value) => Number.isFinite(value) && value >= 0 && value <= 10000)) {
      viewSize = {min: size[0], ideal: Math.max(size[0], size[1]), max: size[2]};
      applyAutoSplit();
    }
    return;
  }
  if (message.action === "complete_task" && typeof message.id === "string" && typeof message.done === "boolean") {
    let ok = true;
    try {
      await complete_task_from_view(message.id, message.done);
      viewTaskState[message.id] = message.done;
    } catch (error) {
      ok = false;
      addMessage(`Aufgabe nicht geändert: ${error.message}`, "error");
    }
    if (event.source) event.source.postMessage({source: "eve-host", request: message.request, ok}, "*");
  } else if (message.action === "open_mail" && /^\d{1,10}$/.test(String(message.uid)) && !replyPending) {
    submitText(`Zeig mir die E-Mail mit der UID ${message.uid}.`);
  }
}

// Avatar (avatar.js) zeigt, was der Assistent gerade tut.
function updateAgentState() {
  if (recordState === "recording") Avatar.setState("listening");
  else if (recordState === "transcribing") Avatar.setState("transcribing");
  else if (speaking) Avatar.setState("speaking");
  else if (replyPending) Avatar.setState("thinking");
  else Avatar.setState("idle");
}

function isNearBottom() {
  return chatHistory.scrollHeight - chatHistory.scrollTop - chatHistory.clientHeight < NEAR_BOTTOM_PX;
}

function scrollToBottom() {
  chatHistory.scrollTop = chatHistory.scrollHeight;
}

function onChatScroll() {
  stickToBottom = isNearBottom();
  scrollDownButton.hidden = stickToBottom;
  // Leseposition nur bei echtem Scrollen merken: nicht, wenn sich gerade die Höhe ändert (das regelt
  // onChatResize), und nicht für die Position, die onChatResize gesetzt hat (evtl. vom Browser
  // begrenzt) - sonst landet man beim Zurückschalten woanders als vorher.
  if (!chatHeight) chatHeight = chatHistory.clientHeight;   // noch keine Meldung vom ResizeObserver
  if (chatHistory.clientHeight !== chatHeight || chatHistory.scrollTop === resizedScrollTop) return;
  resizedScrollTop = null;
  visibleBottom = chatHistory.scrollTop + chatHistory.clientHeight;
}

// Splitter, "Chat groß" oder größeres Fenster ändern die Höhe des Verlaufs. Die Unterkante bleibt fest:
// wer unten war, bleibt unten; wer weiter oben liest, sieht am Eingabefeld weiter denselben Text -
// die Ansicht klappt darüber auf und zu, statt den Verlauf nach oben zu schieben.
function onChatResize() {
  if (chatHistory.clientHeight === 0) return;   // gerade nicht sichtbar - Position behalten
  chatHeight = chatHistory.clientHeight;
  if (stickToBottom) {
    scrollToBottom();
  } else {
    chatHistory.scrollTop = visibleBottom - chatHeight;
    resizedScrollTop = chatHistory.scrollTop;
  }
  onChatScroll();
}

// Element an den Verlauf hängen. Mitscrollen nur, wenn man unten war oder selbst geschrieben hat -
// wer gerade weiter oben liest, wird nicht weggerissen (dann erscheint der ↓-Knopf).
// Lange Antworten werden ab ihrem Anfang gezeigt statt ab ihrem Ende.
function appendToChat(element, own = false) {
  const follow = own || isNearBottom();
  chatHistory.appendChild(element);
  if (follow) {
    if (element.offsetHeight > chatHistory.clientHeight) chatHistory.scrollTop = element.offsetTop - 4;
    else scrollToBottom();
  }
  onChatScroll();
}

// role: "user", "assistant" oder "error" (CSS-Klasse der Chat-Blase).
// Antworten des Assistenten als Markdown mit Formeln (markdown.js), alles andere als reiner Text.
function createMessage(text, role) {
  const element = document.createElement("div");
  element.className = `message ${role}`;
  if (role === "assistant") {
    element.innerHTML = renderMarkdown(text);   // bereinigt durch DOMPurify
  } else {
    element.textContent = text;
  }
  return element;
}

function addMessage(text, role) {
  const element = createMessage(text, role);
  appendToChat(element, role === "user");
  return element;
}

function formatSize(bytes) {
  if (bytes >= 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  return bytes >= 1024 ? `${Math.round(bytes / 1024)} KB` : `${bytes} B`;
}

function attachmentButton(label, action) {
  const button = document.createElement("button");
  button.type = "button";
  button.textContent = label;
  button.addEventListener("click", async () => {
    button.disabled = true;
    try {
      await action();
    } catch (error) {
      addMessage(error.message, "error");
    } finally {
      button.disabled = false;
    }
  });
  return button;
}

// Dateien unter einer Antwort: {"id", "name", "size", "can_open"} (backend/attachments.py).
// Namen stammen z. B. aus fremden Mails - deshalb nur textContent, nie innerHTML.
function addAttachments(message, attachments) {
  const list = document.createElement("div");
  list.className = "attachments";
  for (const attachment of attachments) {
    const row = document.createElement("div");
    row.className = "attachment";
    const name = document.createElement("span");
    name.className = "attachment-name";
    name.textContent = `📎 ${attachment.name}`;
    name.title = attachment.name;
    const size = document.createElement("span");
    size.className = "attachment-size";
    size.textContent = formatSize(attachment.size);
    row.append(name, size);
    if (attachment.can_open) {
      row.appendChild(attachmentButton("Öffnen", () => open_attachment(attachment.id)));
    }
    row.appendChild(attachmentButton("Speichern", async () => {
      addMessage(`Gespeichert unter ${await save_attachment(attachment.id)}`, "assistant");
    }));
    list.appendChild(row);
  }
  message.appendChild(list);
}

// Antwort des Assistenten anzeigen: {"text", "html", "attachments"} - aus chat() oder als Push vom Backend.
// Proaktive Meldungen (backend/proactive.py) haben zusätzlich "proactive": true und "title".
function showReply(reply) {
  const message = createMessage(reply.text, "assistant");
  if (reply.proactive) {
    markProactive(message, reply.title);
    Avatar.flash();
  }
  if (reply.attachments && reply.attachments.length) addAttachments(message, reply.attachments);
  appendToChat(message);   // erst komplett aufbauen, dann einblenden - so stimmt die Scrollposition
  if (reply.html) showView(reply.html);
  if (reply.proactive) ProactiveAlert.show(message, reply.title || "Meldung", reply.text);
}

// Kennzeichnung "meldet sich von selbst" über der Nachricht - Titel nur als Text, nie als HTML.
function markProactive(message, title) {
  message.classList.add("proactive");
  const label = document.createElement("div");
  label.className = "proactive-label";
  const time = new Date().toLocaleTimeString("de-DE", {hour: "2-digit", minute: "2-digit"});
  label.textContent = `🔔 ${title || "Meldung"} · ${time}`;
  message.prepend(label);
}

// spoken: Nachricht kam per Spracheingabe - dann wird die Antwort vorgelesen.
async function submitText(text, spoken = false) {
  if (modelSelect.disabled) {
    messageInput.value = text;
    return;
  }
  // Verlauf ganz zugezogen: wieder aufmachen, sonst sieht man die Antwort nicht
  if (document.body.classList.contains("history-closed")) resetSplit();
  addMessage(text, "user");
  const pending = document.createElement("div");
  pending.className = "pending";
  pending.appendChild(Avatar.create(16, "orb pending-orb"));
  pending.appendChild(document.createElement("span")).textContent = "denkt nach …";
  appendToChat(pending, true);
  replyPending = true;
  updateRecordButton();
  try {
    const reply = await chat(text);
    showReply(reply);
    if (/^modell(?:e$|\s)/i.test(text)) await loadModels();
    if (spoken && speech.output && reply.text) {
      speaking = true;
      updateAgentState();
      try {
        await speak(reply.text);
      } finally {
        speaking = false;
        updateAgentState();
      }
    }
  } catch (error) {
    addMessage(error.message, "error");
  } finally {
    pending.remove();
    replyPending = false;
    updateRecordButton();
  }
}

async function sendMessage(event) {
  event.preventDefault();
  if (modelSelect.disabled) return;
  const text = messageInput.value.trim();
  if (!text) return;
  messageInput.value = "";
  await submitText(text);
}

function updateRecordButton() {
  recordButton.classList.toggle("recording", recordState === "recording");
  recordButton.disabled = recordState === "transcribing" || (replyPending && recordState === "idle");
  recordButton.textContent = {idle: "🎤", recording: "⏹", transcribing: "…"}[recordState];
  recordButton.title = {
    idle: "Spracheingabe starten",
    recording: "Klicken zum Senden, Escape zum Abbrechen",
    transcribing: "wird erkannt …",
  }[recordState];
  updateAgentState();
}

function setRecordState(state) {
  recordState = state;
  updateRecordButton();
}

// Erster Klick: Aufnahme starten. Zweiter Klick: Aufnahme beenden, erkennen und senden.
async function toggleRecording() {
  if (recordState === "idle") {
    setRecordState("recording");
    try {
      await start_recording();
    } catch (error) {
      setRecordState("idle");
      addMessage(error.message, "error");
    }
  } else if (recordState === "recording") {
    setRecordState("transcribing");
    let text = "";
    try {
      text = (await stop_recording()).trim();
    } catch (error) {
      addMessage(error.message, "error");
    }
    setRecordState("idle");
    if (text) await submitText(text, true);
    else addMessage("Ich habe nichts verstanden.", "error");
  }
}

// Escape: Aufnahme verwerfen und Vorlesen abbrechen.
async function onKeyDown(event) {
  if (event.key !== "Escape") return;
  if (recordState === "recording") {
    setRecordState("idle");
    try {
      await cancel_recording();
    } catch (error) {
      addMessage(error.message, "error");
    }
  }
  if (speech.output) stop_speaking().catch(() => {});
}

async function loadSpeechSupport() {
  try {
    speech = await speech_support();
  } catch (error) {
    speech = {input: false, output: false};
  }
  recordButton.hidden = !speech.input;
}

// Sprachmodelle in die Auswahl laden, getrennt nach lokal, Gemini und Claude-Abo.
const isClaude = model => (model.id ?? "").startsWith("claude/");
const MODEL_GROUPS = [
  {label: "Lokal (Ollama)", matches: model => !model.cloud},
  {label: "Cloud (Gemini)", matches: model => Boolean(model.cloud) && !isClaude(model)},
  {label: "Claude (Abo)", matches: isClaude},
];
let renderedModels = "";

async function loadModels() {
  try {
    const {models, current} = await list_models();
    const snapshot = JSON.stringify([models, current]);
    if (snapshot === renderedModels && modelSelect.value === (current ?? "")) return;
    while (modelSelect.firstChild) modelSelect.removeChild(modelSelect.firstChild);
    for (const {label, matches} of MODEL_GROUPS) {
      const members = models.filter(matches);
      if (members.length === 0) continue;
      const group = document.createElement("optgroup");
      group.label = label;
      for (const model of members) {
        const option = document.createElement("option");
        option.value = model.id ?? model.name;
        option.textContent = model.tools ? model.name : `${model.name} (ohne Werkzeuge)`;
        option.selected = option.value === current;
        group.appendChild(option);
      }
      modelSelect.appendChild(group);
    }
    if (current && !Array.from(modelSelect.options).some(option => option.value === current)) {
      const unavailable = new Option(`${current.replace(/^ollama\//, "") || "Ollama"} (nicht verfügbar)`, current);
      unavailable.disabled = true;
      modelSelect.prepend(unavailable);
      modelSelect.value = current;
    }
    modelSelect.hidden = modelSelect.options.length === 0;
    renderedModels = snapshot;
  } catch (error) {
    modelSelect.hidden = true;
  }
}

// Links in Antworten im Standardbrowser öffnen - sonst würde das Popup selbst wegnavigieren.
async function onChatClick(event) {
  const link = event.target.closest("a[href]");
  if (!link) return;
  event.preventDefault();
  try {
    await open_link(link.href);
  } catch (error) {
    addMessage(error.message, "error");
  }
}

// Aufteilung Ansicht/Chat: Anteil der Ansicht (0..1) als flex-grow, passt so auch nach Größenänderungen.
function setSplit(viewShare) {
  viewFrame.style.flexGrow = viewShare === null ? "" : viewShare;
  chatPanel.style.flexGrow = viewShare === null ? "" : 1 - viewShare;
}

// Platz für Ansicht und Chat zusammen (ohne den Splitter selbst)
function splitSpace() {
  return chatPanel.getBoundingClientRect().bottom - viewFrame.getBoundingClientRect().top - splitter.offsetHeight;
}

// Höhe des Chats ohne Verlauf (Eingabe samt Rändern, je nach Design verschieden)
function chatFixedPx() {
  return chatPanel.offsetHeight - chatScroll.offsetHeight;
}

// Grenzen für die Höhe der Ansicht. Automatisch: höchstens so hoch, wie sie es braucht, der Chat behält
// CHAT_MIN_PX. Beim Ziehen darf die Ansicht bis an die Eingabe heran, der Verlauf verschwindet dann.
function viewLimits(space, dragging) {
  const upper = space - (dragging ? chatFixedPx() : CHAT_MIN_PX);
  const min = viewSize ? Math.min(viewSize.min, upper) : VIEW_MIN_PX;
  const max = viewSize && viewSize.max && !dragging ? Math.max(min, Math.min(viewSize.max, upper)) : upper;
  return {min: Math.max(0, min), max: Math.max(0, max)};
}

// Ansicht so hoch, wie sie es sich wünscht (alles auf einen Blick), solange der Chat genug Platz behält.
function applyAutoSplit() {
  if (manualSplit || chatMaximized || !viewSize) return;
  const space = splitSpace();
  if (space <= 0) return;
  const limits = viewLimits(space);
  setSplit(Math.max(limits.min, Math.min(viewSize.ideal, limits.max)) / space);
}

function resetSplit() {
  manualSplit = false;
  chatPanel.style.minHeight = "";
  document.body.classList.remove("history-closed");   // wieder die Mindesthöhe aus popup.css
  if (viewSize) applyAutoSplit();
  else setSplit(null);
}

function onSplitterDown(event) {
  // Verlauf darf beim Ziehen ganz zugehen; die Eingabe bleibt immer sichtbar
  chatPanel.style.minHeight = `${chatFixedPx()}px`;
  splitter.setPointerCapture(event.pointerId);
  splitter.classList.add("dragging");
  document.body.classList.add("dragging");
}

function onSplitterMove(event) {
  if (!splitter.hasPointerCapture(event.pointerId)) return;
  const space = splitSpace();
  const limits = viewLimits(space, true);
  let wanted = event.clientY - viewFrame.getBoundingClientRect().top - splitter.offsetHeight / 2;
  if (wanted > limits.max - SNAP_PX) wanted = limits.max;   // kurz vor der Eingabe: ganz nach unten
  manualSplit = true;
  setSplit(Math.max(limits.min, Math.min(wanted, limits.max)) / space);
  document.body.classList.toggle("history-closed", wanted >= limits.max);
}

function onSplitterUp() {
  splitter.classList.remove("dragging");
  document.body.classList.remove("dragging");
}

function updateLayoutButtons() {
  document.body.classList.toggle("chat-maximized", chatMaximized);
  chatMaxButton.classList.toggle("active", chatMaximized);
  chatMaxButton.textContent = chatMaximized ? "⇕ Ansicht zeigen" : "⇕ Chat groß";
  chatMaxButton.title = chatMaximized ? "Ansicht wieder einblenden" : "Ansicht ausblenden, Chat über die ganze Höhe";
  enlargeButton.classList.toggle("active", popupEnlarged);
  enlargeButton.textContent = popupEnlarged ? "⤡ Fenster klein" : "⤢ Fenster groß";
  enlargeButton.title = popupEnlarged ? "Fenster auf Normalgröße" : "Fenster vergrößern";
}

function toggleChatMaximized() {
  chatMaximized = !chatMaximized;
  updateLayoutButtons();
}

async function toggleEnlarged() {
  try {
    popupEnlarged = await enlarge_popup(!popupEnlarged);
  } catch (error) {
    addMessage(error.message, "error");
  }
  updateLayoutButtons();
}

async function changeModel() {
  const name = modelSelect.selectedOptions[0].textContent;
  modelSelect.disabled = true;
  try {
    await select_model(modelSelect.value);
    addMessage(`Modell: ${name}`, "assistant");
  } catch (error) {
    addMessage(error.message, "error");
  } finally {
    await loadModels();
    modelSelect.disabled = false;
  }
}

inputForm.addEventListener("submit", sendMessage);
document.addEventListener("appearancechange", () => { if (viewHtml) showView(viewHtml); });
window.addEventListener("message", onViewMessage);   // Klicks in der Ansicht (Aufgaben, Mails)
modelSelect.addEventListener("change", changeModel);
window.addEventListener("focus", () => {
  if (!modelSelect.disabled && !replyPending) loadModels();
  refreshView();
});
setInterval(() => { if (document.hasFocus()) refreshView(); }, VIEW_REFRESH_MS / 2);
chatHistory.addEventListener("click", onChatClick);
recordButton.addEventListener("click", toggleRecording);
chatHistory.addEventListener("scroll", onChatScroll);
scrollDownButton.addEventListener("click", scrollToBottom);
new ResizeObserver(onChatResize).observe(chatHistory);
splitter.addEventListener("pointerdown", onSplitterDown);
splitter.addEventListener("pointermove", onSplitterMove);
splitter.addEventListener("pointerup", onSplitterUp);
splitter.addEventListener("lostpointercapture", onSplitterUp);
splitter.addEventListener("dblclick", resetSplit);
window.addEventListener("resize", applyAutoSplit);   // z. B. "Fenster groß"
chatMaxButton.addEventListener("click", toggleChatMaximized);
enlargeButton.addEventListener("click", toggleEnlarged);
document.addEventListener("keydown", onKeyDown);
onPythonEvent("assistant_message", showReply);   // Nachrichten, die das Backend von sich aus schickt
start_view().then(showView);
updateLayoutButtons();
addMessage('Hallo! Frag mich etwas oder schreib "hilfe" für die festen Befehle.', "assistant");
// Erst schreiben, wenn der Assistent bereit ist; Modellliste und Sprache setzen ihn voraus.
messageInput.disabled = true;
LoadingScreen.begin(async () => {
  await loadModels();
  await loadSpeechSupport();
}).then(() => {
  messageInput.disabled = false;
  messageInput.focus();
});
