# EVE

Enhanced Virtual Entity

EVE läuft unter macOS in der Menüleiste und unter Windows im Infobereich der Taskleiste.
Ein Linksklick auf das Symbol öffnet das Popup mit Anzeigebereich und Chat. Ein weiterer
Linksklick blendet es aus. Per Rechtsklick erreichst du das Kontextmenü mit „Beenden“.

Der Assistent nutzt Google Gemini oder lokal installierte Ollama-Modelle und die Werkzeuge aus
[mcp_servers.json](mcp_servers.json).
Feste Befehle wie `hilfe`, `uhrzeit`, `system`, `start` und `neu` funktionieren auch ohne API-Schlüssel.
Das Projekt bietet die Grundlage für Morning-Briefing, den Weg zum nächsten Termin (Travel)
und die Organisation von Nachrichten und Terminen (Assistant²).

## Starten

Verwende Python 3.12 oder neuer und führe die Befehle im Projektordner aus.

### macOS

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
./Start.command
```

Das Fenster erscheint unterhalb des Menüleistensymbols. Beim ersten Start der Spracheingabe
fragt macOS nach Mikrofonzugriff.

### Windows

```bat
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
Start.bat
```

Das Fenster erscheint am Symbol im Infobereich, gegebenenfalls unter dem Überlaufpfeil.

### Gemini einrichten

Erstelle in [Google AI Studio](https://aistudio.google.com/api-keys) einen API-Schlüssel. Setze
`GEMINI_API_KEY` in der Startumgebung oder speichere den Schlüssel in `gemini-api-key.txt`
im App-Datenordner. Die Datei enthält nur den Schlüssel und liegt außerhalb des Projekts.

- macOS: `~/Library/Application Support/PersonalDigitalAgent`
- Windows: `%APPDATA%\PersonalDigitalAgent`

`PDA_APP_DATA_DIR` kann einen anderen App-Datenordner angeben. Standardmäßig verwendet EVE
`gemini-3.5-flash-lite`. Das Modell lässt sich im Popup oder mit `modell <name>` wechseln.
`modelle` zeigt die Auswahl. Mit `PDA_GEMINI_MODEL` kannst du einen weiteren Modellnamen
als Gemini-Standard vorgeben. Gemini verarbeitet den Chatverlauf und verwendete Werkzeugergebnisse
in der Google-Cloud.

### Lokales Ollama-Modell wählen

Starte [Ollama](https://ollama.com/) auf demselben Rechner. Ist noch kein Modell installiert,
lade in Ollama ein Modell für deinen Rechner. Öffne EVE und wähle es unter **Lokal (Ollama)** im
Modellmenü neben der Eingabe. `modelle` aktualisiert die Liste, `modell ollama/<name>` wechselt im Chat.
Die Auswahl bleibt gespeichert. Lokale Antworten brauchen keinen Gemini-Schlüssel. Der lokale
Chatverlauf wird beim Wechsel zu Gemini nicht mitgesendet. Einzelne MCP-Werkzeuge können weiterhin
Netzdienste nutzen.

In der Standardkonfiguration sind beide Anbieter auswählbar. `PDA_ASSISTANT_BACKEND=ollama` oder
`PDA_ASSISTANT_BACKEND=gemini` beschränkt die Auswahl auf einen Anbieter.
`PDA_ASSISTANT_BACKEND=commands` startet mit festen Befehlen.

### Sprache

Rechts neben dem Eingabefeld startet 🎤 die Spracheingabe, ein zweiter Klick sendet die Nachricht,
**Escape** bricht ab. Antworten auf gesprochene Nachrichten werden vorgelesen (Escape stoppt das
Vorlesen). Alles läuft lokal:

- Spracherkennung: [faster-whisper](https://github.com/SYSTRAN/faster-whisper), Modell `small`
  (≈ 480 MB)
- Sprachausgabe: [Piper](https://github.com/OHF-Voice/piper1-gpl), Stimme `de_DE-pavoque-low`
  (≈ 60 MB); geht Piper nicht, eine installierte Stimme von macOS oder Windows

Modell und Stimme werden beim ersten Gebrauch in den Unterordner `speech` des App-Datenordners
geladen, die erste Aufnahme dauert deshalb länger. Andere Größen und Stimmen über
`PDA_WHISPER_MODEL` (`tiny`, `base`, `medium` …), `PDA_PIPER_VOICE` und `PDA_SPEECH_LANGUAGE`
(siehe [config.py](backend/config.py)).

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

### Einstellungen (Präferenzen)

**⚙ Einstellungen** oben links im Chat öffnet ein Formular über dem ganzen Popup. Gespeichert wird
in `preferences.json` im App-Datenordner, gültig ab der nächsten Nachricht.

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

EVE kann sich **von sich aus** melden, ohne dass man etwas gefragt hat. Zum Vorführen gibt es
ein Test-Makro: **Cmd+Alt+P** unter macOS bzw. **Strg+Alt+P** unter Windows (auch bei geschlossenem Popup) oder
Rechtsklick aufs Tray-Icon → „Proaktive Meldung testen“. Dann

1. formuliert das Sprachmodell eine kurze Meldung (ohne Modell: fester Text),
2. **öffnet sich das Popup von selbst** – genau wie bei einem Klick aufs Tray-Icon (Ecke an der
   Mitte des Icons, gleiche Einfahr-Animation, schließt sich beim Klick daneben),
3. steht die Meldung im Chat, markiert mit 🔔, und oben eine Ansicht mit Zeitpunkt und Auslöser,
4. wird sie vorgelesen, wenn die Sprachausgabe verfügbar ist.

Man kann direkt im Chat antworten – das Modell kennt seine Meldung. Einstellungen:
`PDA_PROACTIVE_HOTKEY` (z. B. `Ctrl+Shift+F9`, leer = aus), `PDA_PROACTIVE_SPEAK=0` (nicht vorlesen),
`PDA_PROACTIVE_OPEN_POPUP=0` (statt des Popups nur eine Systembenachrichtigung; Klick öffnet es).
Später lösen echte Anlässe (Briefing um 7 Uhr, Termin, neue Mail) dasselbe aus, siehe
[backend/proactive.py](backend/proactive.py).

## Testen

```
pip install -r requirements-dev.txt
pytest
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
| Verhalten des KI-Assistenten (Anweisungen, Tool-Schleife) | [backend/assistant/gemini_assistant.py](backend/assistant/gemini_assistant.py) |
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
Templates und Sicherheit, die Schnittstellen für Gemini und Integrationen (inkl. Tool-Calling
und MCP), die Tests und bekannte Fallstricke.
