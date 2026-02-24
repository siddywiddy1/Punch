from __future__ import annotations

import base64
import logging
from email.mime.text import MIMEText
from pathlib import Path

logger = logging.getLogger("punch.tools.gmail")

SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.send",
]


def _get_service(credentials_path: str = "data/gmail_credentials.json",
                 token_path: str = "data/gmail_token.json"):
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
    return build("gmail", "v1", credentials=creds)


async def list_messages(query: str = "is:unread", max_results: int = 10,
                        credentials_path: str = "data/gmail_credentials.json") -> list[dict]:
    import asyncio
    def _fetch():
        service = _get_service(credentials_path)
        results = service.users().messages().list(
            userId="me", q=query, maxResults=max_results
        ).execute()
        messages = results.get("messages", [])
        detailed = []
        for msg in messages:
            full = service.users().messages().get(userId="me", id=msg["id"], format="metadata").execute()
            headers = {h["name"]: h["value"] for h in full.get("payload", {}).get("headers", [])}
            detailed.append({
                "id": msg["id"],
                "subject": headers.get("Subject", ""),
                "from": headers.get("From", ""),
                "date": headers.get("Date", ""),
                "snippet": full.get("snippet", ""),
            })
        return detailed
    return await asyncio.get_event_loop().run_in_executor(None, _fetch)


async def get_message(msg_id: str, credentials_path: str = "data/gmail_credentials.json") -> dict:
    import asyncio
    def _fetch():
        service = _get_service(credentials_path)
        msg = service.users().messages().get(userId="me", id=msg_id, format="full").execute()
        headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
        body = ""
        payload = msg.get("payload", {})
        if "body" in payload and payload["body"].get("data"):
            body = base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="replace")
        elif "parts" in payload:
            for part in payload["parts"]:
                if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
                    body = base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", errors="replace")
                    break
        return {
            "id": msg_id,
            "subject": headers.get("Subject", ""),
            "from": headers.get("From", ""),
            "to": headers.get("To", ""),
            "date": headers.get("Date", ""),
            "body": body,
        }
    return await asyncio.get_event_loop().run_in_executor(None, _fetch)


async def send_email(to: str, subject: str, body: str,
                     credentials_path: str = "data/gmail_credentials.json") -> dict:
    import asyncio
    def _send():
        service = _get_service(credentials_path)
        message = MIMEText(body)
        message["to"] = to
        message["subject"] = subject
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
        result = service.users().messages().send(
            userId="me", body={"raw": raw}
        ).execute()
        return {"id": result["id"], "status": "sent"}
    return await asyncio.get_event_loop().run_in_executor(None, _send)
