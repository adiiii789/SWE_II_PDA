// Alle Funktionen aus backend/api.py sind hier direkt aufrufbar - immer mit "await".
// Ereignisse aus backend/events.py kommen über onPythonEvent(name, handler) an.

const viewFrame = document.getElementById("view-frame");
const chatHistory = document.getElementById("chat-history");
const inputForm = document.getElementById("input-form");
const messageInput = document.getElementById("message-input");
const modelSelect = document.getElementById("model-select");

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

async function submitText(text) {
  addMessage(text, "user");
  const pending = document.createElement("div");
  pending.className = "pending";
  pending.textContent = "denkt nach …";
  chatHistory.appendChild(pending);
  chatHistory.scrollTop = chatHistory.scrollHeight;
  try {
    const reply = await chat(text);
    showReply(reply);
  } catch (error) {
    addMessage(error.message, "error");
  } finally {
    pending.remove();
  }
}

async function sendMessage(event) {
  event.preventDefault();
  const text = messageInput.value.trim();
  if (!text) return;
  messageInput.value = "";
  await submitText(text);
}

// Installierte Ollama-Modelle in die Auswahl laden (leer = Assistent ohne Sprachmodell).
async function loadModels() {
  try {
    const {models, current} = await list_models();
    while (modelSelect.firstChild) modelSelect.removeChild(modelSelect.firstChild);
    for (const model of models) {
      const option = document.createElement("option");
      option.value = model.name;
      option.textContent = model.tools ? model.name : `${model.name} (ohne Werkzeuge)`;
      option.selected = model.name === current;
      modelSelect.appendChild(option);
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
onPythonEvent("assistant_message", showReply);   // Nachrichten, die das Backend von sich aus schickt
start_view().then(showView);
loadModels();
addMessage('Hallo! Frag mich etwas oder schreib "hilfe" für die festen Befehle.', "assistant");
messageInput.focus();
