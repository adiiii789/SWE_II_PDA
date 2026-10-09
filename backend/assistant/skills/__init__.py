"""Fähigkeiten (Skills) des Assistenten - ein Assistent, drei Aufgabenbereiche.

Es gibt genau einen durchgehenden Assistenten: ein Gesprächsverlauf, ein Satz
Präferenzen, Rückfragen über alle Bereiche hinweg. Eine Fähigkeit bündelt, was
er für einen Aufgabenbereich braucht. Noch leer. Geplant:

  Fähigkeit           Wofür                                  Integrationen (backend/integrations/)
  ------------------  -------------------------------------  -------------------------------------
  morning             kurzes Briefing über den Tag           Calendar, OpenWeather, Aktien-API, Musik
  travel              wie komme ich zum nächsten Termin?     Calendar, Google Routes, Tankerkönig
  organization        Nachrichten verfassen, Tag planen      Calendar, Gmail, Google Keep
                      (im Projektplan: "Assistant²")

Konvention:
  - Ein Modul pro Fähigkeit, z. B. skills/morning.py. Es stellt bereit:
      * die Integrationen der Fähigkeit (ToolProvider, gebündelt per
        CompositeToolProvider aus backend/assistant/tools.py),
      * kurze Anweisungen für das Sprachmodell (wann und wie die Werkzeuge
        einzusetzen sind, Antwortstil),
      * optional einen autonomen Auslöser, z. B. Briefing um 7 Uhr; die Antwort
        geht dann mit backend.presenter.push(reply) in den Chat.
  - Der Assistent (ein Assistant mit LanguageModel, backend/assistant/llm.py) sammelt
    die Werkzeuge und Anweisungen aller Fähigkeiten. Das Modell wählt per
    Tool-Calling selbst, welche Werkzeuge es braucht. Sind es für ein kleines
    lokales Modell zu viele, gibt der Assistent je Anfrage nur die Werkzeuge der
    passenden Fähigkeit mit - die Struktur bleibt dieselbe.
  - Kontextwissen kommt aus dem PreferenceStore (backend/preferences.py).
"""
