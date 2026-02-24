from __future__ import annotations

import logging
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger("punch.tools.calendar")

SCOPES = ["https://www.googleapis.com/auth/calendar"]


def _get_service(credentials_path: str = "data/calendar_credentials.json",
                 token_path: str = "data/calendar_token.json"):
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    creds = None
    if Path(token_path).exists():
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(credentials_path, SCOPES)
            creds = flow.run_local_server(port=0)
        Path(token_path).write_text(creds.to_json())
    return build("calendar", "v3", credentials=creds)


async def list_events(days_ahead: int = 7, max_results: int = 20,
                      credentials_path: str = "data/calendar_credentials.json") -> list[dict]:
    import asyncio
    def _fetch():
        service = _get_service(credentials_path)
        now = datetime.utcnow().isoformat() + "Z"
        end = (datetime.utcnow() + timedelta(days=days_ahead)).isoformat() + "Z"
        results = service.events().list(
            calendarId="primary", timeMin=now, timeMax=end,
            maxResults=max_results, singleEvents=True, orderBy="startTime",
        ).execute()
        events = results.get("items", [])
        return [{
            "id": e["id"],
            "summary": e.get("summary", "No title"),
            "start": e.get("start", {}).get("dateTime", e.get("start", {}).get("date", "")),
            "end": e.get("end", {}).get("dateTime", e.get("end", {}).get("date", "")),
            "location": e.get("location", ""),
            "description": e.get("description", ""),
        } for e in events]
    return await asyncio.get_event_loop().run_in_executor(None, _fetch)


async def create_event(summary: str, start: str, end: str, description: str = "",
                       location: str = "",
                       credentials_path: str = "data/calendar_credentials.json") -> dict:
    import asyncio
    def _create():
        service = _get_service(credentials_path)
        event = {
            "summary": summary,
            "location": location,
            "description": description,
            "start": {"dateTime": start, "timeZone": "UTC"},
            "end": {"dateTime": end, "timeZone": "UTC"},
        }
        result = service.events().insert(calendarId="primary", body=event).execute()
        return {"id": result["id"], "link": result.get("htmlLink", "")}
    return await asyncio.get_event_loop().run_in_executor(None, _create)
