"""Integrationen externer Dienste - als ToolProvider (backend/assistant/tools.py) oder als
Client, den eine Fähigkeit in ihre Werkzeuge einbaut (z. B. skills/travel/tools.py).

Integrationen und welche Fähigkeit (backend/assistant/skills/) sie nutzt:

  Integration          Fähigkeit
  -------------------  ---------------------------------------------
  Google Calendar      morning, travel, organization  (google_calendar.py: lesen)
  Open-Meteo           travel, morning  (weather.py: stündliche Vorhersage, ohne Key)
  Aktien-API           morning  (Recap des Vortages)
  Musik                morning  (Songvorschlag, Abspielen)
  openrouteservice     travel   (openrouteservice.py: Adressen, Routen Auto/Rad/zu Fuß)
  VVS (EFA)             travel   (vvs.py: Verbindungen im VVS-Gebiet mit Echtzeit und Preis, ohne Key)
  Transitous           travel   (transitous.py: Bahn/ÖPNV-Verbindungen mit Bus und Tram, ohne Key)
                                (transit.py: gemeinsames Format beider)
  DB OpenBoards/Timetables travel (db_timetables.py: Ersatz - Züge mit bis zu drei Umstiegen, mit Echtzeit)
  DB StaDa             travel   (db_stations.py: Bahnhof zur Adresse, Liste aller Bahnhöfe mit Koordinaten)
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
