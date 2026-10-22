// Alle Funktionen aus backend/api.py sind hier direkt aufrufbar - immer mit "await".
// Ereignisse aus backend/events.py kommen über onPythonEvent(name, handler) an.

const viewFrame = document.getElementById("view-frame");
const chatHistory = document.getElementById("chat-history");
const inputForm = document.getElementById("input-form");
const messageInput = document.getElementById("message-input");
const modelSelect = document.getElementById("model-select");
const recordButton = document.getElementById("record-button");

// Sprache (backend/speech.py): was verfügbar ist, kommt von speech_support().
let speech = {input: false, output: false};
let recordState = "idle";   // "idle" | "recording" | "transcribing"
let replyPending = false;   // Bridge-Aufrufe laufen nacheinander - während chat() keine Aufnahme starten

// Zeigt fertig gerendertes HTML (aus frontend/templates/, vom Backend gerendert) im iframe an.
function showView(html) {
  viewFrame.srcdoc = html;
}

// role: "user", "assistant" oder "error" (CSS-Klasse der Chat-Blase)
function addMessage(text, role) {
  const element = document.createElement("div");
  element.className = `message ${role}`;
  element.textContent = text;
  chatHistory.appendChild(element);
  chatHistory.scrollTop = chatHistory.scrollHeight;
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
  chatHistory.scrollTop = chatHistory.scrollHeight;
}

// Antwort des Assistenten anzeigen: {"text", "html", "attachments"} - aus chat() oder als Push vom Backend.
function showReply(reply) {
  const message = addMessage(reply.text, "assistant");
  if (reply.attachments && reply.attachments.length) addAttachments(message, reply.attachments);
  if (reply.html) showView(reply.html);
}

// spoken: Nachricht kam per Spracheingabe - dann wird die Antwort vorgelesen.
async function submitText(text, spoken = false) {
  addMessage(text, "user");
  const pending = document.createElement("div");
  pending.className = "pending";
  pending.textContent = "denkt nach …";
  chatHistory.appendChild(pending);
  chatHistory.scrollTop = chatHistory.scrollHeight;
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

async function changeModel() {
  try {
    addMessage(`Modell: ${await select_model(modelSelect.value)}`, "assistant");
  } catch (error) {
    addMessage(error.message, "error");
  }
}

inputForm.addEventListener("submit", sendMessage);
modelSelect.addEventListener("change", changeModel);
recordButton.addEventListener("click", toggleRecording);
document.addEventListener("keydown", onKeyDown);
onPythonEvent("assistant_message", showReply);   // Nachrichten, die das Backend von sich aus schickt
start_view().then(showView);
loadModels();
loadSpeechSupport();
addMessage('Hallo! Frag mich etwas oder schreib "hilfe" für die festen Befehle.', "assistant");
messageInput.focus();
