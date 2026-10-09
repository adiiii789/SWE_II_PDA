// Alle Funktionen aus backend/api.py sind hier direkt aufrufbar - immer mit "await".
// Ereignisse aus backend/events.py kommen über onPythonEvent(name, handler) an.

const viewFrame = document.getElementById("view-frame");
const chatHistory = document.getElementById("chat-history");
const inputForm = document.getElementById("input-form");
const messageInput = document.getElementById("message-input");

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
}

// Antwort des Assistenten anzeigen: {"text", "html"} - aus chat() oder als Push vom Backend.
function showReply(reply) {
  addMessage(reply.text, "assistant");
  if (reply.html) showView(reply.html);
}

async function sendMessage(event) {
  event.preventDefault();
  const text = messageInput.value.trim();
  if (!text) return;
  messageInput.value = "";
  addMessage(text, "user");
  try {
    showReply(await chat(text));
  } catch (error) {
    addMessage(error.message, "error");
  }
}

inputForm.addEventListener("submit", sendMessage);
onPythonEvent("assistant_message", showReply);   // Nachrichten, die das Backend von sich aus schickt
start_view().then(showView);
addMessage('Hallo! Schreib "hilfe", um meine Befehle zu sehen.', "assistant");
messageInput.focus();
