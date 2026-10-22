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

// Sprache (backend/speech.py): was verfügbar ist, kommt von speech_support().
let speech = {input: false, output: false};
let recordState = "idle";   // "idle" | "recording" | "transcribing"
let replyPending = false;   // Bridge-Aufrufe laufen nacheinander - während chat() keine Aufnahme starten

// Layout: Chat über die ganze Höhe (ohne Ansicht) und vergrößertes Fenster (backend/desktop/popup_window.py)
let chatMaximized = false;
let popupEnlarged = false;
let stickToBottom = true;   // war der Verlauf zuletzt ganz unten? Dann bleibt er es auch bei Größenänderungen

const NEAR_BOTTOM_PX = 40;
const VIEW_MIN_PX = 60;     // Mindesthöhen beim Ziehen am #splitter
const CHAT_MIN_PX = 120;

// Zeigt fertig gerendertes HTML (aus frontend/templates/, vom Backend gerendert) im iframe an.
function showView(html) {
  viewFrame.srcdoc = html;
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
function showReply(reply) {
  const message = createMessage(reply.text, "assistant");
  if (reply.attachments && reply.attachments.length) addAttachments(message, reply.attachments);
  appendToChat(message);   // erst komplett aufbauen, dann einblenden - so stimmt die Scrollposition
  if (reply.html) showView(reply.html);
}

// spoken: Nachricht kam per Spracheingabe - dann wird die Antwort vorgelesen.
async function submitText(text, spoken = false) {
  addMessage(text, "user");
  const pending = document.createElement("div");
  pending.className = "pending";
  pending.textContent = "denkt nach …";
  appendToChat(pending, true);
  replyPending = true;
  updateRecordButton();
  try {
    const reply = await chat(text);
    showReply(reply);
    if (spoken && speech.output && reply.text) await speak(reply.text);
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

// Ollama-Modelle in die Auswahl laden, getrennt nach lokal und Cloud (leer = Assistent ohne Sprachmodell).
const MODEL_GROUPS = [
  {label: "Lokal (auf diesem PC)", cloud: false},
  {label: "Cloud (ollama.com)", cloud: true},
];

async function loadModels() {
  try {
    const {models, current} = await list_models();
    while (modelSelect.firstChild) modelSelect.removeChild(modelSelect.firstChild);
    for (const {label, cloud} of MODEL_GROUPS) {
      const members = models.filter(model => Boolean(model.cloud) === cloud);
      if (members.length === 0) continue;
      const group = document.createElement("optgroup");
      group.label = label;
      for (const model of members) {
        const option = document.createElement("option");
        option.value = model.name;
        option.textContent = model.tools ? model.name : `${model.name} (ohne Werkzeuge)`;
        option.selected = model.name === current;
        group.appendChild(option);
      }
      modelSelect.appendChild(group);
    }
    modelSelect.hidden = models.length === 0;
  } catch (error) {
    modelSelect.hidden = true;   // z. B. Ollama läuft nicht - der Chat meldet das bei der ersten Nachricht
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

function onSplitterDown(event) {
  splitter.setPointerCapture(event.pointerId);
  splitter.classList.add("dragging");
  document.body.classList.add("dragging");
}

function onSplitterMove(event) {
  if (!splitter.hasPointerCapture(event.pointerId)) return;
  const top = viewFrame.getBoundingClientRect().top;
  const total = chatPanel.getBoundingClientRect().bottom - top;
  const viewHeight = Math.max(VIEW_MIN_PX, Math.min(event.clientY - top, total - CHAT_MIN_PX));
  setSplit(viewHeight / total);
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
  try {
    addMessage(`Modell: ${await select_model(modelSelect.value)}`, "assistant");
  } catch (error) {
    addMessage(error.message, "error");
  }
}

inputForm.addEventListener("submit", sendMessage);
modelSelect.addEventListener("change", changeModel);
chatHistory.addEventListener("click", onChatClick);
recordButton.addEventListener("click", toggleRecording);
chatHistory.addEventListener("scroll", onChatScroll);
scrollDownButton.addEventListener("click", scrollToBottom);
// Splitter, "Chat groß" oder größeres Fenster ändern die Höhe - wer unten war, bleibt unten.
new ResizeObserver(() => { if (stickToBottom) scrollToBottom(); }).observe(chatHistory);
splitter.addEventListener("pointerdown", onSplitterDown);
splitter.addEventListener("pointermove", onSplitterMove);
splitter.addEventListener("pointerup", onSplitterUp);
splitter.addEventListener("lostpointercapture", onSplitterUp);
splitter.addEventListener("dblclick", () => setSplit(null));
chatMaxButton.addEventListener("click", toggleChatMaximized);
enlargeButton.addEventListener("click", toggleEnlarged);
document.addEventListener("keydown", onKeyDown);
onPythonEvent("assistant_message", showReply);   // Nachrichten, die das Backend von sich aus schickt
start_view().then(showView);
loadModels();
loadSpeechSupport();
updateLayoutButtons();
addMessage('Hallo! Frag mich etwas oder schreib "hilfe" für die festen Befehle.', "assistant");
messageInput.focus();
