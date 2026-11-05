# Personal Digital Agent (PDA)

Desktop-Anwendung für macOS und Windows: Ein Klick auf das Symbol öffnet ein Popup mit einem
**Anzeigebereich** (oben) und einem **Chat mit einem Assistenten** (unten). Rechtsklick öffnet
das Kontextmenü mit „Beenden“.

Das Projekt ist die **Grundlage** für einen persönlichen Assistenten mit lokalem
Sprachmodell (Ollama). Er hat drei **Fähigkeiten**: Morning-Briefing, Weg zum nächsten Termin
(Travel) und Organisation von Nachrichten und Terminen (im Projektplan „Assistant²“). Der
Assistent läuft mit einem lokalen Modell aus Ollama und nutzt Werkzeuge von **MCP-Servern**
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

Standardmäßig werden ausschließlich Cloud-Modelle angeboten. [Ollama](https://ollama.com)
installieren und einmal mit `ollama signin` anmelden. Das Programm startet den lokalen
Ollama-Zugang bei Bedarf automatisch; ein bereits laufender Dienst wird weiterverwendet.
Es wird kein lokales Modell heruntergeladen. Die Antworten selbst entstehen in der Cloud.
Beim ersten Start wird ein verfügbares Cloud-Modell mit Werkzeugunterstützung ausgewählt;
anschließend bleibt die eigene Modellauswahl gespeichert. Der Anbieter benötigt dafür ein
entsprechendes Cloud-Kontingent bzw. Guthaben.

Lokale Modelle können später mit `PDA_OLLAMA_CLOUD_ONLY=0` wieder zugelassen werden.
Ohne nutzbares Cloud-Kontingent funktionieren weiterhin die festen Befehle.

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

### Sprache

Rechts neben dem Eingabefeld startet 🎤 die Spracheingabe, ein zweiter Klick sendet die Nachricht,
**Escape** bricht ab. Antworten auf gesprochene Nachrichten werden vorgelesen (Escape stoppt das
Vorlesen). Aufnahme, Spracherkennung und Sprachausgabe laufen lokal; der transkribierte Nachrichtentext
geht bei Verwendung eines Cloud-Modells zur Beantwortung an Ollama:

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

### Sprachmodell: lokal oder Ollama-Cloud

Der Assistent verwendet standardmäßig **Cloud-Modelle** über den lokalen Ollama-Zugang.
Es werden keine lokalen Modellgewichte geladen:

1. Bei ollama.com anmelden und einmal im Terminal `ollama signin` ausführen.
2. Im Chat `modelle` eingeben. Die Liste zeigt die verfügbaren Cloud-Modelle.
3. Mit `modell gemma4:31b-cloud` wechseln. Die Wahl bleibt gespeichert.

Welche Modelle genutzt werden können, hängt vom aktuellen Konto und Kontingent ab.
HTTP 402 bedeutet, dass Ollama Guthaben oder einen passenden Tarif verlangt; HTTP 429 bedeutet,
dass ein Nutzungslimit erreicht wurde.
Für lokale Modelle später `PDA_OLLAMA_CLOUD_ONLY=0` setzen; mit zusätzlich `PDA_OLLAMA_CLOUD=0`
werden die Cloud-Modelle ausgeblendet.

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
| Verhalten des Assistenten (Anweisungen, Tool-Schleife) | [backend/assistant/ollama_assistant.py](backend/assistant/ollama_assistant.py) |
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
Templates und Sicherheit, die Schnittstellen für Ollama und Integrationen (inkl. Tool-Calling
und MCP), die Tests und bekannte Fallstricke.
