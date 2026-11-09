// Die Sandbox bleibt ohne allow-same-origin. Nur bekannte Designnamen werden übernommen.
(function () {
  const themes = ["apple-light", "apple-dark", "neumorphic", "oled", "pixel", "maximalist"];
  window.addEventListener("message", function (event) {
    if (event.source !== window.parent || !event.data || event.data.type !== "pda:appearance") return;
    if (themes.includes(event.data.theme)) document.documentElement.dataset.theme = event.data.theme;
  });
  document.addEventListener("pointerdown", function () {
    window.parent.postMessage({type: "pda:view-interaction"}, "*");
  });
  window.parent.postMessage({type: "pda:appearance-ready"}, "*");
}());
