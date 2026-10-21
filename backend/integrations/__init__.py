"""Integrationen externer Dienste - als ToolProvider (backend/assistant/tools.py) oder als
Client, den eine Fähigkeit in ihre Werkzeuge einbaut (z. B. skills/travel/tools.py).

Integrationen und welche Fähigkeit (backend/assistant/skills/) sie nutzt:

  Integration          Fähigkeit
  -------------------  ---------------------------------------------
  Google Calendar      morning, travel, organization  (google_calendar.py: lesen)
  OpenWeather          morning
  Aktien-API           morning  (Recap des Vortages)
  Musik                morning  (Songvorschlag, Abspielen)
  openrouteservice     travel   (openrouteservice.py: Adressen, Routen Auto/Rad/zu Fuß)
  DB Timetables        travel   (db_timetables.py: Direktverbindungen aus dem Fahrplan)
  Tankerkönig          travel   (tankerkoenig.py: aktuelle Spritpreise)
  Gmail                organization  (E-Mails verfassen, senden und lesen - als MCP-Server umgesetzt)
  Google Keep          organization  (Notizen, To-do-Listen)

Konvention:
  - Ein Modul pro Integration, z. B. integrations/weather.py mit einer Klasse,
    die ToolProvider erfüllt (list_tools / call_tool).
  - Zugangsdaten und API-Keys nicht im Code, sondern aus der Konfiguration bzw.
    Umgebungsvariablen lesen.
  - Alternativ läuft eine Integration als MCP-Server; dann stellt MCPToolProvider
    (mcp_client.py, ebenfalls ein ToolProvider) ihre Werkzeuge bereit. Dafür
    genügt ein Eintrag in mcp_servers.json im Projektordner.
  - Eine Fähigkeit bündelt ihre Integrationen als CompositeToolProvider.
  - HTTP über JsonHttp (http.py); Tests ohne echte Netzwerkaufrufe (FakeHttp aus tests/integrations/fake_http.py statt JsonHttp).
"""
