# Personal Digital Agent (PDA)

Desktop-Anwendung für macOS und Windows: Ein Klick auf das Symbol öffnet ein Popup mit einem
**Anzeigebereich** (oben) und einem **Chat mit einem Assistenten** (unten). Rechtsklick öffnet
das Kontextmenü mit „Beenden“.

Das Projekt ist die **Grundlage** für einen persönlichen Assistenten mit Gemini als
Sprachmodell. Er hat drei **Fähigkeiten**: Morning-Briefing, Weg zum nächsten Termin
(Travel) und Organisation von Nachrichten und Terminen (im Projektplan „Assistant²“). Der
Assistent nutzt Werkzeuge von **MCP-Servern**
(eingetragen in [mcp_servers.json](mcp_servers.json)). Die Fähigkeiten selbst sind noch nicht
umgesetzt. Feste Befehle wie `hilfe`, `uhrzeit`, `system`, `start` und `neu` funktionieren
weiterhin ohne Modell.

## Starten

Python 3.12 oder 3.13 verwenden. Auf beiden Betriebssystemen startet dieselbe `main.py`;
die Plattform wird automatisch erkannt. Unter macOS erscheint das Symbol oben in der
Menüleiste, unter Windows unten im Infobereich. Ein Klick öffnet bzw. schließt das Popup.
Rechtsklick zeigt das Menü mit „Proaktive Meldung testen“ und „Beenden“.

### macOS

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python main.py
```

Danach kann auch `Start.command` per Doppelklick verwendet werden. Die Anwendung bleibt
im Hintergrund aktiv und hat auf dem Mac kein zusätzliches Dock-Symbol. Das Popup öffnet
sich unter dem Menüleistensymbol und bleibt auch beim Vergrößern im sichtbaren Bildschirm.
Die genaue Symbolposition bestimmt die Anordnung der Menüleiste; bei wenig Platz neben
der Notch können Symbole verborgen sein.

### Windows

```bat
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python main.py
```

Danach kann auch `Start.bat` verwendet werden. Das Popup öffnet sich oberhalb des Symbols.

### PyCharm

Als Projektinterpreter die lokale Umgebung auswählen: `.venv/bin/python` am Mac bzw.
`.venv\Scripts\python.exe` unter Windows. Die gemeinsame Startkonfiguration heißt
**Personal Digital Agent**. Konfiguration auswählen und auf ▶ drücken. Alternativ `main.py` starten.

### Sprachmodell

Standardmäßig verwendet der Assistent **Gemini 3.5 Flash-Lite** über die Google Gemini API.
Erstelle in [Google AI Studio](https://aistudio.google.com/api-keys) einen API-Schlüssel.
Speichere ihn als einzige Zeile in `gemini-api-key.txt` im App-Datenordner, außerhalb des Git-Projekts.
Die Datei ist Klartext und sollte nur für dein Benutzerkonto lesbar sein.

- macOS: `~/Library/Application Support/PersonalDigitalAgent/gemini-api-key.txt`
- Windows: `%APPDATA%\PersonalDigitalAgent\gemini-api-key.txt`

Auf macOS kannst du den Schlüssel im Terminal verdeckt einfügen und mit Enter speichern:

```zsh
(
  umask 077
  dir="$HOME/Library/Application Support/PersonalDigitalAgent"
  mkdir -p "$dir" || exit
  read -rs "key?Gemini-API-Schlüssel: "
  printf '\n'
  if [[ -n "$key" ]]; then
    printf '%s\n' "$key" > "$dir/gemini-api-key.txt"
    chmod 600 "$dir/gemini-api-key.txt"
  fi
)
```

Alternativ liest das Programm die Umgebungsvariable `GEMINI_API_KEY`. Sie hat Vorrang
vor der Datei. Nach dem Wechsel auf Gemini die Anwendung neu starten. Im Popup kannst du
zwischen Flash-Lite, Flash und 3.8 Flash wechseln. Die Auswahl bleibt gespeichert.
Welche Modelle dein Konto nutzen kann, hängt von den [Kontingenten deines Projekts](https://ai.google.dev/gemini-api/docs/rate-limits) ab.

Nur Befehle verwenden:

```sh
# macOS
PDA_ASSISTANT_BACKEND=commands .venv/bin/python main.py
```

```bat
rem Windows
set PDA_ASSISTANT_BACKEND=commands
.venv\Scripts\python main.py
```

### Design auswählen

Der **Design**-Button oben rechts zeigt zwei Gruppen mit Vorschauen. Standard ist
**Apple · Automatisch**: Die Oberfläche folgt dem hellen oder dunklen Erscheinungsbild des
Betriebssystems. **Apple Hell** und **Apple Dunkel** lassen sich auch dauerhaft auswählen.
Systemschrift, klare Abstufungen von Text und Flächen, ruhige Inhaltskarten und dezente
Materialien für die Bedienebene orientieren sich an Apples Gestaltungsempfehlungen.

Die weiteren Designs greifen vier unterschiedliche Stilrichtungen auf:

- **Neumorphismus:** weiche, plastische Reliefs und eingedrückte Eingabefelder.
- **OLED:** echter schwarzer Hintergrund mit gezielten neongrünen Akzenten.
- **Pixel Art:** lokal eingebundene Pixelschrift, harte Kanten und versetzte Schatten.
- **Maximalismus:** Gelb, Magenta und Cyan, kräftige Konturen und Collage-Elemente.

Die Auswahl wirkt sofort auf Chat, Einstellungen und die eingebauten Ansichten und bleibt
beim Neustarten erhalten. Gespeichert wird ausschließlich die Designkennung lokal im
WebEngine-Profil unter `pda.appearance.v2`; Gesprächsinhalte werden dort nicht gespeichert.
Beim Update auf diese Auswahl wird einmalig Apple · Automatisch als Standard verwendet.
Die Auswahl ist mit Pfeiltasten bedienbar; Escape schließt sie. Eigene HTML-Ansichten behalten
ihre Gestaltung. Die Pixelschrift liegt samt Lizenz im Projekt; es gibt keine externen
Schriftaufrufe zur Laufzeit.

Auch die tatsächliche Fensterfläche hat abgerundete Ecken. Beim Öffnen gleitet sie kurz
vom Symbol aus hinein und blendet ein; beim Schließen läuft die Bewegung in Gegenrichtung.
Erneutes Öffnen kann die Schließanimation unterbrechen. Der Chat bleibt dabei erhalten.
Die Betriebssystemoption „Bewegung reduzieren“ wird berücksichtigt; optional lässt sich die
Animation mit `PDA_REDUCE_MOTION=1` abschalten. Chat und Fenster lassen sich weiterhin separat
vergrößern; die Aufteilung zwischen Überblick und Chat lässt sich ziehen oder per Pfeiltaste ändern.

Das Robotersymbol orientiert sich an der Projektvorlage: unter macOS als automatisch
angepasste monochrome Menüleistenversion, unter Windows als farbiges Symbol in mehreren Größen.

Gestaltungsgrundlagen: [Materialien](https://developer.apple.com/design/human-interface-guidelines/materials),
[Typografie](https://developer.apple.com/design/human-interface-guidelines/typography),
[Dunkelmodus](https://developer.apple.com/design/human-interface-guidelines/dark-mode) und
[Bewegung](https://developer.apple.com/design/human-interface-guidelines/motion).

### Sprache

Rechts neben dem Eingabefeld startet 🎤 die Spracheingabe, ein zweiter Klick sendet die Nachricht,
**Escape** bricht ab. Antworten auf gesprochene Nachrichten werden vorgelesen (Escape stoppt das
Vorlesen). Aufnahme, Spracherkennung und Sprachausgabe laufen lokal; der transkribierte Nachrichtentext
geht bei Verwendung von Gemini zur Beantwortung an Google:

- Spracherkennung: [faster-whisper](https://github.com/SYSTRAN/faster-whisper), Modell `small`
  (≈ 480 MB)
- Sprachausgabe: [Piper](https://github.com/OHF-Voice/piper1-gpl), Stimme `de_DE-pavoque-low`
  (≈ 60 MB); geht Piper nicht, eine installierte macOS-Stimme bzw. die eingebaute Windows-Stimme

Modell und Stimme werden beim ersten Gebrauch im Datenordner unter `speech` geladen,
die erste Aufnahme dauert deshalb länger. Die macOS-Ersatzstimme benötigt keinen Modelldownload.
Beim ersten Klick auf das Mikrofon fragt macOS nach der Aufnahmefreigabe. Wird sie abgelehnt,
kann sie unter Systemeinstellungen → Datenschutz & Sicherheit → Mikrofon geändert werden;
beim Start aus PyCharm kann die Freigabe PyCharm oder Python zugeordnet sein. Andere Größen und Stimmen über
`PDA_WHISPER_MODEL` (`tiny`, `base`, `medium` …), `PDA_PIPER_VOICE` und `PDA_SPEECH_LANGUAGE`
(siehe [config.py](backend/config.py)). `PDA_MAC_VOICE` legt optional eine installierte Mac-Stimme fest.

### MCP-Server einbinden

In [mcp_servers.json](mcp_servers.json) eintragen – dasselbe Format wie bei Claude Desktop, sodass
sich Einträge aus den Anleitungen fertiger Server meist direkt übernehmen lassen:

```json
{
  "mcpServers": {
    "pda":        { "command": "python", "args": ["mcp_servers/pda_server.py"] },
    "filesystem": { "command": "npx", "args": ["-y", "@modelcontextprotocol/server-filesystem", "C:/Users/me/Documents"] }
  }
}
```

Der eigene Server ist [mcp_servers/pda_server.py](mcp_servers/pda_server.py), geschrieben mit dem
offiziellen MCP-SDK. Er bietet `get_current_time`, `calculate`, `send_email`, `list_emails`, `read_email` und
`read_attachment`. Ein neues Tool
ist dort eine Funktion mit `@mcp.tool()`. Mit `mcp dev mcp_servers/pda_server.py` lässt er sich
ohne Assistent im Browser ausprobieren.

**E-Mail:** `mcp_servers/.env.example` nach `mcp_servers/.env` kopieren und SMTP-Zugang sowie
die erlaubten Empfänger (`PDA_MAIL_RECIPIENTS`) eintragen. Bei Gmail braucht ihr ein App-Passwort.
Der Assistent kann nur an diese Adressen schreiben.
Zum **Lesen** (IMAP) reicht das meist schon: Der IMAP-Server wird aus dem SMTP-Server abgeleitet
(`smtp.gmail.com` → `imap.gmail.com`), Login und App-Passwort werden übernommen. Abweichend lässt
sich alles mit `PDA_IMAP_HOST`, `PDA_IMAP_PORT`, `PDA_IMAP_USER`, `PDA_IMAP_PASSWORD` setzen. Der
Zugriff ist nur lesend: Mails bleiben ungelesen und werden weder gelöscht noch verschoben.
**Anhänge** erscheinen im Chat unter der Antwort und lassen sich dort öffnen oder in den
Download-Ordner speichern. Den Text von PDF-, Word-, Excel-, PowerPoint- und Textdateien kann der
Assistent lesen und zusammenfassen (dafür `pypdf` und `openpyxl` aus `requirements.txt`).

Unterstützt werden Server über **stdio** (Unterprozess). `"python"` startet dasselbe Python, mit
dem das Programm läuft; `"disabled": true` schaltet einen Eintrag ab. Nach Änderungen das
Programm neu starten.

### Modellauswahl und optionaler Ollama-Betrieb

Der Chatbefehl `modelle` zeigt die Auswahl, `modell gemini-3.5-flash` wechselt das Modell.
`PDA_GEMINI_MODEL` kann eine weitere Gemini-Modell-ID zur Auswahl hinzufügen und legt die
Vorgabe fest, solange noch kein Modell gespeichert ist.
Bei Gemini gehen Gesprächskontext und benötigte Werkzeugergebnisse an Google.

Für Ollama die App mit `PDA_ASSISTANT_BACKEND=ollama` starten. Sie startet den lokalen
Ollama-Dienst bei Bedarf. Für die Ollama-Cloud ist `ollama signin` erforderlich.
Mit `PDA_OLLAMA_CLOUD_ONLY=0` sind lokale Modelle wählbar und mit zusätzlich
`PDA_OLLAMA_CLOUD=0` werden Cloud-Modelle ausgeblendet.

### Einstellungen (Präferenzen)

**⚙ Einstellungen** oben links im Chat öffnet ein Formular über dem ganzen Popup. Gespeichert wird
in `preferences.json` im Datenordner, gültig ab der nächsten Nachricht.

- macOS: `~/Library/Application Support/PersonalDigitalAgent`
- Windows: `%APPDATA%\PersonalDigitalAgent`
- Eigener Ort: Umgebungsvariable `PDA_APP_DATA_DIR` (auch für MCP-Werkzeuge gültig).

- **Antworten:** Länge, Tiefe, Darstellung (Fließtext, Stichpunkte, strukturiert …), Ton, Anrede
  (du/Sie), Sprache, Emojis, Rückfragen statt Raten und ein Freitext für weitere Wünsche.
- **Werkzeuge:** Für jede Werkzeuggruppe einstellbar, ob der Assistent sie überhaupt nutzt, wie
  ausführlich er Ergebnisse im Chat wiedergibt, ob oben eine Tabelle der Aufrufe erscheint
  (aus, gekürzt, vollständig) und ein Freitext zur Darstellung. **E-Mail** zusätzlich: welche
  Angaben je Mail (Absender, Betreff, Datum, Vorschau, Anhänge …), wie viel Inhalt (nur Angaben,
  Zusammenfassung, Wichtiges, Volltext), Liste oder Tabelle, Höchstzahl, Rückfrage vor dem Senden.
- **Neue Werkzeuge** (z. B. aus einem weiteren MCP-Server) erscheinen automatisch mit den
  Grundeinstellungen. Eigene Zusatzfelder: `ToolGroup` in
  [backend/assistant/settings.py](backend/assistant/settings.py) eintragen.

### Proaktive Meldungen

Der PDA kann sich **von sich aus** melden, ohne dass man etwas gefragt hat. Zum Vorführen gibt es
ein Test-Makro: **⌘+⌥+P** auf macOS bzw. **Strg+Alt+P** unter Windows (auch bei geschlossenem Popup) oder
Rechtsklick aufs Tray-Icon → „Proaktive Meldung testen“. Dann

1. formuliert das Sprachmodell eine kurze Meldung (ohne Modell: fester Text),
2. **öffnet sich das Popup von selbst** – genau wie bei einem Klick aufs Tray-Icon (am Symbol, mit passender Einfahr-Animation; schließt sich beim Klick daneben),
3. steht die Meldung im Chat, markiert mit 🔔, und oben eine Ansicht mit Zeitpunkt und Auslöser,
4. wird sie vorgelesen, wenn die Sprachausgabe verfügbar ist.

Man kann direkt im Chat antworten – das Modell kennt seine Meldung. Einstellungen:
`PDA_PROACTIVE_HOTKEY` (z. B. `Ctrl+Shift+F9`, leer = aus), `PDA_PROACTIVE_SPEAK=0` (nicht vorlesen),
`PDA_PROACTIVE_OPEN_POPUP=0` (statt des Popups nur eine Systembenachrichtigung; Klick öffnet es).
Später lösen echte Anlässe (Briefing um 7 Uhr, Termin, neue Mail) dasselbe aus, siehe
[backend/proactive.py](backend/proactive.py).

## Testen

```
python -m pip install -r requirements-dev.txt
python -m pytest
```

`pytest` misst die Testabdeckung und schlägt fehl, wenn sie unter 80 % liegt.

## Wo arbeite ich?

Für die eigentliche Projektarbeit braucht ihr nur diese Stellen:

| Aufgabe | Ort |
|---|---|
| Integration eines Dienstes (Calendar, Wetter, Gmail …) | [backend/integrations/](backend/integrations/__init__.py) – Anleitung in der `__init__.py` |
| Fähigkeit des Assistenten (morning, travel, organization) | [backend/assistant/skills/](backend/assistant/skills/__init__.py) – Anleitung in der `__init__.py` |
| Darstellung im Anzeigebereich | [frontend/templates/](frontend/templates/) – Vorlage: `default.html.j2` |
| Funktion, die das Frontend aufrufen kann | [backend/api.py](backend/api.py) |
| eigenes Werkzeug (MCP) | [mcp_servers/pda_server.py](mcp_servers/pda_server.py) – Funktion mit `@mcp.tool()` |
| fremder MCP-Server | [mcp_servers.json](mcp_servers.json) |
| Verhalten des Assistenten (Anweisungen, Tool-Schleife) | [backend/assistant/model_assistant.py](backend/assistant/model_assistant.py) |
| Sprache (Erkennung, Vorlesen) | [backend/speech.py](backend/speech.py) |

Alles andere ist **Infrastruktur** und muss für neue Funktionen nicht angefasst werden:
`backend/bridge/`, `backend/desktop/`, `rendering.py`, `presenter.py`, `events.py`, `views.py`.

## So hängt es zusammen

```
FRONTEND (frontend/, läuft im Browser)      BACKEND (backend/, läuft in Python)

popup.js ── await chat("…") ─────────────►  api.py ──► Assistent (assistant/)
                                                          │  Fähigkeiten (skills/) mit
                                                          │  Integrationen (integrations/)
                                                          ▼
iframe   ◄── fertiges HTML ◄── Template (frontend/templates/) + Daten des Assistenten
Chat     ◄── Nachricht ohne Eingabe ◄──── presenter.push(…)   z. B. Morning-Briefing
```

## Zwei Beispiele

**Python-Funktion im Frontend aufrufen**: Jede Funktion in `backend/api.py` ist in JavaScript
unter demselben Namen verfügbar.

```python
# backend/api.py
def add(a, b):
    return a + b
```

```js
// frontend/popup.js
const sum = await add(2, 3);
```

**Assistent zeigt Daten im Anzeigebereich an**: Er liefert nur Daten, das Template macht daraus
die Ansicht.

```python
return AssistantReply(
    "Hier ist das Wetter.",
    TemplateView("default", {"title": "Wetter", "text": "18 °C, sonnig"}),
)
```

## Mehr Details

[ARCHITEKTUR.md](ARCHITEKTUR.md) erklärt den Aufbau ausführlich. Dort stehen der
Programmablauf, die Brücke zwischen JavaScript und Python, der Weg einer Chat-Nachricht,
Templates und Sicherheit, die Schnittstellen für Sprachmodelle und Integrationen (inkl. Tool-Calling
und MCP), die Tests und bekannte Fallstricke.
