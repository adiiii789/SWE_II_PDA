// Meldet dem Popup (frontend/popup.js), wie hoch die Ansicht sein möchte. Das Popup richtet danach die
// Aufteilung zwischen Ansicht und Chat aus, solange der Nutzer sie nicht selbst gezogen hat, und begrenzt
// das Ziehen am Splitter. Wird in die Templates eingebettet (iframe, sandbox ohne Zugriff aufs Popup).
//   min    darunter wird die Ansicht unbrauchbar
//   ideal  bequeme Höhe, alles ohne Scrollen sichtbar
//   max    größer bringt nichts (0 = keine Grenze)
var EveViewSize = (function () {
  var last = "";
  function report(size) {
    var message = {
      source: "eve-view", action: "size",
      min: Math.round(size.min), ideal: Math.round(size.ideal), max: Math.round(size.max || 0)
    };
    var key = message.min + "/" + message.ideal + "/" + message.max;
    if (key === last) return;
    last = key;
    window.parent.postMessage(message, "*");
  }
  // Für schlichte Seiten (default.html.j2): so hoch wie der Inhalt.
  function reportContent() {
    var height = document.body.offsetHeight + 2;   // + Rahmen des iframes
    report({min: Math.min(height, 60), ideal: height, max: height});
  }
  return {report: report, reportContent: reportContent};
})();
