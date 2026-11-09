// Designs und Avatar-Stil - rein optisch, gespeichert nur im Browser-Speicher der Seite.
// Ein Design setzt die CSS-Variablen aus theme.css neu (Farben, Form, Schatten, Schrift), im Popup
// und in der Ansicht (iframe, siehe themedHtml). Stile mit eigenem Charakter haben zusätzlich Regeln
// in popup.css unter html[data-theme=…] und optional viewCss für die Ansicht.
// Auswahl über den Design-Knopf in der Kopfzeile; Klick wendet sofort an, so lässt sich alles ausprobieren.
//
// Leistung: alles statisch (keine Dauer-Animationen) - diese Seite wickelt auch die Python-Aufrufe ab.

// Grobes Pixelmuster als Kachel (Hintergrund "Minecraft"), immer gleich, ohne Bilddatei
function pixelTile(colors) {
  let rects = "", seed = 5;
  for (let y = 0; y < 16; y++) {
    for (let x = 0; x < 16; x++) {
      seed = (seed * 31 + 7) % 1009;
      rects += `<rect x='${x * 4}' y='${y * 4}' width='4' height='4' fill='${colors[seed % colors.length]}'/>`;
    }
  }
  const svg = `<svg xmlns='http://www.w3.org/2000/svg' width='64' height='64' shape-rendering='crispEdges'>${rects}</svg>`;
  return `url("data:image/svg+xml,${encodeURIComponent(svg)}") 0 0 / 64px 64px`;
}

const THEMES = [
  // --- Farbschemata: schlicht, nur andere Farben -------------------------------------------------
  {id: "night", group: "colors", name: "Nacht", orb: ["#7C83F2", "#4FB3E8", "#C77DDB"], orbBase: "#14152A",
    vars: {}},   // = Standardwerte aus theme.css
  {id: "graphite", group: "colors", name: "Graphit", orb: ["#C9CED8", "#7D8796", "#A3ADBD"], orbBase: "#1A1C21",
    vars: {"--background": "#0F0F10", "--page-bg": "#0F0F10", "--surface": "#161618", "--surface-2": "#1C1C1F",
      "--text": "#E8E8EA", "--text-muted": "#8A8A90", "--control": "#202023", "--control-hover": "#29292D",
      "--border": "#28282C", "--accent": "#E8E8EA", "--accent-text": "#111112", "--link": "#B3C4FF",
      "--user-bg": "#232326", "--user-text": "#E8E8EA"}},
  {id: "light", group: "colors", name: "Hell", orb: ["#5B6CF0", "#3FA7E0", "#B66BD8"], orbBase: "#20244A",
    vars: {"--background": "#F4F5F7", "--page-bg": "#F4F5F7", "--surface": "#FFFFFF", "--surface-2": "#F8F9FA",
      "--text": "#1C1E24", "--text-muted": "#6E7280", "--control": "#ECEEF1", "--control-hover": "#E2E5EA",
      "--border": "#E1E4E9", "--accent": "#4F5FE8", "--accent-text": "#FFFFFF", "--link": "#3445D1",
      "--danger": "#D93B48", "--warning": "#B7860B", "--user-bg": "#E8EBFB", "--user-text": "#1C1E24"}},
  {id: "forest", group: "colors", name: "Wald", orb: ["#4FB58A", "#7FC8A9", "#3C8D7A"], orbBase: "#12201B",
    vars: {"--background": "#0F1412", "--page-bg": "#0F1412", "--surface": "#151C19", "--surface-2": "#1A221F",
      "--text": "#E3EAE6", "--text-muted": "#869690", "--control": "#1D2622", "--control-hover": "#25302B",
      "--border": "#25302B", "--accent": "#4FB58A", "--accent-text": "#08140F", "--link": "#8FD6B6",
      "--user-bg": "#1E2E27", "--user-text": "#E3EAE6"}},
  {id: "sand", group: "colors", name: "Sand", orb: ["#E0915A", "#D96C6C", "#E6B566"], orbBase: "#2A1D16",
    vars: {"--background": "#151210", "--page-bg": "#151210", "--surface": "#1C1815", "--surface-2": "#221D19",
      "--text": "#EDE6E0", "--text-muted": "#9A8F86", "--control": "#26201C", "--control-hover": "#2F2823",
      "--border": "#2E2722", "--accent": "#E0915A", "--accent-text": "#1A100A", "--link": "#F0B48A",
      "--user-bg": "#2E241D", "--user-text": "#EDE6E0"}},
  {id: "classic", group: "colors", name: "Klassisch", orb: ["#6A86C8", "#8AB4F8", "#B48CF0"], orbBase: "#1E1E1E",
    vars: {"--background": "#2E2E2E", "--page-bg": "#2E2E2E", "--surface": "#383838", "--surface-2": "#3E3E3E",
      "--text": "#F1F1F1", "--text-muted": "#AAAAAA", "--control": "#3E3E3E", "--control-hover": "#4E4E4E",
      "--border": "#555555", "--accent": "#3A4A6A", "--accent-text": "#F1F1F1", "--link": "#8AB4F8",
      "--danger": "#C25555", "--warning": "#E0B050", "--user-bg": "#3A4A6A", "--user-text": "#F1F1F1"}},

  // --- Stile: eigene Formen, Schatten und Schrift (Gruppe = Abschnitt im Design-Panel) -----------

  // Modern
  {id: "apple", group: "modern", name: "Apple", description: "Hell, ruhig, Nachrichten wie in iMessage",
    orb: ["#FF375F", "#5E5CE6", "#64D2FF"], orbBase: "#101018",
    vars: {"--background": "#F5F5F7", "--page-bg": "#F5F5F7", "--surface": "#FFFFFF", "--surface-2": "#E9E9EB",
      "--text": "#1D1D1F", "--text-muted": "#6E6E73", "--control": "#FFFFFF", "--control-hover": "#F0F0F2",
      "--border": "#E3E3E6", "--accent": "#0071E3", "--accent-text": "#FFFFFF", "--link": "#0066CC",
      "--danger": "#FF3B30", "--warning": "#C27C00", "--user-bg": "#0A84FF", "--user-text": "#FFFFFF",
      "--radius": "14px", "--radius-sm": "10px",
      "--card-shadow": "0 1px 2px rgba(0, 0, 0, 0.04), 0 6px 18px rgba(0, 0, 0, 0.06)",
      "--control-shadow": "0 1px 2px rgba(0, 0, 0, 0.06)",
      "--font": "-apple-system, \"SF Pro Text\", \"Segoe UI Variable Text\", \"Segoe UI\", sans-serif",
      "--font-heading": "-apple-system, \"SF Pro Display\", \"Segoe UI Variable Display\", \"Segoe UI\", sans-serif"},
    viewCss: "h2 { font-size: 22px; font-weight: 700; letter-spacing: -0.01em; } th { color: #6E6E73; }"},
  {id: "apple-dark", group: "modern", name: "Apple Dunkel", description: "Wie Apple, im dunklen Modus",
    orb: ["#FF375F", "#5E5CE6", "#64D2FF"], orbBase: "#000000",
    vars: {"--background": "#000000", "--page-bg": "#000000", "--surface": "#1C1C1E", "--surface-2": "#2C2C2E",
      "--text": "#F5F5F7", "--text-muted": "#98989D", "--control": "#2C2C2E", "--control-hover": "#3A3A3C",
      "--border": "#38383A", "--accent": "#0A84FF", "--accent-text": "#FFFFFF", "--link": "#64A8FF",
      "--danger": "#FF453A", "--warning": "#FFD60A", "--user-bg": "#0A84FF", "--user-text": "#FFFFFF",
      "--radius": "14px", "--radius-sm": "10px",
      "--font": "-apple-system, \"SF Pro Text\", \"Segoe UI Variable Text\", \"Segoe UI\", sans-serif",
      "--font-heading": "-apple-system, \"SF Pro Display\", \"Segoe UI Variable Display\", \"Segoe UI\", sans-serif"},
    viewCss: "h2 { font-size: 22px; font-weight: 700; letter-spacing: -0.01em; }"},
  {id: "glass", group: "modern", name: "Glas", description: "Durchscheinende Flächen auf Farbverlauf",
    orb: ["#FFFFFF", "#9AD0FF", "#FFB3E6"], orbBase: "#5B4FA8", look: {gloss: true},
    vars: {"--background": "#8A7FD6",
      "--page-bg": "radial-gradient(circle at 15% 20%, #7EE8FA 0, transparent 45%), radial-gradient(circle at 85% 75%, #FF9AD5 0, transparent 50%), linear-gradient(135deg, #8EC5FC 0%, #B39DDB 50%, #E0C3FC 100%)",
      "--surface": "rgba(255, 255, 255, 0.32)", "--surface-2": "rgba(255, 255, 255, 0.45)",
      "--text": "#1E2140", "--text-muted": "#454B78", "--control": "rgba(255, 255, 255, 0.40)",
      "--control-hover": "rgba(255, 255, 255, 0.60)", "--border": "rgba(255, 255, 255, 0.65)",
      "--accent": "#3D3A9E", "--accent-text": "#FFFFFF", "--link": "#2C2A8A", "--user-bg": "rgba(61, 58, 158, 0.85)",
      "--user-text": "#FFFFFF", "--radius": "18px", "--radius-sm": "12px",
      "--card-shadow": "inset 0 1px 0 rgba(255, 255, 255, 0.7), 0 8px 24px rgba(40, 30, 120, 0.18)",
      "--control-shadow": "inset 0 1px 0 rgba(255, 255, 255, 0.6)",
      "--bubble-shadow": "0 4px 12px rgba(40, 30, 120, 0.25)"},
    viewCss: "html, body { background: transparent; }"},
  {id: "clay", group: "modern", name: "Clay", description: "Weiche, aufgeblasene Knete-Formen",
    orb: ["#FF8FB8", "#9B8CFF", "#7FE0D0"], orbBase: "#5A3E8C", look: {gloss: true},
    vars: {"--background": "#F1E7FF", "--page-bg": "#F1E7FF", "--surface": "#FFFFFF", "--surface-2": "#F8F2FF",
      "--text": "#3C2A57", "--text-muted": "#86739F", "--control": "#F6EEFF", "--control-hover": "#EEE2FF",
      "--border": "transparent", "--accent": "#8B5CF6", "--accent-text": "#FFFFFF", "--link": "#6D3FE0",
      "--user-bg": "#FFB8D4", "--user-text": "#4A2340", "--radius": "26px", "--radius-sm": "18px", "--bw": "0px",
      "--card-shadow": "12px 12px 26px rgba(150, 110, 200, 0.28), inset -6px -6px 14px rgba(150, 110, 200, 0.16), inset 6px 6px 14px rgba(255, 255, 255, 0.95)",
      "--control-shadow": "5px 5px 12px rgba(150, 110, 200, 0.28), inset -3px -3px 6px rgba(150, 110, 200, 0.20), inset 3px 3px 6px rgba(255, 255, 255, 0.9)",
      "--bubble-shadow": "6px 6px 14px rgba(220, 100, 150, 0.30), inset -4px -4px 8px rgba(200, 80, 130, 0.18), inset 4px 4px 8px rgba(255, 255, 255, 0.6)",
      "--inset-shadow": "inset 4px 4px 8px rgba(150, 110, 200, 0.22), inset -4px -4px 8px rgba(255, 255, 255, 0.9)"}},
  {id: "material", group: "modern", name: "Material", description: "Tonale Flächen, Pillen-Knöpfe",
    orb: ["#6750A4", "#7D5260", "#625B71"], orbBase: "#21005D",
    vars: {"--background": "#FEF7FF", "--page-bg": "#FEF7FF", "--surface": "#F7F2FA", "--surface-2": "#ECE6F0",
      "--text": "#1D1B20", "--text-muted": "#49454F", "--control": "#E8DEF8", "--control-hover": "#DCD0F0",
      "--border": "#CAC4D0", "--accent": "#6750A4", "--accent-text": "#FFFFFF", "--link": "#6750A4",
      "--danger": "#B3261E", "--warning": "#7D5700", "--user-bg": "#EADDFF", "--user-text": "#21005D",
      "--radius": "24px", "--radius-sm": "20px", "--bw": "0px",
      "--card-shadow": "0 1px 3px rgba(0, 0, 0, 0.10), 0 1px 2px rgba(0, 0, 0, 0.06)",
      "--font": "Roboto, \"Segoe UI\", sans-serif", "--font-heading": "Roboto, \"Segoe UI\", sans-serif"},
    viewCss: "h2 { font-size: 22px; font-weight: 400; }"},
  {id: "depth", group: "modern", name: "3D", description: "Tiefe, Glanzkanten, Raum",
    orb: ["#5B8CFF", "#8F6BFF", "#38D2FF"], orbBase: "#0E1430", look: {gloss: true},
    vars: {"--background": "#0B0F1A",
      "--page-bg": "radial-gradient(120% 70% at 50% -10%, #25325E 0%, #0B0F1A 62%)",
      "--surface": "#151B2E", "--surface-2": "#1B2340", "--text": "#E8ECF8", "--text-muted": "#8E98B8",
      "--control": "#1F2844", "--control-hover": "#273256", "--border": "#2B3659",
      "--accent": "#5B8CFF", "--accent-text": "#FFFFFF", "--link": "#9DB8FF",
      "--user-bg": "linear-gradient(180deg, #6A97FF 0%, #3F66DA 100%)", "--user-text": "#FFFFFF",
      "--radius": "16px", "--radius-sm": "10px",
      "--card-shadow": "inset 0 1px 0 rgba(255, 255, 255, 0.07), 0 14px 28px rgba(0, 0, 0, 0.45), 0 3px 8px rgba(0, 0, 0, 0.35)",
      "--control-shadow": "inset 0 1px 0 rgba(255, 255, 255, 0.10), 0 2px 5px rgba(0, 0, 0, 0.45)",
      "--bubble-shadow": "inset 0 1px 0 rgba(255, 255, 255, 0.25), 0 6px 14px rgba(20, 40, 120, 0.45)",
      "--inset-shadow": "inset 0 2px 6px rgba(0, 0, 0, 0.45)"}},
  {id: "neumorph", group: "modern", name: "Neumorph", description: "Weich herausgedrückte Flächen",
    orb: ["#6A7CF5", "#9FA9F7", "#B98DF0"], orbBase: "#3A4270", look: {gloss: true},
    vars: {"--background": "#E3E7EE", "--page-bg": "#E3E7EE", "--surface": "#E3E7EE", "--surface-2": "#E3E7EE",
      "--text": "#3A4256", "--text-muted": "#7D869A", "--control": "#E3E7EE", "--control-hover": "#DCE1E9",
      "--border": "transparent", "--accent": "#5A6CF0", "--accent-text": "#FFFFFF", "--link": "#4152D8",
      "--danger": "#D9475A", "--warning": "#B7860B", "--user-bg": "#E3E7EE", "--user-text": "#4152D8",
      "--radius": "18px", "--radius-sm": "12px", "--bw": "0px",
      "--card-shadow": "7px 7px 14px #C2C7D0, -7px -7px 14px #FFFFFF",
      "--control-shadow": "3px 3px 7px #C2C7D0, -3px -3px 7px #FFFFFF",
      "--bubble-shadow": "4px 4px 9px #C2C7D0, -4px -4px 9px #FFFFFF",
      "--inset-shadow": "inset 3px 3px 6px #C2C7D0, inset -3px -3px 6px #FFFFFF"},
    viewCss: "table { border-collapse: separate; border-spacing: 0; } th, td { border-bottom: none; } tbody tr:nth-child(odd) td { background: #DDE2EA; }"},

  // Retro
  {id: "gameboy", group: "retro", name: "Gameboy", description: "Handheld mit Gehäuse, grünem Bildschirm, Steuerkreuz",
    orb: ["#8BAC0F", "#9BBC0F", "#306230"], orbBase: "#0F380F", look: {pixel: true},
    vars: {"--background": "#C9C5BD",
      "--page-bg": "linear-gradient(180deg, #D4D0C8 0%, #C6C2BA 100%)",
      "--surface": "#9BBC0F", "--surface-2": "#8BAC0F", "--text": "#0F380F", "--text-muted": "#306230",
      "--control": "#8BAC0F", "--control-hover": "#7A9B0E", "--border": "#0F380F",
      "--accent": "#306230", "--accent-text": "#9BBC0F", "--link": "#0F380F", "--danger": "#0F380F",
      "--warning": "#0F380F", "--user-bg": "#306230", "--user-text": "#9BBC0F",
      "--radius": "0px", "--radius-sm": "0px", "--bw": "2px",
      "--font": "Consolas, \"Lucida Console\", \"Courier New\", monospace",
      "--font-heading": "Consolas, \"Lucida Console\", \"Courier New\", monospace"},
    viewCss: "html, body { background: #9BBC0F; } h2 { text-transform: uppercase; letter-spacing: 0.06em; } th { text-transform: uppercase; } th, td { border-bottom-width: 2px; }"},
  {id: "win95", group: "retro", name: "Win 95", description: "Graue Fenster mit Reliefkanten",
    orb: ["#000080", "#1084D0", "#00A0A0"], orbBase: "#000040", look: {pixel: true},
    vars: {"--background": "#C0C0C0", "--page-bg": "#C0C0C0", "--surface": "#FFFFFF", "--surface-2": "#C0C0C0",
      "--text": "#000000", "--text-muted": "#404040", "--control": "#C0C0C0", "--control-hover": "#C8C8C8",
      "--border": "transparent", "--accent": "#000080", "--accent-text": "#FFFFFF", "--link": "#0000EE",
      "--danger": "#C00000", "--warning": "#806000", "--user-bg": "#000080", "--user-text": "#FFFFFF",
      "--radius": "0px", "--radius-sm": "0px", "--bw": "0px",
      "--card-shadow": "inset -1px -1px #FFFFFF, inset 1px 1px #808080, inset -2px -2px #DFDFDF, inset 2px 2px #0A0A0A",
      "--control-shadow": "inset -1px -1px #0A0A0A, inset 1px 1px #FFFFFF, inset -2px -2px #808080, inset 2px 2px #DFDFDF",
      "--inset-shadow": "inset -1px -1px #FFFFFF, inset 1px 1px #808080, inset -2px -2px #DFDFDF, inset 2px 2px #0A0A0A",
      "--font": "Tahoma, \"Microsoft Sans Serif\", sans-serif", "--font-heading": "Tahoma, \"Microsoft Sans Serif\", sans-serif"},
    viewCss: "body { padding: 14px; } h2 { font-size: 14px; font-weight: bold; } table { border-collapse: collapse; } th { background: #C0C0C0; color: #000; font-weight: normal; box-shadow: inset -1px -1px #808080, inset 1px 1px #FFFFFF; } th, td { padding: 4px 6px; border-bottom: 1px solid #E0E0E0; } td:first-child { color: #000; }"},
  {id: "terminal", group: "retro", name: "Terminal", description: "Grüner Phosphor auf Schwarz",
    orb: ["#33FF66", "#1FAA44", "#B6FFC8"], orbBase: "#020A04", look: {pixel: true},
    vars: {"--background": "#050A06",
      "--page-bg": "repeating-linear-gradient(0deg, rgba(0, 0, 0, 0.25) 0 1px, transparent 1px 3px), #07100A",
      "--surface": "#08140C", "--surface-2": "#0C1C11", "--text": "#5CFF85", "--text-muted": "#2FA552",
      "--control": "#0C1C11", "--control-hover": "#123020", "--border": "#1F6B36",
      "--accent": "#5CFF85", "--accent-text": "#03140A", "--link": "#B6FFC8", "--danger": "#FF5555",
      "--warning": "#E8FF5C", "--user-bg": "transparent", "--user-text": "#B6FFC8",
      "--radius": "0px", "--radius-sm": "0px",
      "--font": "\"Cascadia Mono\", Consolas, \"Courier New\", monospace",
      "--font-heading": "\"Cascadia Mono\", Consolas, \"Courier New\", monospace"},
    viewCss: "body { text-shadow: 0 0 4px rgba(92, 255, 133, 0.45); } h2::before { content: '# '; } th { text-transform: uppercase; }"},
  {id: "vapor", group: "retro", name: "Vaporwave", description: "Sonnenuntergang, Neon-Raster, 80er",
    orb: ["#FF71CE", "#01CDFE", "#B967FF"], orbBase: "#2A0A4A", look: {gloss: true},
    vars: {"--background": "#1A0533",
      "--page-bg": "linear-gradient(180deg, #1A0533 0%, #4B0F6B 45%, #B0306B 78%, #FF7A45 100%)",
      "--surface": "rgba(26, 5, 51, 0.78)", "--surface-2": "rgba(60, 15, 90, 0.85)", "--text": "#FFE8FB",
      "--text-muted": "#F7A8E6", "--control": "rgba(60, 15, 90, 0.85)", "--control-hover": "rgba(90, 25, 120, 0.9)",
      "--border": "#FF71CE", "--accent": "#01CDFE", "--accent-text": "#1A0533", "--link": "#05FFA1",
      "--warning": "#FFFB96", "--user-bg": "linear-gradient(90deg, #FF71CE, #B967FF)", "--user-text": "#FFFFFF",
      "--radius": "4px", "--radius-sm": "3px",
      "--card-shadow": "4px 4px 0 #01CDFE", "--bubble-shadow": "3px 3px 0 #01CDFE",
      "--font": "\"Trebuchet MS\", \"Segoe UI\", sans-serif", "--font-heading": "\"Trebuchet MS\", \"Segoe UI\", sans-serif"},
    viewCss: "h2 { font-style: italic; text-transform: uppercase; letter-spacing: 0.12em; color: #01CDFE; text-shadow: 2px 2px 0 #FF71CE; } th { color: #FFFB96; }"},
  {id: "newspaper", group: "retro", name: "Zeitung", description: "Zeitungspapier, Serifen, Linien",
    orb: ["#4A4A4A", "#8A8A8A", "#2A2A2A"], orbBase: "#EDE7DA",
    vars: {"--background": "#F3EEE3", "--page-bg": "#F3EEE3", "--surface": "#F8F4EB", "--surface-2": "#EFE9DC",
      "--text": "#161616", "--text-muted": "#555048", "--control": "#F8F4EB", "--control-hover": "#E9E2D3",
      "--border": "#161616", "--accent": "#161616", "--accent-text": "#F8F4EB", "--link": "#7A1F1F",
      "--danger": "#9E1B1B", "--warning": "#7A1F1F", "--user-bg": "transparent", "--user-text": "#161616",
      "--radius": "0px", "--radius-sm": "0px",
      "--font": "Georgia, \"Times New Roman\", serif", "--font-heading": "\"Times New Roman\", Georgia, serif"},
    viewCss: "h2 { font-size: 28px; font-weight: 900; padding-bottom: 6px; border-bottom: 4px double #161616; } p { font-style: italic; } th { text-transform: uppercase; letter-spacing: 0.1em; font-size: 10px; color: #161616; } td { border-bottom-style: dotted; }"},
  {id: "deco", group: "retro", name: "Art déco", description: "Schwarz und Gold, 1920er",
    orb: ["#D4AF37", "#F3D98B", "#9C7A1E"], orbBase: "#0E0E0E", look: {gloss: true},
    vars: {"--background": "#0E0E0E",
      "--page-bg": "repeating-linear-gradient(45deg, rgba(212, 175, 55, 0.05) 0 1px, transparent 1px 16px), repeating-linear-gradient(-45deg, rgba(212, 175, 55, 0.05) 0 1px, transparent 1px 16px), #0E0E0E",
      "--surface": "#141414", "--surface-2": "#1B1B1B", "--text": "#F3E9D2", "--text-muted": "#BFA76A",
      "--control": "#1B1B1B", "--control-hover": "#262217", "--border": "#D4AF37",
      "--accent": "#D4AF37", "--accent-text": "#0E0E0E", "--link": "#F3D98B", "--warning": "#F3D98B",
      "--user-bg": "#1B1B1B", "--user-text": "#F3D98B", "--radius": "0px", "--radius-sm": "0px",
      "--card-shadow": "0 0 0 3px #0E0E0E, 0 0 0 4px #D4AF37",
      "--font": "Georgia, \"Palatino Linotype\", serif", "--font-heading": "\"Bodoni MT\", Didot, Georgia, serif"},
    viewCss: "h2 { text-transform: uppercase; letter-spacing: 0.25em; text-align: center; color: #D4AF37; font-weight: 400; } h2::before, h2::after { content: ' \\25C6  '; font-size: 10px; vertical-align: middle; } th { text-transform: uppercase; letter-spacing: 0.15em; color: #D4AF37; }"},

  // Ausdrucksstark
  {id: "maximal", group: "bold", name: "Maximal", description: "Laut, bunt, Muster",
    orb: ["#FF4FA3", "#FFD23F", "#7CF5FF"], orbBase: "#2B0B3F",
    vars: {"--background": "#2B0B3F",
      "--page-bg": "radial-gradient(circle at 12% 18%, rgba(255, 79, 163, 0.35) 0 7%, transparent 7.5%), radial-gradient(circle at 88% 64%, rgba(124, 245, 255, 0.22) 0 9%, transparent 9.5%), radial-gradient(circle at 70% 8%, rgba(255, 210, 63, 0.28) 0 4%, transparent 4.5%), repeating-linear-gradient(45deg, rgba(255, 210, 63, 0.07) 0 10px, transparent 10px 22px), #2B0B3F",
      "--surface": "#3D1358", "--surface-2": "#4B1A6B", "--text": "#FFF4E0", "--text-muted": "#FFC6E5",
      "--control": "#5A2080", "--control-hover": "#6E2A9A", "--border": "#FF4FA3",
      "--accent": "#FFD23F", "--accent-text": "#2B0B3F", "--link": "#7CF5FF", "--warning": "#FFD23F",
      "--user-bg": "linear-gradient(135deg, #FF4FA3 0%, #FF8A3D 100%)", "--user-text": "#FFFFFF",
      "--radius": "22px", "--radius-sm": "14px", "--bw": "2px",
      "--card-shadow": "6px 6px 0 #FFD23F", "--control-shadow": "none", "--bubble-shadow": "4px 4px 0 #7CF5FF",
      "--font-heading": "Georgia, \"Times New Roman\", serif"},
    viewCss: "h2 { font-style: italic; font-size: 28px; color: #FFD23F; } th { color: #7CF5FF; } td { border-bottom-style: dashed; }"},
  {id: "brutal", group: "bold", name: "Brutal", description: "Schwarze Kanten, harte Schatten",
    orb: ["#FF6B35", "#90A8FF", "#FFD600"], orbBase: "#111111",
    vars: {"--background": "#FFF4D6", "--page-bg": "#FFF4D6", "--surface": "#FFFFFF", "--surface-2": "#FFFFFF",
      "--text": "#000000", "--text-muted": "#3D3D3D", "--control": "#FFFFFF", "--control-hover": "#FFE27A",
      "--border": "#000000", "--accent": "#FF6B35", "--accent-text": "#000000", "--link": "#1D3FE0",
      "--danger": "#E0002B", "--warning": "#000000", "--user-bg": "#90A8FF", "--user-text": "#000000",
      "--radius": "8px", "--radius-sm": "6px", "--bw": "2px",
      "--card-shadow": "5px 5px 0 #000000", "--control-shadow": "2px 2px 0 #000000",
      "--bubble-shadow": "3px 3px 0 #000000",
      "--font": "\"Segoe UI\", Arial, sans-serif", "--font-heading": "\"Arial Black\", \"Segoe UI Black\", sans-serif"},
    viewCss: "h2 { font-size: 22px; } table { border: 2px solid #000; } th { background: #FFD600; color: #000; font-weight: 800; } th, td { padding: 8px 10px; border-bottom: 2px solid #000; }"},
  {id: "comic", group: "bold", name: "Comic", description: "Rasterpunkte, dicke Linien, Sprechblasen",
    orb: ["#FFD23F", "#E63946", "#4CC9F0"], orbBase: "#1D3557",
    vars: {"--background": "#FFF3B0",
      "--page-bg": "radial-gradient(rgba(230, 57, 70, 0.22) 1.3px, transparent 1.8px) 0 0 / 9px 9px, #FFF3B0",
      "--surface": "#FFFFFF", "--surface-2": "#FFFFFF", "--text": "#111111", "--text-muted": "#444444",
      "--control": "#FFFFFF", "--control-hover": "#FFE066", "--border": "#111111",
      "--accent": "#E63946", "--accent-text": "#FFFFFF", "--link": "#1D3557", "--danger": "#E63946",
      "--warning": "#111111", "--user-bg": "#4CC9F0", "--user-text": "#111111",
      "--radius": "16px", "--radius-sm": "12px", "--bw": "3px",
      "--card-shadow": "5px 5px 0 #111111", "--control-shadow": "2px 2px 0 #111111", "--bubble-shadow": "3px 3px 0 #111111",
      "--font": "\"Comic Sans MS\", \"Comic Neue\", cursive", "--font-heading": "Impact, \"Arial Black\", sans-serif"},
    viewCss: "h2 { font-size: 26px; font-weight: 400; letter-spacing: 0.04em; text-transform: uppercase; color: #E63946; text-shadow: 2px 2px 0 #111; } th, td { border-bottom: 2px solid #111; }"},
  {id: "bauhaus", group: "bold", name: "Bauhaus", description: "Kreis, Quadrat, Dreieck in Grundfarben",
    orb: ["#E53935", "#1E4FA0", "#F9C80E"], orbBase: "#111111",
    vars: {"--background": "#F2EBDD",
      "--page-bg": "#F2EBDD",
      "--surface": "#FFFFFF", "--surface-2": "#F7F2E8", "--text": "#111111", "--text-muted": "#444444",
      "--control": "#FFFFFF", "--control-hover": "#F9C80E", "--border": "#111111",
      "--accent": "#E53935", "--accent-text": "#FFFFFF", "--link": "#1E4FA0", "--warning": "#1E4FA0",
      "--user-bg": "#1E4FA0", "--user-text": "#FFFFFF", "--radius": "0px", "--radius-sm": "0px", "--bw": "2px",
      "--font": "Bahnschrift, Futura, \"Century Gothic\", sans-serif",
      "--font-heading": "Bahnschrift, Futura, \"Century Gothic\", sans-serif"},
    viewCss: "h2 { font-size: 24px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; } h2::after { content: ''; display: inline-block; width: 12px; height: 12px; margin-left: 10px; border-radius: 50%; background: #E53935; } th { background: #111; color: #F2EBDD; padding-left: 8px; } td:first-child { padding-left: 8px; } th, td { border-bottom: 2px solid #111; }"},
  {id: "cyber", group: "bold", name: "Cyberpunk", description: "Gelb, Cyan und Magenta, abgeschnittene Ecken",
    orb: ["#FCEE0A", "#00F0FF", "#FF003C"], orbBase: "#0D0221",
    vars: {"--background": "#0D0221",
      "--page-bg": "linear-gradient(rgba(0, 240, 255, 0.06) 1px, transparent 1px) 0 0 / 100% 22px, #0D0221",
      "--surface": "#120836", "--surface-2": "#1A0E47", "--text": "#E8F9FF", "--text-muted": "#7FD6E6",
      "--control": "#1A0E47", "--control-hover": "#26155E", "--border": "#FCEE0A",
      "--accent": "#FCEE0A", "--accent-text": "#000000", "--link": "#00F0FF", "--danger": "#FF003C",
      "--warning": "#FCEE0A", "--user-bg": "#FF003C", "--user-text": "#FFFFFF", "--radius": "0px", "--radius-sm": "0px",
      "--font": "Bahnschrift, \"Segoe UI\", sans-serif", "--font-heading": "Bahnschrift, \"Agency FB\", \"Segoe UI\", sans-serif"},
    viewCss: "h2 { text-transform: uppercase; letter-spacing: 0.18em; color: #FCEE0A; } h2::before { content: '// '; color: #FF003C; } th { color: #00F0FF; text-transform: uppercase; letter-spacing: 0.1em; } th, td { border-bottom-color: rgba(252, 238, 10, 0.35); }"},

  // Spiele & Getränke: nur der Stil, gezeichnet ohne Logos, Figuren oder Texturen der Vorbilder
  {id: "minecraft", group: "fun", name: "Minecraft", description: "Erde, Stein und grobe Pixel, Block für Block",
    orb: ["#5FAB3A", "#8B5A2B", "#7ED0E8"], orbBase: "#2B1C10", look: {pixel: true},
    vars: {"--background": "#593D29", "--page-bg": pixelTile(["#866043", "#866043", "#79553A", "#9B7653", "#6B4A30"]),
      "--surface": "rgba(24, 18, 13, 0.84)", "--surface-2": "rgba(70, 58, 46, 0.92)", "--text": "#FFFFFF",
      "--text-muted": "#CFC8BC", "--control": "#6F6F6F", "--control-hover": "#858585", "--border": "#000000",
      "--accent": "#4C7A2A", "--accent-text": "#FFFFFF", "--link": "#7FE0FF", "--danger": "#FF6B6B",
      "--warning": "#FFD83D", "--user-bg": "#4C7A2A", "--user-text": "#FFFFFF", "--radius": "0px", "--radius-sm": "0px",
      "--bw": "2px", "--card-shadow": "inset 2px 2px 0 rgba(255, 255, 255, 0.16), inset -2px -2px 0 rgba(0, 0, 0, 0.5)",
      "--control-shadow": "inset 2px 2px 0 rgba(255, 255, 255, 0.35), inset -2px -2px 0 rgba(0, 0, 0, 0.4)",
      "--bubble-shadow": "inset -2px -2px 0 rgba(0, 0, 0, 0.3), inset 2px 2px 0 rgba(255, 255, 255, 0.18)",
      "--inset-shadow": "inset 2px 2px 0 rgba(0, 0, 0, 0.6)",
      "--font": "\"Cascadia Mono\", Consolas, monospace", "--font-heading": "\"Cascadia Mono\", Consolas, monospace"},
    viewCss: "html, body { background: #231B14; color: #FFF; } h2 { color: #FFD83D; text-shadow: 2px 2px 0 #4A3C10; } th { color: #8FE36A; } th, td { border-bottom: 2px solid #4A3F33; }"},
  {id: "roblox", group: "fun", name: "Roblox", description: "Knallige Bausteine mit Noppen, dicke Knöpfe",
    orb: ["#E2231A", "#0D69AC", "#F5CD30"], orbBase: "#1B1B1F", look: {gloss: true},
    vars: {"--background": "#0D69AC",
      "--page-bg": "radial-gradient(circle at 12px 12px, rgba(255, 255, 255, 0.20) 0 7px, rgba(0, 0, 0, 0.12) 7px 8.5px, transparent 9px) 0 0 / 24px 24px, #0D69AC",
      "--surface": "#FFFFFF", "--surface-2": "#EEF2F6", "--text": "#1B1F27", "--text-muted": "#5B6472",
      "--control": "#FFFFFF", "--control-hover": "#FFE680", "--border": "#0A4F82", "--accent": "#D81E15",
      "--accent-text": "#FFFFFF", "--link": "#0B5FB0", "--danger": "#C4160E", "--warning": "#F5CD30",
      "--user-bg": "#2F7D32", "--user-text": "#FFFFFF", "--radius": "12px", "--radius-sm": "9px", "--bw": "0px",
      "--card-shadow": "0 6px 0 rgba(0, 0, 0, 0.28)", "--control-shadow": "0 4px 0 rgba(0, 0, 0, 0.25)",
      "--bubble-shadow": "0 4px 0 rgba(0, 0, 0, 0.20)",
      "--font": "\"Arial Rounded MT Bold\", \"Trebuchet MS\", \"Segoe UI\", sans-serif",
      "--font-heading": "\"Arial Black\", \"Arial Rounded MT Bold\", sans-serif"},
    viewCss: "h2 { color: #0D69AC; font-size: 24px; } th { background: #F5CD30; color: #1B1F27; padding-left: 8px; } td:first-child { padding-left: 8px; }"},
  {id: "white-monster", group: "fun", name: "White Monster", description: "Eiskaltes Weiß, gebürstetes Silber, null Zucker",
    orb: ["#DCE6EE", "#8FD8F0", "#9AA6B2"], orbBase: "#0C0D0F", look: {gloss: true},
    vars: {"--background": "#E4E9EE",
      "--page-bg": "linear-gradient(105deg, #FFFFFF 0%, #E4E9EE 28%, #FAFCFD 46%, #CCD4DC 72%, #F2F5F7 100%)",
      "--surface": "#FFFFFF", "--surface-2": "#EEF1F4", "--text": "#0C0D0F", "--text-muted": "#59626C",
      "--control": "#FFFFFF", "--control-hover": "#DDF1F9", "--border": "#0C0D0F", "--accent": "#0C0D0F",
      "--accent-text": "#FFFFFF", "--link": "#006E94", "--danger": "#C4161C", "--warning": "#0093C4",
      "--user-bg": "#0C0D0F", "--user-text": "#FFFFFF", "--radius": "2px", "--radius-sm": "2px", "--bw": "1px",
      "--card-shadow": "0 10px 26px rgba(30, 45, 60, 0.16)",
      "--font": "Bahnschrift, \"Segoe UI\", sans-serif",
      "--font-heading": "\"Bahnschrift Condensed\", Bahnschrift, Impact, sans-serif"},
    viewCss: "h2 { font-style: italic; font-weight: 800; font-size: 26px; text-transform: uppercase; letter-spacing: 0.03em; border-bottom: 3px solid #8FD8F0; padding-bottom: 4px; } th { text-transform: uppercase; letter-spacing: 0.08em; color: #0C0D0F; }"},
  {id: "spezi", group: "fun", name: "Paulaner Spezi", description: "Cola trifft Orange im Biergarten",
    orb: ["#F28C1E", "#5A2A12", "#FFC24A"], orbBase: "#2A1208", look: {gloss: true},
    vars: {"--background": "#F28C1E",
      "--page-bg": "linear-gradient(135deg, #FFB347 0%, #F28C1E 34%, #A2501A 66%, #4A2210 100%)",
      "--surface": "#FFF8EC", "--surface-2": "#FFEFD6", "--text": "#33190C", "--text-muted": "#7A5A44",
      "--control": "#FFF8EC", "--control-hover": "#FFE3B8", "--border": "#4A2210", "--accent": "#1F6FB5",
      "--accent-text": "#FFFFFF", "--link": "#1A5F9E", "--danger": "#B3261E", "--warning": "#D9690A",
      "--user-bg": "#F7A23B", "--user-text": "#2A1208", "--radius": "14px", "--radius-sm": "10px", "--bw": "2px",
      "--card-shadow": "0 6px 16px rgba(60, 25, 5, 0.32)", "--bubble-shadow": "0 2px 5px rgba(60, 25, 5, 0.25)",
      "--font": "\"Trebuchet MS\", \"Segoe UI\", sans-serif", "--font-heading": "Georgia, \"Times New Roman\", serif"},
    viewCss: "h2 { font-style: italic; color: #A2501A; border-bottom: 3px dotted #F28C1E; padding-bottom: 4px; } th { color: #1F6FB5; }"},

  // Besonders
  {id: "eco", group: "special", name: "Nachhaltig", description: "Flach, klare Linien, kräftige Flächen, ohne Animation",
    orb: ["#7ED957", "#00AEEF", "#E9B7A9"], orbBase: "#1565C0", look: {still: true},
    vars: {"--background": "#FFFFFF", "--page-bg": "#FFFFFF", "--surface": "#FFFFFF", "--surface-2": "#F4F4F4",
      "--text": "#000000", "--text-muted": "#3A3A3A", "--control": "#FFFFFF", "--control-hover": "#E8F7FD",
      "--border": "#000000", "--accent": "#000000", "--accent-text": "#FFFFFF", "--link": "#000000",
      "--danger": "#D7261E", "--warning": "#FF5A1F", "--user-bg": "#00AEEF", "--user-text": "#000000",
      "--radius": "0px", "--radius-sm": "0px", "--bw": "2px",
      "--font": "\"Segoe UI\", system-ui, sans-serif", "--font-heading": "\"Segoe UI Variable Display\", \"Segoe UI\", system-ui, sans-serif"},
    viewCss: "html, body { background: #00AEEF; } body { padding: 22px 24px; } h2 { font-size: 24px; font-weight: 700; color: #000; } p { color: #000; } th, td { border-bottom: 1.5px solid #000; color: #000; } td:first-child { color: #000; } th { font-weight: 700; }"},
  {id: "paper", group: "special", name: "Papier", description: "Liniertes Heft, Handschrift, Klebezettel",
    orb: ["#1F3A93", "#5B7BD5", "#E53935"], orbBase: "#FFFDF5",
    vars: {"--background": "#FFFDF5",
      "--page-bg": "linear-gradient(90deg, transparent 5px, rgba(229, 57, 53, 0.45) 5px 6px, transparent 6px), repeating-linear-gradient(0deg, rgba(80, 120, 200, 0.18) 0 1px, transparent 1px 24px), #FFFDF5",
      "--surface": "#FFFEF9", "--surface-2": "#FFF8E1", "--text": "#1F3A93", "--text-muted": "#5B6B9A",
      "--control": "#FFFEF9", "--control-hover": "#FFF8D6", "--border": "#B8C4E2",
      "--accent": "#1F3A93", "--accent-text": "#FFFFFF", "--link": "#C62828", "--warning": "#C62828",
      "--user-bg": "#FFF59D", "--user-text": "#333333", "--radius": "3px", "--radius-sm": "3px",
      "--card-shadow": "0 2px 6px rgba(0, 0, 0, 0.10)", "--bubble-shadow": "2px 3px 6px rgba(0, 0, 0, 0.15)",
      "--font": "\"Segoe Print\", \"Bradley Hand\", \"Comic Sans MS\", cursive",
      "--font-heading": "\"Segoe Print\", \"Bradley Hand\", \"Comic Sans MS\", cursive"},
    viewCss: "html, body { background: repeating-linear-gradient(0deg, rgba(80, 120, 200, 0.18) 0 1px, transparent 1px 26px), #FFFEF9; } h2 { text-decoration: underline wavy #C62828; text-underline-offset: 4px; } th, td { border-bottom: none; }"},
  {id: "blueprint", group: "special", name: "Blaupause", description: "Technische Zeichnung auf Millimeterpapier",
    orb: ["#FFFFFF", "#9CC3F0", "#5E95D8"], orbBase: "#123C70",
    vars: {"--background": "#1D4F91",
      "--page-bg": "linear-gradient(rgba(255, 255, 255, 0.16) 1px, transparent 1px) 0 0 / 100% 60px, linear-gradient(90deg, rgba(255, 255, 255, 0.16) 1px, transparent 1px) 0 0 / 60px 100%, linear-gradient(rgba(255, 255, 255, 0.07) 1px, transparent 1px) 0 0 / 100% 12px, linear-gradient(90deg, rgba(255, 255, 255, 0.07) 1px, transparent 1px) 0 0 / 12px 100%, #1D4F91",
      "--surface": "rgba(22, 64, 120, 0.82)", "--surface-2": "rgba(255, 255, 255, 0.08)", "--text": "#F2F7FF",
      "--text-muted": "#A9C4EA", "--control": "rgba(255, 255, 255, 0.06)", "--control-hover": "rgba(255, 255, 255, 0.14)",
      "--border": "rgba(242, 247, 255, 0.75)", "--accent": "#F2F7FF", "--accent-text": "#1D4F91", "--link": "#FFE08A",
      "--warning": "#FFE08A", "--user-bg": "transparent", "--user-text": "#F2F7FF", "--radius": "0px", "--radius-sm": "0px",
      "--font": "\"Cascadia Mono\", Consolas, monospace", "--font-heading": "\"Cascadia Mono\", Consolas, monospace"},
    viewCss: "h2 { text-transform: uppercase; letter-spacing: 0.2em; font-weight: 400; } h2::after { content: '  [ M 1:1 ]'; font-size: 10px; color: #A9C4EA; } th, td { border-bottom: 1px dashed rgba(242, 247, 255, 0.5); }"},
  {id: "reader", group: "special", name: "E-Reader", description: "Sepia wie ein Buch, ruhig für die Augen",
    orb: ["#8B5A2B", "#C08A55", "#5E3B1A"], orbBase: "#F4ECD8",
    vars: {"--background": "#F4ECD8", "--page-bg": "#F4ECD8", "--surface": "#FBF5E6", "--surface-2": "#EFE4CB",
      "--text": "#3B2F1E", "--text-muted": "#7A6A52", "--control": "#FBF5E6", "--control-hover": "#EFE4CB",
      "--border": "#DCCDAE", "--accent": "#8B5A2B", "--accent-text": "#FFFFFF", "--link": "#8B5A2B",
      "--warning": "#8B5A2B", "--user-bg": "#EADFC4", "--user-text": "#3B2F1E", "--radius": "6px", "--radius-sm": "5px",
      "--font": "Georgia, \"Palatino Linotype\", serif", "--font-heading": "Georgia, \"Palatino Linotype\", serif"},
    viewCss: "body { font-size: 14px; } h2 { font-weight: 400; font-style: italic; font-size: 22px; }"},
  {id: "contrast", group: "special", name: "Kontrast", description: "Hoher Kontrast, große Schrift, gut lesbar",
    orb: ["#FFFF00", "#00FFFF", "#FFFFFF"], orbBase: "#000000",
    vars: {"--background": "#000000", "--page-bg": "#000000", "--surface": "#000000", "--surface-2": "#000000",
      "--text": "#FFFFFF", "--text-muted": "#FFFF00", "--control": "#000000", "--control-hover": "#333333",
      "--border": "#FFFFFF", "--accent": "#FFFF00", "--accent-text": "#000000", "--link": "#00FFFF",
      "--danger": "#FF6666", "--warning": "#FFFF00", "--user-bg": "#000000", "--user-text": "#FFFFFF",
      "--radius": "4px", "--radius-sm": "4px", "--bw": "2px",
      "--font": "\"Segoe UI\", Arial, sans-serif", "--font-heading": "\"Segoe UI\", Arial, sans-serif"},
    viewCss: "body { font-size: 15px; } td:first-child, th { color: #FFFF00; } th, td { border-bottom: 2px solid #FFFFFF; }"},
];

// Abschnitte im Design-Panel, in dieser Reihenfolge
const THEME_GROUPS = [
  {id: "colors", label: "Farben"},
  {id: "modern", label: "Modern"},
  {id: "retro", label: "Retro"},
  {id: "bold", label: "Ausdrucksstark"},
  {id: "fun", label: "Spiele & Getränke"},
  {id: "special", label: "Besonders"},
];

const THEME_VARIABLES = ["--background", "--page-bg", "--surface", "--surface-2", "--text", "--text-muted",
  "--control", "--control-hover", "--border", "--accent", "--accent-text", "--link", "--danger", "--warning",
  "--user-bg", "--user-text", "--radius", "--radius-sm", "--bw", "--card-shadow", "--control-shadow",
  "--bubble-shadow", "--inset-shadow", "--font", "--font-heading"];

const Appearance = (() => {
  const STORAGE = {theme: "pda.theme", avatar: "pda.avatar"};
  const defaults = {};   // Werte aus theme.css, Grundlage für alle Designs
  let theme = THEMES[0];
  let avatarStyle = "nebula";

  // Browser-Speicher kann fehlen oder gesperrt sein - dann gilt einfach der Standard.
  function load(key) {
    try { return window.localStorage.getItem(key); } catch (error) { return null; }
  }
  function store(key, value) {
    try { window.localStorage.setItem(key, value); } catch (error) { /* nur nicht gemerkt */ }
  }

  function themeVars(option) {
    return Object.assign({}, defaults, option.vars);
  }

  function applyTheme(id, remember = true) {
    theme = THEMES.find(candidate => candidate.id === id) || THEMES[0];
    const root = document.documentElement;
    for (const [name, value] of Object.entries(themeVars(theme))) root.style.setProperty(name, value);
    root.dataset.theme = theme.id;
    Avatar.setColors(theme.orb, theme.orbBase, theme.look);
    if (remember) store(STORAGE.theme, theme.id);
    document.dispatchEvent(new Event("appearancechange"));
    updatePanel();
  }

  function applyAvatar(id, remember = true) {
    avatarStyle = Avatar.STYLES.some(style => style.id === id) ? id : "nebula";
    Avatar.setStyle(avatarStyle);
    if (remember) store(STORAGE.avatar, avatarStyle);
    updatePanel();
  }

  // HTML der Ansicht im Design; der <style>-Block kommt nach den eigenen Styles des Templates.
  function themedHtml(html) {
    const vars = themeVars(theme);
    const lines = THEME_VARIABLES.map(name => `${name}: ${vars[name]};`).join(" ");
    const style = `<style id="pda-theme">:root { ${lines} } ${theme.viewCss || ""}</style>`;
    if (/<\/head>/i.test(html)) return html.replace(/<\/head>/i, `${style}</head>`);
    if (/^\s*<!doctype[^>]*>/i.test(html)) return html.replace(/^\s*<!doctype[^>]*>/i, match => match + style);
    return style + html;
  }

  // --- Auswahl-Panel ---------------------------------------------------------------------------

  const panel = document.getElementById("design-panel");
  const button = document.getElementById("design-button");
  const groupsBox = document.getElementById("design-groups");
  const grids = {};
  const avatarList = document.getElementById("design-avatars");
  const description = document.getElementById("design-description");

  function node(tag, className, text) {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text !== undefined) element.textContent = text;
    return element;
  }

  // Vorschau: Hintergrund, eine Mini-Karte in Form und Schatten des Designs, Akzentpunkt
  function buildPanel() {
    for (const group of THEME_GROUPS) {
      groupsBox.appendChild(node("div", "design-label", group.label));
      grids[group.id] = groupsBox.appendChild(node("div", "design-grid"));
    }
    for (const option of THEMES) {
      const vars = themeVars(option);
      const card = node("button", "theme-card");
      card.type = "button";
      card.dataset.theme = option.id;
      if (option.description) card.title = option.description;
      const swatch = node("span", "theme-swatch");
      swatch.style.background = vars["--page-bg"];
      const mini = node("span", "theme-swatch-card");
      mini.style.background = vars["--surface"];
      mini.style.border = `${vars["--bw"]} solid ${vars["--border"]}`;
      mini.style.borderRadius = `${Math.min(parseInt(vars["--radius"], 10) || 0, 6)}px`;
      const dot = node("span", "theme-swatch-accent");
      dot.style.background = vars["--accent"];
      mini.appendChild(dot);
      swatch.appendChild(mini);
      card.append(swatch, node("span", "theme-name", option.name));
      card.addEventListener("click", () => applyTheme(option.id));
      grids[option.group].appendChild(card);
    }
    for (const option of Avatar.STYLES) {
      const card = node("button", "avatar-card");
      card.type = "button";
      card.dataset.avatar = option.id;
      card.title = option.description;
      const canvas = node("canvas", "orb");
      canvas.style.width = canvas.style.height = "36px";
      Avatar.mount(canvas, {size: 36, style: option.id});
      card.append(canvas, node("span", "avatar-name", option.name));
      card.addEventListener("click", () => applyAvatar(option.id));
      avatarList.appendChild(card);
    }
  }

  function updatePanel() {
    for (const grid of Object.values(grids)) {
      for (const card of grid.children) card.classList.toggle("active", card.dataset.theme === theme.id);
    }
    for (const card of avatarList.children) card.classList.toggle("active", card.dataset.avatar === avatarStyle);
    description.textContent = theme.description ? `${theme.name}: ${theme.description}` : "";
  }

  function openPanel() {
    panel.hidden = false;
    button.classList.add("active");
    Avatar.redraw();   // Vorschauen zeichnen, solange sie sichtbar sind
  }

  function closePanel() {
    panel.hidden = true;
    button.classList.remove("active");
  }

  button.addEventListener("click", event => {
    event.stopPropagation();
    if (panel.hidden) openPanel(); else closePanel();
  });
  document.getElementById("design-close").addEventListener("click", closePanel);
  document.addEventListener("click", event => {
    if (!panel.hidden && !panel.contains(event.target) && event.target !== button) closePanel();
  });
  document.addEventListener("keydown", event => {
    if (event.key === "Escape" && !panel.hidden) closePanel();
  });

  const computed = getComputedStyle(document.documentElement);
  for (const name of THEME_VARIABLES) defaults[name] = computed.getPropertyValue(name).trim();
  buildPanel();
  Avatar.mount(document.getElementById("agent-orb"), {size: 28});
  Avatar.mount(document.getElementById("listening-orb"), {size: 96});
  document.body.dataset.agent = Avatar.state;
  applyTheme(load(STORAGE.theme) || THEMES[0].id, false);
  applyAvatar(load(STORAGE.avatar) || "nebula", false);

  return {themedHtml, applyTheme, applyAvatar, closePanel, get theme() { return theme.id; }};
})();
