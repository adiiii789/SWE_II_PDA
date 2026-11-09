# Personal Digital Agent (PDA)

Tray-Anwendung für Windows: Ein Klick auf das Tray-Icon öffnet ein Popup mit einem
**Anzeigebereich** (oben) und einem **Chat mit einem Assistenten** (unten). Rechtsklick öffnet
das Kontextmenü mit „Beenden“.

Das Projekt ist die **Grundlage** für einen persönlichen KI-Assistenten mit lokalem
Sprachmodell (Ollama). Er hat drei **Fähigkeiten**: Morning-Briefing, Weg zum nächsten Termin
(Travel) und Organisation von Nachrichten und Terminen (im Projektplan „Assistant²“). Der
Assistent läuft mit einem lokalen Modell aus Ollama und nutzt Werkzeuge von **MCP-Servern**
(eingetragen in [mcp_servers.json](mcp_servers.json)). Die Fähigkeiten selbst sind noch nicht
umgesetzt. Feste Befehle wie `hilfe`, `uhrzeit`, `system`, `start` und `neu` funktionieren
weiterhin ohne Modell.

## Starten

1. [Ollama](https://ollama.com) installieren und starten, ein Modell mit Tool-Calling laden:
   ```
   ollama pull qwen3:8b        # oder llama3.1:8b, qwen2.5:7b; klein: llama3.2:3b
   ```
2. Programm starten:
   ```
   pip install -r requirements.txt
   python main.py
   ```
3. Im Popup links neben dem Eingabefeld das Modell wählen (alle in Ollama installierten Modelle).

Windows, Python 3.12. Ohne Ollama: `set PDA_ASSISTANT_BACKEND=commands` startet nur mit den
festen Befehlen.

### Sprache

Rechts neben dem Eingabefeld startet 🎤 die Spracheingabe, ein zweiter Klick sendet die Nachricht,
**Escape** bricht ab. Antworten auf gesprochene Nachrichten werden vorgelesen (Escape stoppt das
Vorlesen). Alles läuft lokal:

- Spracherkennung: [faster-whisper](https://github.com/SYSTRAN/faster-whisper), Modell `small`
  (≈ 480 MB)
- Sprachausgabe: [Piper](https://github.com/OHF-Voice/piper1-gpl), Stimme `de_DE-pavoque-low`
  (≈ 60 MB); geht Piper nicht, die eingebaute Windows-Stimme

Modell und Stimme werden beim ersten Gebrauch nach `%APPDATA%\PersonalDigitalAgent\speech`
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
offiziellen MCP-SDK. Er bietet `get_current_time`, `calculate`, `send_email`, `list_emails`, `read_email`,
`read_attachment`, `list_calendar_events`, `create_calendar_event`, `list_tasks` und `create_task`. Ein neues Tool
ist dort eine Funktion mit `@mcp.tool()`. Mit `mcp dev mcp_servers/pda_server.py` lässt er sich
ohne Assistent im Browser ausprobieren.

**E-Mail:** `mcp_servers/.env.example` nach `mcp_servers/.env` kopieren und SMTP-Zugang sowie
die erlaubten Empfänger (`PDA_MAIL_RECIPIENTS`) eintragen. Bei Gmail braucht ihr ein App-Passwort.
Der Assistent kann nur an diese Adressen schreiben. Steht ein Name davor
(`Mama <mama@example.com>, Anna Müller <anna@example.com>`), reicht beim Senden der Name („schick
Anna eine Mail …“).
Zum **Lesen** (IMAP) reicht das meist schon: Der IMAP-Server wird aus dem SMTP-Server abgeleitet
(`smtp.gmail.com` → `imap.gmail.com`), Login und App-Passwort werden übernommen. Abweichend lässt
sich alles mit `PDA_IMAP_HOST`, `PDA_IMAP_PORT`, `PDA_IMAP_USER`, `PDA_IMAP_PASSWORD` setzen. Der
Zugriff ist nur lesend: Mails bleiben ungelesen und werden weder gelöscht noch verschoben.
**Anhänge** erscheinen im Chat unter der Antwort und lassen sich dort öffnen oder in den
Download-Ordner speichern. Den Text von PDF-, Word-, Excel-, PowerPoint- und Textdateien kann der
Assistent lesen und zusammenfassen (dafür `pypdf` und `openpyxl` aus `requirements.txt`).

**Google Kalender:** Der Assistent liest Termine aller eingeblendeten Kalender und legt auf Wunsch
neue im Hauptkalender an, ohne Gäste einzuladen. Einmalig einzurichten:

1. In der [Google Cloud Console](https://console.cloud.google.com/) ein Projekt anlegen und die
   **Google Calendar API** und die **Google Tasks API** aktivieren.
2. Unter *Google Auth Platform* den Zustimmungsbildschirm einrichten (App-Name, Kontakt-Mails) und
   unter *Datenzugriff* die Bereiche `calendar.events`, `calendar.readonly` und `tasks` hinzufügen.
3. Unter *Zielgruppe* **Extern** und **Testen** einstellen und bei *Testnutzer* die eigene
   Gmail-Adresse eintragen. Ohne diesen Eintrag lehnt Google die Anmeldung ab (`403 access_denied`).
4. Unter *Clients* einen OAuth-Client vom Typ **Desktop-App** anlegen und die JSON-Datei herunterladen.
5. Im Projektordner `python mcp_servers/google_calendar.py "<Pfad zur JSON-Datei>"` ausführen.
6. Im Browser mit der Gmail-Adresse anmelden und alle Berechtigungen erlauben. Die Warnung
   vor einer nicht überprüften App überspringt man mit *Erweitert* → *Weiter zu …*. Im Terminal steht
   danach `Google Kalender und Google Tasks sind eingerichtet`, die heruntergeladene JSON-Datei kann weg.
7. Den PDA komplett beenden und neu starten. Test: „Was steht diese Woche an?“

**Alle 7 Tage neu anmelden:** Im Status „Testen“ läuft die Anmeldung nach 7 Tagen ab, der Assistent
meldet das im Chat. Dann reicht `python mcp_servers/google_calendar.py` (ohne Pfad) und die Anmeldung
im Browser. Dauerhaft geht es nur, wenn die App veröffentlicht ist: Dafür verlangt Google unter
*Branding* eine Startseiten-URL und eine URL zur Datenschutzerklärung.

Zugangsdaten und Anmeldung liegen in `%APPDATA%/PersonalDigitalAgent/google/`, nicht im Repo.
Beim Erstellen fragt der Assistent standardmäßig nach. Das lässt sich im Popup unter ⚙ Einstellungen →
Werkzeuge → Google Kalender abschalten.

**Google Tasks:** Der Assistent liest die offenen Aufgaben aller Listen und legt auf Wunsch neue in
der Standardliste an. Tasks nutzt dieselbe Anmeldung wie der Kalender, die Einrichtung oben deckt beides
ab. Wer den Kalender schon vor Tasks eingerichtet hat, aktiviert nur noch die **Google Tasks API**,
fügt unter *Datenzugriff* den Bereich `tasks` hinzu und meldet sich einmal mit
`python mcp_servers/google_calendar.py` neu an. Die Rückfrage vor dem Erstellen lässt sich unter
⚙ Einstellungen → Werkzeuge → Google Tasks abschalten.

Unterstützt werden Server über **stdio** (Unterprozess). `"python"` startet dasselbe Python, mit
dem das Programm läuft; `"disabled": true` schaltet einen Eintrag ab. Nach Änderungen das
Programm neu starten.

### Sprachmodell: lokal oder Ollama-Cloud

Der Assistent braucht ein laufendes [Ollama](https://ollama.com). Entweder ein Modell lokal
herunterladen (`ollama pull qwen3.5:9b`) oder ein **Cloud-Modell** nutzen. Das läuft auf
ollama.com, es wird nichts heruntergeladen:

1. Kostenloses Konto auf ollama.com anlegen und einmal im Terminal `ollama signin` ausführen.
2. Im Chat `modelle` eingeben. Die Liste zeigt lokale und Cloud-Modelle.
3. Mit `modell gemma4:31b-cloud` wechseln. Die Wahl bleibt gespeichert.

Im Free-Plan sind nur einige Cloud-Modelle enthalten, und es gibt ein Nutzungskontingent. Bei
einem kostenpflichtigen Modell nennt die Fehlermeldung ein kostenloses Modell als Alternative.
`PDA_OLLAMA_CLOUD=0` blendet die Cloud-Modelle aus.

### Einstellungen (Präferenzen)

**⚙ Einstellungen** oben links im Chat öffnet ein Formular über dem ganzen Popup. Gespeichert wird
in `%APPDATA%\PersonalDigitalAgent\preferences.json`, gültig ab der nächsten Nachricht.

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
ein Test-Makro: **Strg+Alt+P** (funktioniert überall in Windows, auch bei geschlossenem Popup) oder
Rechtsklick aufs Tray-Icon → „Proaktive Meldung testen“. Dann

1. formuliert das Sprachmodell eine kurze Meldung (ohne Modell: fester Text),
2. **öffnet sich das Popup von selbst** – genau wie bei einem Klick aufs Tray-Icon (Ecke an der
   Mitte des Icons, gleiche Einfahr-Animation, schließt sich beim Klick daneben),
3. steht die Meldung im Chat, markiert mit 🔔, und oben eine Ansicht mit Zeitpunkt und Auslöser,
4. wird sie vorgelesen, wenn die Sprachausgabe verfügbar ist.

Man kann direkt im Chat antworten – das Modell kennt seine Meldung. Einstellungen:
`PDA_PROACTIVE_HOTKEY` (z. B. `Ctrl+Shift+F9`, leer = aus), `PDA_PROACTIVE_SPEAK=0` (nicht vorlesen),
`PDA_PROACTIVE_OPEN_POPUP=0` (statt des Popups nur eine Windows-Benachrichtigung; Klick öffnet es).
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
| Verhalten des KI-Assistenten (Anweisungen, Tool-Schleife) | [backend/assistant/ollama_assistant.py](backend/assistant/ollama_assistant.py) |
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
