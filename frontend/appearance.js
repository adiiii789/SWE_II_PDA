// Nur Darstellungspräferenzen; keine Gesprächsinhalte im Browserspeicher.
(function () {
  "use strict";
  const storageKey = "pda.appearance.v2";
  const designs = [
    {id: "system", name: "Apple · Automatisch", description: "Hell und Dunkel folgen deinem System.", group: "apple"},
    {id: "apple-light", name: "Apple Hell", description: "Licht, Klarheit und feine Materialien.", group: "apple", colors: ["#f5f5f7", "#ffffff", "#0067d9", "#1d1d1f"]},
    {id: "apple-dark", name: "Apple Dunkel", description: "Tiefe Grautöne. Sanfte blaue Akzente.", group: "apple", colors: ["#161618", "#303034", "#82b7ff", "#f5f5f7"]},
    {id: "neumorphic", name: "Neumorphismus", description: "Weiche Reliefs und fühlbare Tiefe.", group: "styles", colors: ["#e6e8ed", "#e6e8ed", "#47638c", "#343e51"]},
    {id: "oled", name: "OLED", description: "Echtes Schwarz. Elektrisches Grün.", group: "styles", colors: ["#000000", "#101810", "#67ff12", "#f0f8ed"]},
    {id: "pixel", name: "Pixel Art", description: "8-Bit-Schrift und kantige Formen.", group: "styles", colors: ["#101026", "#253c9a", "#ffe45c", "#f5f3ff"]},
    {id: "maximalist", name: "Maximalismus", description: "Knallige Farben. Mutige Kontraste.", group: "styles", colors: ["#fff500", "#ff3bd4", "#00ebed", "#131313"]},
  ];
  const allowed = designs.map(design => design.id);
  const media = window.matchMedia("(prefers-color-scheme: dark)");
  let selected = "system";
  try {
    const saved = localStorage.getItem(storageKey);
    if (allowed.includes(saved)) selected = saved;
  } catch (_) { /* Bei gesperrtem Speicher bleibt die Systemvorgabe aktiv. */ }
  let theme;
  let panel, trigger, status;

  function sync() {
    const frame = document.getElementById("view-frame");
    if (frame && frame.contentWindow) frame.contentWindow.postMessage({type: "pda:appearance", theme: theme}, "*");
  }

  function apply() {
    theme = selected === "system" ? (media.matches ? "apple-dark" : "apple-light") : selected;
    document.documentElement.dataset.theme = theme;
    document.documentElement.dataset.appearance = selected;
    if (panel) {
      for (const button of panel.querySelectorAll("[data-design]")) {
        const active = button.dataset.design === selected;
        button.setAttribute("aria-checked", String(active));
        button.tabIndex = active ? 0 : -1;
      }
      trigger.title = "Design: " + designs.find(design => design.id === selected).name;
    }
    sync();
  }

  function select(id) {
    if (!allowed.includes(id)) throw new Error("Unbekanntes Design");
    selected = id;
    apply();
    try {
      localStorage.setItem(storageKey, selected);
      if (status) status.textContent = designs.find(design => design.id === id).name + " ausgewählt · automatisch gespeichert";
    } catch (_) {
      if (status) status.textContent = "Design übernommen. Auf diesem Gerät konnte es nicht gespeichert werden.";
    }
  }

  function close(restoreFocus) {
    if (!panel || panel.hidden) return;
    panel.hidden = true;
    trigger.setAttribute("aria-expanded", "false");
    if (restoreFocus !== false) trigger.focus();
  }

  function open() {
    panel.hidden = false;
    trigger.setAttribute("aria-expanded", "true");
    panel.querySelector('[aria-checked="true"]').focus();
  }

  function buildOption(design) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "design-option";
    button.dataset.design = design.id;
    button.setAttribute("role", "radio");
    button.setAttribute("aria-label", design.name + ". " + design.description);
    const title = '<span class="design-option-name">' + design.name + '<span class="design-check" aria-hidden="true">✓</span></span>';
    const description = '<span class="design-option-description">' + design.description + '</span>';
    if (design.id === "system") {
      button.innerHTML = '<span class="system-preview" aria-hidden="true"></span><span class="system-copy">' + title + description + '</span>';
    } else {
      const colors = design.colors;
      button.style.setProperty("--preview-bg", colors[0]);
      button.style.setProperty("--preview-surface", colors[1]);
      button.style.setProperty("--preview-accent", colors[2]);
      button.style.setProperty("--preview-text", colors[3]);
      // Ausschließlich feste Texte und Elemente aus dem lokalen Designkatalog.
      button.innerHTML = '<span class="design-preview" aria-hidden="true"><span class="preview-bar"></span><span class="preview-card"></span><span class="preview-bubble"></span></span>' + title + description;
    }
    button.addEventListener("click", () => select(design.id));
    return button;
  }

  document.addEventListener("DOMContentLoaded", function () {
    panel = document.getElementById("design-panel");
    trigger = document.getElementById("design-button");
    status = document.getElementById("design-status");
    const options = document.getElementById("design-options");
    for (const group of [{id: "apple", title: "APPLE · STANDARD"}, {id: "styles", title: "INSPIRIERT VON DEINEN VORLAGEN"}]) {
      const heading = document.createElement("span");
      heading.className = "design-section-label";
      heading.textContent = group.title;
      options.appendChild(heading);
      for (const design of designs.filter(item => item.group === group.id)) options.appendChild(buildOption(design));
    }
    apply();
    trigger.addEventListener("click", () => panel.hidden ? open() : close());
    document.getElementById("design-close").addEventListener("click", () => close());
    document.getElementById("view-frame").addEventListener("load", sync);
    document.addEventListener("pointerdown", event => {
      if (!panel.hidden && !panel.contains(event.target) && !trigger.contains(event.target)) close(false);
    });
    panel.addEventListener("keydown", event => {
      const button = event.target.closest("[data-design]");
      if (!button) return;
      let index = allowed.indexOf(button.dataset.design);
      if (event.key === "ArrowRight" || event.key === "ArrowDown") index = (index + 1) % allowed.length;
      else if (event.key === "ArrowLeft" || event.key === "ArrowUp") index = (index + allowed.length - 1) % allowed.length;
      else if (event.key === "Home") index = 0;
      else if (event.key === "End") index = allowed.length - 1;
      else return;
      event.preventDefault();
      select(allowed[index]);
      panel.querySelector('[data-design="' + allowed[index] + '"]').focus();
    });
    document.addEventListener("keydown", event => {
      if (event.key === "Escape" && !panel.hidden) {
        event.preventDefault();
        event.stopImmediatePropagation();
        close();
      }
    }, true);
  });

  window.addEventListener("message", event => {
    const frame = document.getElementById("view-frame");
    if (!frame || event.source !== frame.contentWindow || !event.data) return;
    if (event.data.type === "pda:appearance-ready") sync();
    if (event.data.type === "pda:view-interaction") close(false);
  });
  if (media.addEventListener) media.addEventListener("change", () => { if (selected === "system") apply(); });
  else media.addListener(() => { if (selected === "system") apply(); });
  window.PDAAppearance = {select: select, sync: sync, close: close,
    get selected() { return selected; }, get theme() { return theme; }};
  apply();
}());
