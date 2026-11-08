// Antworten des Sprachmodells lesbar darstellen: Markdown (marked) mit Formeln (KaTeX).
// Formeln: $…$ und \(…\) im Text, $$…$$ und \[…\] abgesetzt.
//
// Sicherheit: Antworten können fremde Inhalte enthalten (z. B. aus Mails), und diese Seite
// darf Python-Funktionen aufrufen. Deshalb geht das Markdown-HTML durch DOMPurify: kein Skript,
// kein Event-Handler, keine Bilder, kein eigenes HTML des Modells. Formeln kommen erst danach
// hinein - KaTeX erzeugt mit trust: false nur eigenes, escaptes HTML (DOMPurify würde dessen
// SVGs, z. B. Wurzelzeichen, zerstören). Bibliotheken: vendor/ (offline, Chromium 87 von Qt 5.15).

const DISPLAY_MATH = [/^\$\$([\s\S]+?)\$\$/, /^\\\[([\s\S]+?)\\\]/];
// $…$ nicht bei Beträgen wie "5 $ und 10 $": kein Leerzeichen direkt innen, keine Ziffer danach.
const INLINE_MATH = [/^\$(?!\s)((?:\\.|[^\\$\n])+?)(?<!\s)\$(?!\d)/, /^\\\(([\s\S]+?)\\\)/];

let formulas = [];   // Formeln der Nachricht, die gerade gerendert wird

// level "block": Formel auf eigener Zeile. level "inline": im Fließtext, auch $$…$$ mitten im Satz.
function mathExtension(level) {
  const patterns = level === "block" ? DISPLAY_MATH.map(p => [p, true])
    : [...DISPLAY_MATH.map(p => [p, true]), ...INLINE_MATH.map(p => [p, false])];
  return {
    name: `math_${level}`,
    level,
    start(src) {
      const match = src.match(level === "block" ? /^ {0,3}(?:\$\$|\\\[)/m : /\$|\\[(\[]/);
      return match ? match.index : undefined;
    },
    tokenizer(src) {
      for (const [pattern, display] of patterns) {
        const match = pattern.exec(src);
        if (match) return {type: `math_${level}`, raw: match[0], formula: match[1].trim(), display};
      }
      return undefined;
    },
    renderer(token) {
      formulas.push(token);
      return `<span data-formula="${formulas.length - 1}"></span>`;   // Platzhalter, siehe renderMarkdown
    },
  };
}

marked.use({
  gfm: true,
  breaks: true,   // einfache Zeilenumbrüche wie im Chat beibehalten
  headerIds: false,
  mangle: false,
  extensions: [mathExtension("block"), mathExtension("inline")],
  renderer: {
    html: () => "",   // eigenes HTML des Modells nicht anzeigen
  },
});

// Markdown-Text -> bereinigtes HTML für innerHTML.
function renderMarkdown(text) {
  formulas = [];
  const template = document.createElement("template");
  template.innerHTML = DOMPurify.sanitize(marked.parse(text), {
    FORBID_TAGS: ["style", "form", "input", "button", "iframe", "img", "svg", "math"],
    ALLOWED_URI_REGEXP: /^(?:https?|mailto):/i,
  });
  for (const placeholder of template.content.querySelectorAll("span[data-formula]")) {
    const token = formulas[Number(placeholder.dataset.formula)];
    if (!token) continue;
    const html = katex.renderToString(token.formula, {
      displayMode: token.display, throwOnError: false, output: "html", trust: false,
    });
    placeholder.removeAttribute("data-formula");
    placeholder.className = token.display ? "math-block" : "math";
    placeholder.innerHTML = html;
  }
  return template.innerHTML.trim();
}
