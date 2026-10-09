"""Backend des Personal Digital Agent (PDA) - alles, was in Python läuft.

  api.py           Schnittstelle zum Frontend: jede Funktion hier ist im JavaScript aufrufbar
  events.py        Ereignisse vom Backend ans Frontend (Push, z. B. für autonome Abläufe)
  presenter.py     Antwort des Assistenten → {"text", "html"} fürs Frontend
  views.py         Ansicht-Anfragen: Template + Daten oder eigenes HTML
  rendering.py     macht aus einer Ansicht-Anfrage HTML (Jinja2)
  preferences.py   Schnittstelle: Kontextwissen und persönliche Präferenzen
  speech.py        Schnittstelle: Spracheingabe und -ausgabe
  config.py        Einstellungen
  assistant/       Fachlogik: der Assistent, seine Fähigkeiten, Ollama- und Tool-Schnittstellen
  integrations/    externe Dienste (Calendar, Wetter, Gmail …) als ToolProvider
  bridge/          Technik, die Frontend (JavaScript) und Backend (Python) verbindet
  desktop/         Qt-Hülle: Tray-Icon und Popup-Fenster, in dem das Frontend angezeigt wird

Das Frontend (Ordner frontend/) kennt vom Backend nur die Funktionen aus api.py
und die Ereignisse aus events.py.
"""
