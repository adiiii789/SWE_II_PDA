// Gespeicherte Chats (backend/chat_history.py): Liste im Panel unter dem Chats-Knopf.
// Jedes Gespräch speichert das Backend von selbst. Ein Klick auf einen Chat setzt ihn fort - der
// Assistent bekommt das Gespräch als Verlauf -, "Neuer Chat" beginnt einen leeren, Löschen braucht
// einen zweiten Klick. Aufgebaut wie die Design-Auswahl (popup.css), so färbt jedes Design es mit ein.
// Nutzt aus popup.js: replyPending, messageInput, showSavedChat, showNewChat.
const Chats = (() => {
  const panel = document.getElementById("chats-panel");
  const button = document.getElementById("chats-button");
  const list = document.getElementById("chats-list");
  const search = document.getElementById("chats-search");
  const status = document.getElementById("chats-status");
  const newButton = document.getElementById("chats-new");
  const SEARCH_FROM = 6;          // Suchfeld erst ab so vielen Chats
  const CONFIRM_MS = 3000;        // so lange wartet "Löschen?" auf den zweiten Klick
  let chats = [];                 // list_chats()
  let busy = false;
  let confirmTimer = null;

  function node(tag, className, text) {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text !== undefined) element.textContent = text;   // Titel stammen vom Nutzer - nie innerHTML
    return element;
  }

  function setStatus(text, error = false) {
    status.textContent = text;
    status.classList.toggle("error", error);
  }

  // "Heute, 14:05", "Gestern, 09:12" oder "24.11.2026"
  function formatDay(date) {
    if (isNaN(date)) return "";
    const day = new Date(date.getFullYear(), date.getMonth(), date.getDate());
    const today = new Date();
    const days = Math.round((new Date(today.getFullYear(), today.getMonth(), today.getDate()) - day) / 86400000);
    const clock = date.toLocaleTimeString("de-DE", {hour: "2-digit", minute: "2-digit"});
    if (days === 0) return `Heute, ${clock}`;
    if (days === 1) return `Gestern, ${clock}`;
    return date.toLocaleDateString("de-DE", {day: "2-digit", month: "2-digit", year: "numeric"});
  }

  function describe(chat) {
    const count = chat.count === 1 ? "1 Nachricht" : `${chat.count} Nachrichten`;
    return `${formatDay(new Date(chat.updated))} · ${count}`;
  }

  function item(chat) {
    const row = node("div", chat.current ? "chat-item current" : "chat-item");
    row.setAttribute("role", "listitem");
    const open = row.appendChild(node("button", "chat-open"));
    open.type = "button";
    open.title = chat.current ? "Dieser Chat läuft gerade" : "Chat fortsetzen";
    open.appendChild(node("span", "chat-title", chat.title));
    open.appendChild(node("span", "chat-meta", chat.current ? `Aktuell · ${describe(chat)}` : describe(chat)));
    open.addEventListener("click", () => openSaved(chat));
    const remove = row.appendChild(node("button", "icon-button small chat-delete", "Löschen"));
    remove.type = "button";
    remove.dataset.icon = "trash";
    remove.title = "Chat löschen";
    remove.addEventListener("click", () => askDelete(remove, chat));
    return row;
  }

  function render() {
    const query = search.value.trim().toLowerCase();
    const shown = chats.filter(chat => !query || chat.title.toLowerCase().includes(query));
    list.textContent = "";
    for (const chat of shown) list.appendChild(item(chat));
    search.hidden = chats.length < SEARCH_FROM && !query;
    if (!chats.length) setStatus("Noch keine gespeicherten Chats. Jedes Gespräch wird von selbst gespeichert.");
    else if (!shown.length) setStatus("Kein Chat passt zur Suche.");
    else setStatus("");
  }

  async function load() {
    setStatus("Lade …");
    try {
      chats = await list_chats();
      render();
    } catch (error) {
      chats = [];
      list.textContent = "";
      setStatus(error.message, true);
    }
  }

  // Bridge-Aufrufe laufen nacheinander: Während eine Antwort unterwegs ist, nicht den Chat wechseln -
  // sonst landete sie im falschen.
  async function run(action) {
    if (busy) return;
    if (replyPending) {
      setStatus("Einen Moment – die Antwort kommt noch.", true);
      return;
    }
    busy = true;
    panel.classList.add("busy");
    try {
      await action();
    } catch (error) {
      setStatus(error.message, true);
    } finally {
      busy = false;
      panel.classList.remove("busy");
    }
  }

  function openSaved(chat) {
    if (chat.current) {
      closePanel();
      return;
    }
    run(async () => {
      showSavedChat(await open_chat(chat.id));
      closePanel();
      messageInput.focus();
    });
  }

  function startNew() {
    run(async () => {
      await new_chat();
      showNewChat();
      closePanel();
      messageInput.focus();
    });
  }

  function resetConfirm() {
    clearTimeout(confirmTimer);
    for (const remove of list.querySelectorAll(".chat-delete.confirm")) {
      remove.classList.remove("confirm");
      remove.textContent = "Löschen";
      remove.title = "Chat löschen";
    }
  }

  function askDelete(remove, chat) {
    if (!remove.classList.contains("confirm")) {
      resetConfirm();
      remove.classList.add("confirm");
      remove.textContent = "Löschen?";
      remove.title = "Noch einmal klicken: Chat endgültig löschen";
      confirmTimer = setTimeout(resetConfirm, CONFIRM_MS);
      return;
    }
    resetConfirm();
    run(async () => {
      const result = await delete_chat(chat.id);
      chats = result.chats;
      if (result.cleared) showNewChat();   // war der laufende Chat
      render();
    });
  }

  function openPanel() {
    Appearance.closePanel();
    search.value = "";
    panel.hidden = false;
    button.classList.add("active");
    load();
  }

  function closePanel() {
    resetConfirm();
    panel.hidden = true;
    button.classList.remove("active");
  }

  button.addEventListener("click", () => { if (panel.hidden) openPanel(); else closePanel(); });
  document.getElementById("chats-close").addEventListener("click", closePanel);
  newButton.addEventListener("click", startNew);
  search.addEventListener("input", render);
  // Design und Einstellungen liegen an derselben Stelle - nie zwei Panels übereinander
  for (const id of ["design-button", "settings-button"]) {
    document.getElementById(id).addEventListener("click", () => { if (!panel.hidden) closePanel(); });
  }
  document.addEventListener("click", event => {
    if (!panel.hidden && !panel.contains(event.target) && !button.contains(event.target)) closePanel();
  });
  document.addEventListener("keydown", event => {
    if (event.key === "Escape" && !panel.hidden) closePanel();
  });

  return {open: openPanel, close: closePanel};
})();
