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
