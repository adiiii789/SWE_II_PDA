// Einstellungen (⚙ im Chat): Antwort-Wünsche ans Sprachmodell und Darstellung je Werkzeug.
// Das Formular entsteht allein aus dem Schema von get_settings() (backend/assistant/settings.py) -
// neue Einstellungen oder Werkzeuge brauchen hier keine Änderung.
// Texte kommen teils von fremden MCP-Servern (Werkzeugbeschreibungen) - deshalb nur textContent.

const settingsPanel = document.getElementById("settings-panel");
const settingsBody = document.getElementById("settings-body");
const settingsStatus = document.getElementById("settings-status");
const settingsButton = document.getElementById("settings-button");
const settingsSaveButton = document.getElementById("settings-save");
const settingsResetButton = document.getElementById("settings-reset");
const settingsTabs = Array.from(document.querySelectorAll("#settings-tabs button"));

let settingsForm = null;       // letzte Antwort von get_settings()
let settingsTab = "answer";    // "answer" | "tools"
let resetArmed = false;        // Zurücksetzen braucht einen zweiten Klick

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

// Ein Eingabefeld je Art ("kind"); liefert {node, read()} - read() gibt den aktuellen Wert zurück.
function buildField(field, value, idPrefix) {
  const id = `${idPrefix}-${field.key}`;
  const row = element("div", `setting setting-${field.kind}`);
  row.dataset.key = field.key;
  const label = element("label", "setting-label", field.label);
  label.htmlFor = id;
  let read;

  if (field.kind === "choice") {
    const select = element("select");
    select.id = id;
    for (const choice of field.choices) {
      const option = element("option", "", choice.label);
      option.value = choice.value;
      option.selected = choice.value === value;
      select.appendChild(option);
    }
    row.append(label, select);
    read = () => select.value;
  } else if (field.kind === "multi") {
    const box = element("div", "setting-options");
    const inputs = field.choices.map(choice => {
      const option = element("label", "setting-option");
      const input = element("input");
      input.type = "checkbox";
      input.value = choice.value;
      input.checked = value.includes(choice.value);
      option.append(input, document.createTextNode(choice.label));
      box.appendChild(option);
      return input;
    });
    row.append(element("span", "setting-label", field.label), box);
    read = () => inputs.filter(input => input.checked).map(input => input.value);
  } else if (field.kind === "bool") {
    const input = element("input");
    input.type = "checkbox";
    input.id = id;
    input.checked = Boolean(value);
    label.prepend(input);
    row.append(label);
    read = () => input.checked;
  } else if (field.kind === "number") {
    const input = element("input");
    input.type = "number";
    input.id = id;
    input.min = field.minimum;
    input.max = field.maximum;
    input.step = 1;
    input.value = value;
    row.append(label, input);
    read = () => Number(input.value);
  } else {
    const input = element("textarea");
    input.id = id;
    input.rows = 2;
    input.value = value;
    input.placeholder = field.help || "";
    row.append(label, input);
    read = () => input.value;
  }
  if (field.help && field.kind !== "text") row.appendChild(element("div", "setting-help", field.help));
  return {node: row, read};
}

// Felder eines Bereichs bauen; gibt eine Funktion zurück, die alle Werte als {key: value} liest.
function buildFields(container, fields, values, idPrefix) {
  const readers = {};
  for (const field of fields) {
    const {node, read} = buildField(field, values[field.key], idPrefix);
    container.appendChild(node);
    readers[field.key] = read;
  }
  return () => Object.fromEntries(Object.entries(readers).map(([key, read]) => [key, read()]));
}

let readSettings = () => ({});

function renderSettings() {
  // nicht replaceChildren(): das Chromium von Qt 5 kennt es noch nicht
  while (settingsBody.firstChild) settingsBody.removeChild(settingsBody.firstChild);
  resetArmed = false;
  updateResetButton();
  const {answer, tools} = settingsForm;

  const answerSection = element("section", "settings-section");
  answerSection.dataset.tab = "answer";
  answerSection.appendChild(element("p", "settings-intro",
    "So soll der Assistent antworten. Gilt ab der nächsten Nachricht."));
  const readAnswer = buildFields(answerSection, answer.fields, answer.values, "answer");

  const toolSection = element("section", "settings-section");
  toolSection.dataset.tab = "tools";
  toolSection.appendChild(element("p", "settings-intro",
    "Je Werkzeug: ob der Assistent es nutzt und wie er Ergebnisse zeigt. Neue Werkzeuge erscheinen hier automatisch."));
  const toolReaders = {};
  for (const group of tools) {
    const details = element("details", "settings-group");
    details.dataset.group = group.id;
    const summary = element("summary", "", group.title);
    if (!group.available) summary.appendChild(element("span", "settings-badge", "gerade nicht verfügbar"));
    details.appendChild(summary);
    if (group.description) details.appendChild(element("div", "settings-description", group.description));
    details.appendChild(element("div", "settings-tools", group.tools.join(" · ")));
    toolReaders[group.id] = buildFields(details, group.fields, group.values, `tool-${group.id}`);
    // Abgeschaltete Gruppe: übrige Felder ausgrauen (Werte bleiben erhalten)
    const enabled = details.querySelector('[data-key="enabled"] input');
    const updateEnabled = () => details.classList.toggle("disabled", enabled && !enabled.checked);
    if (enabled) enabled.addEventListener("change", updateEnabled);
    updateEnabled();
    toolSection.appendChild(details);
  }
  if (tools.length === 0) toolSection.appendChild(element("p", "settings-intro", "Keine Werkzeuge vorhanden."));

  settingsBody.append(answerSection, toolSection);
  readSettings = () => ({
    answer: readAnswer(),
    tools: Object.fromEntries(Object.entries(toolReaders).map(([id, read]) => [id, read()])),
  });
  showSettingsTab(settingsTab);
}

function showSettingsTab(tab) {
  settingsTab = tab;
  for (const button of settingsTabs) button.classList.toggle("active", button.dataset.tab === tab);
  for (const section of settingsBody.querySelectorAll(".settings-section")) section.hidden = section.dataset.tab !== tab;
}

function setSettingsStatus(text, isError = false) {
  settingsStatus.textContent = text;
  settingsStatus.classList.toggle("error", isError);
}

async function openSettings() {
  settingsPanel.hidden = false;
  settingsButton.classList.add("active");
  setSettingsStatus("lädt …");
  try {
    settingsForm = await get_settings();
    renderSettings();
    setSettingsStatus("");
  } catch (error) {
    setSettingsStatus(error.message, true);
  }
}

function closeSettings() {
  settingsPanel.hidden = true;
  settingsButton.classList.remove("active");
  messageInput.focus();
}

async function saveSettings() {
  settingsSaveButton.disabled = true;
  try {
    settingsForm = await save_settings(readSettings());
    closeSettings();
    addMessage("Einstellungen gespeichert - sie gelten ab der nächsten Nachricht.", "assistant");
  } catch (error) {
    setSettingsStatus(error.message, true);   // nichts gespeichert - Formular bleibt offen
  } finally {
    settingsSaveButton.disabled = false;
  }
}

function updateResetButton() {
  settingsResetButton.textContent = resetArmed ? "Wirklich alles zurücksetzen?" : "Standard wiederherstellen";
  settingsResetButton.classList.toggle("danger", resetArmed);
}

async function resetSettings() {
  if (!resetArmed) {
    resetArmed = true;
    updateResetButton();
    return;
  }
  try {
    settingsForm = await reset_settings();
    renderSettings();
    setSettingsStatus("Standardwerte wiederhergestellt.");
  } catch (error) {
    setSettingsStatus(error.message, true);
  }
}

settingsButton.addEventListener("click", () => (settingsPanel.hidden ? openSettings() : closeSettings()));
document.getElementById("settings-close").addEventListener("click", closeSettings);
document.getElementById("settings-cancel").addEventListener("click", closeSettings);
settingsSaveButton.addEventListener("click", saveSettings);
settingsResetButton.addEventListener("click", resetSettings);
for (const button of settingsTabs) button.addEventListener("click", () => showSettingsTab(button.dataset.tab));
settingsPanel.addEventListener("keydown", event => {
  if (event.key === "Escape") {
    event.stopPropagation();
    closeSettings();
  }
});
