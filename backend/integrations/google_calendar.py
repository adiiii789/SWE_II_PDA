"""Google Calendar: Termine lesen (nur lesend).

Einrichtung: in der Google Cloud Console die "Google Calendar API" aktivieren, einen
OAuth-Client vom Typ "Desktop-App" anlegen und das JSON als
config.GOOGLE_DIR / "credentials.json" speichern. Beim ersten Zugriff öffnet sich der
Browser zur Anmeldung; das Token liegt danach in token.json daneben.
"""
from __future__ import annotations

import datetime
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from backend.integrations.http import Http, IntegrationError

EVENTS_URL = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]


@dataclass(frozen=True)
class CalendarEvent:
    id: str
    title: str
    start: datetime.datetime      # mit Zeitzone
    end: datetime.datetime
    location: str = ""
    updated: str = ""             # ändert sich, wenn der Termin bearbeitet wird


class GoogleCalendar:
    def __init__(self, http: Http, token: Callable[[bool], str]):
        """token(interactive): liefert ein gültiges OAuth-Zugriffstoken (oauth_token)."""
        self.http = http
        self.token = token

    def events(self, start: datetime.datetime, end: datetime.datetime, limit: int = 50,
               interactive: bool = True) -> list[CalendarEvent]:
        """Termine mit Uhrzeit zwischen start und end, nach Beginn sortiert. Ganztägige fehlen.
        interactive=False: nie zur Anmeldung den Browser öffnen (Aufruf im Hintergrund)."""
        data = self.http.get_json(EVENTS_URL, {
            "timeMin": start.isoformat(), "timeMax": end.isoformat(), "singleEvents": "true",
            "orderBy": "startTime", "maxResults": limit,
        }, {"Authorization": f"Bearer {self.token(interactive)}"})
        return [_event(item) for item in data.get("items", [])
                if "dateTime" in item.get("start", {}) and item.get("status") != "cancelled"]


def _event(item: dict) -> CalendarEvent:
    return CalendarEvent(item.get("id", ""), item.get("summary", "(ohne Titel)"),
                         datetime.datetime.fromisoformat(item["start"]["dateTime"]),
                         datetime.datetime.fromisoformat(item["end"]["dateTime"]),
                         item.get("location", ""), item.get("updated", ""))


def oauth_token(google_dir: Path) -> Callable[[bool], str]:
    """Token-Lieferant für GoogleCalendar. Aufruf mit interactive=False (z. B. aus der
    Erinnerung im Hintergrund) öffnet nie den Browser, sondern meldet einen Fehler."""
    lock = threading.Lock()
    state: dict = {}

    def token(interactive: bool = True) -> str:
        # Erst hier importieren: google-auth wird nur gebraucht, wenn der Kalender genutzt wird.
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials

        secrets, token_file = google_dir / "credentials.json", google_dir / "token.json"
        with lock:
            credentials = state.get("credentials")
            if credentials is not None and credentials.valid:
                return credentials.token
            if credentials is None and token_file.is_file():
                credentials = Credentials.from_authorized_user_file(str(token_file), SCOPES)
            if credentials is not None and not credentials.valid and credentials.refresh_token:
                try:
                    credentials.refresh(Request())
                except Exception:   # noqa: BLE001  # z. B. Zugriff widerrufen - neu anmelden
                    credentials = None
            if credentials is None or not credentials.valid:
                if not interactive:
                    raise IntegrationError("Google Calendar: noch nicht angemeldet")
                if not secrets.is_file():
                    raise IntegrationError(f"Google Calendar ist nicht eingerichtet: {secrets} fehlt (siehe README)")
                from google_auth_oauthlib.flow import InstalledAppFlow
                credentials = InstalledAppFlow.from_client_secrets_file(str(secrets), SCOPES).run_local_server(port=0)
            token_file.parent.mkdir(parents=True, exist_ok=True)
            token_file.write_text(credentials.to_json(), encoding="utf-8")
            state["credentials"] = credentials
            return credentials.token

    return token
