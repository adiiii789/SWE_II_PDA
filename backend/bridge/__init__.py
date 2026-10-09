"""Verbindung Frontend (JavaScript) ↔ Backend (Python) über QWebChannel.

  function_registry.py  findet die öffentlichen Funktionen aus backend/api.py
  web_bridge.py         Python-Seite: nimmt Aufrufe entgegen, antwortet mit JSON
  bridge_client.js      JavaScript-Seite: wird automatisch in jede Seite eingefügt
                        und stellt die Python-Funktionen als JS-Funktionen bereit

Für die Arbeit an Frontend oder Backend muss hier nichts angepasst werden.
"""
