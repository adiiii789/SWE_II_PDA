"""Integrationen externer Dienste - jede als ToolProvider (backend/assistant/tools.py).

Noch leer. Geplante Integrationen und welche Fähigkeit (backend/assistant/skills/) sie nutzt:

  Integration          Fähigkeit
  -------------------  ---------------------------------------------
  Google Calendar      morning, travel, organization  (lesen, erstellen)
  OpenWeather          morning
  Aktien-API           morning  (Recap des Vortages)
  Musik                morning  (Songvorschlag, Abspielen)
  Google Routes        travel   (Fahrzeit Auto / ÖPNV)
  Tankerkönig          travel   (Spritpreis-Prognose)
  Gmail                organization  (E-Mails verfassen und senden)
  Google Keep          organization  (Notizen, To-do-Listen)

Konvention:
  - Ein Modul pro Integration, z. B. integrations/weather.py mit einer Klasse,
    die ToolProvider erfüllt (list_tools / call_tool).
  - Zugangsdaten und API-Keys nicht im Code, sondern aus der Konfiguration bzw.
    Umgebungsvariablen lesen.
  - Alternativ läuft eine Integration als MCP-Server; dann stellt ein MCP-Client
    (ebenfalls ein ToolProvider) ihre Werkzeuge bereit.
  - Eine Fähigkeit bündelt ihre Integrationen als CompositeToolProvider.
  - Tests ohne echte Netzwerkaufrufe (HTTP-Client mocken).
"""
