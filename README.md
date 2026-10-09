# Personal Digital Agent (PDA)

Tray-Anwendung für Windows: Ein Klick auf das Tray-Icon öffnet ein Popup mit einem
**Anzeigebereich** (oben) und einem **Chat mit einem Assistenten** (unten). Rechtsklick öffnet
das Kontextmenü mit „Beenden“.

Das Projekt ist die **Grundlage** für einen persönlichen KI-Assistenten mit lokalem
Sprachmodell (Ollama). Er hat drei **Fähigkeiten**: Morning-Briefing, Weg zum nächsten Termin
(Travel) und Organisation von Nachrichten und Terminen (im Projektplan „Assistant²“). Das Gerüst
steht. Fähigkeiten und Integrationen sind noch nicht umgesetzt. Bis dahin antwortet ein
Platzhalter-Assistent auf die Befehle `hilfe`, `uhrzeit`, `system` und `start`.

## Starten

```
pip install -r requirements.txt
python main.py
```

Windows, Python 3.12.

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
| Ollama, Präferenzen, Sprache | Schnittstellen in [llm.py](backend/assistant/llm.py), [preferences.py](backend/preferences.py), [speech.py](backend/speech.py) implementieren |

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
