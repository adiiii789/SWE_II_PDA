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
let settingsTab = "answer";    // "answer" | "tools" | "proactive" | "companion"
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
  } else if (field.kind === "time") {
    const input = element("input");
    input.type = "time";
    input.id = id;
    input.value = value;
    row.append(label, input);
    read = () => input.value;
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

let companionChoice = {models: [], value: "builtin"};   // für das Feld "Figur", siehe openSettings

function companionFields() {
  return [
    {key: "shown", kind: "bool", label: "3D-Begleiter anzeigen"},
    {key: "model", kind: "choice", label: "Figur",
      help: "Modelle aus dem Ordner frontend/models. Anpassen lässt sich jedes über eine gleichnamige .json-Datei.",
      choices: [...companionChoice.models.map(model => ({value: model.id, label: model.title})),
        {value: "builtin", label: "Eingebaute Figur"}]},
    {key: "side", kind: "choice", label: "Position", help: "Auf welcher Seite des Fensters die Figur steht.",
      choices: [{value: "left", label: "Links vom Fenster"}, {value: "right", label: "Rechts vom Fenster"}]},
  ];
}

function renderSettings() {
  // nicht replaceChildren(): das Chromium von Qt 5 kennt es noch nicht
  while (settingsBody.firstChild) settingsBody.removeChild(settingsBody.firstChild);
  resetArmed = false;
  updateResetButton();
  const {answer, tools, proactive} = settingsForm;

  const answerSection = element("section", "settings-section");
  answerSection.dataset.tab = "answer";
  answerSection.appendChild(element("p", "settings-intro",
    "So soll der Assistent antworten. Gilt ab der nächsten Nachricht."));
  const readAnswer = buildFields(answerSection, answer.fields, answer.values, "answer");

  const toolSection = element("section", "settings-section");
  toolSection.dataset.tab = "tools";
  toolSection.appendChild(element("p", "settings-intro",
    "Je Werkzeug: ob der Assistent es nutzt und wie er Ergebnisse zeigt. Neue Werkzeuge erscheinen hier automatisch."));
  const toolReaders = buildGroups(toolSection, tools, "tool");
  if (tools.length === 0) toolSection.appendChild(element("p", "settings-intro", "Keine Werkzeuge vorhanden."));

  const proactiveSection = element("section", "settings-section");
  proactiveSection.dataset.tab = "proactive";
  proactiveSection.appendChild(element("p", "settings-intro",
    "Wann sich der PDA von selbst meldet. Gilt ab der nächsten Prüfung."));
  const proactiveReaders = buildGroups(proactiveSection, proactive, "proactive");

  // Begleiter: nur im Browser gespeichert (appearance.js), deshalb nicht im Schema von get_settings()
  const companionSection = element("section", "settings-section");
  companionSection.dataset.tab = "companion";
  companionSection.appendChild(element("p", "settings-intro",
    "Die 3D-Figur neben dem Fenster. Sie zeigt mit Augen und Licht, ob der Assistent zuhört, nachdenkt oder spricht."));
  const readCompanion = buildFields(companionSection, companionFields(),
    {shown: Appearance.companionShown, side: Appearance.companionSide, model: companionChoice.value}, "companion");

  settingsBody.append(answerSection, toolSection, proactiveSection, companionSection);
  const readAll = readers => Object.fromEntries(Object.entries(readers).map(([id, read]) => [id, read()]));
  readSettings = () => ({answer: readAnswer(), tools: readAll(toolReaders), proactive: readAll(proactiveReaders),
    companion: readCompanion()});
  showSettingsTab(settingsTab);
}

// Aufklappbare Gruppen mit Feldern; gibt {Gruppen-ID: Funktion, die die Werte liest} zurück.
function buildGroups(container, groups, idPrefix) {
  const readers = {};
  for (const group of groups) {
    const details = element("details", "settings-group");
    details.dataset.group = group.id;
    const summary = element("summary", "", group.title);
    if (!group.available) summary.appendChild(element("span", "settings-badge", "gerade nicht verfügbar"));
    details.appendChild(summary);
    if (group.description) details.appendChild(element("div", "settings-description", group.description));
    if (group.tools.length) details.appendChild(element("div", "settings-tools", group.tools.join(" · ")));
    readers[group.id] = buildFields(details, group.fields, group.values, `${idPrefix}-${group.id}`);
    // Abgeschaltete Gruppe: übrige Felder ausgrauen (Werte bleiben erhalten)
    const enabled = details.querySelector('[data-key="enabled"] input');
    const updateEnabled = () => details.classList.toggle("disabled", enabled && !enabled.checked);
    if (enabled) enabled.addEventListener("change", updateEnabled);
    updateEnabled();
    container.appendChild(details);
  }
  return readers;
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
    const [form, models, current] = await Promise.all([get_settings(), loadCompanionModels(), currentCompanionModel()]);
    settingsForm = form;
    companionChoice = {models: models.models, value: current};
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
    const {companion, ...values} = readSettings();
    settingsForm = await save_settings(values);
    Appearance.applyCompanion(companion.shown ? companion.side : "off");
    if (companion.model !== companionChoice.value) {
      companionChoice.value = companion.model;
      chooseCompanionModel(companion.model);
    }
    closeSettings();
    addMessage("Einstellungen gespeichert - sie gelten ab sofort.", "assistant");
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
    Appearance.applyCompanion("left");
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
