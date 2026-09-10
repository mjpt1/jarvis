"""Gmail + Google Calendar.

نیاز: فایلِ `~/.jarvis/credentials/google_credentials.json` (نوع OAuth «Desktop app»)
و کتابخانه‌های google-api-python-client / google-auth-oauthlib.
اولین بار مرورگر برای رضایت باز می‌شود؛ توکن در همان پوشه ذخیره می‌شود.
"""

from __future__ import annotations

import base64
import datetime
from email.mime.text import MIMEText

from ..logging_setup import get_logger
from ..paths import CREDENTIALS_DIR, ensure_dirs

log = get_logger("google")

_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/calendar",
]
_CRED_FILE = CREDENTIALS_DIR / "google_credentials.json"
_TOKEN_FILE = CREDENTIALS_DIR / "google_token.json"

_service_cache: dict = {}


def available() -> bool:
    if not _CRED_FILE.is_file():
        return False
    try:
        import google.auth  # noqa: F401
        import googleapiclient  # noqa: F401
        return True
    except Exception:
        return False


def _creds():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    ensure_dirs()
    creds = None
    if _TOKEN_FILE.is_file():
        creds = Credentials.from_authorized_user_file(str(_TOKEN_FILE), _SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(_CRED_FILE), _SCOPES)
            creds = flow.run_local_server(port=0)
        _TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")
    return creds


def _svc(name: str, version: str):
    key = f"{name}{version}"
    if key not in _service_cache:
        from googleapiclient.discovery import build
        _service_cache[key] = build(name, version, credentials=_creds(),
                                    cache_discovery=False)
    return _service_cache[key]


# ---------------- Gmail ----------------

def unread_summary(limit: int = 5) -> str:
    try:
        svc = _svc("gmail", "v1")
        res = svc.users().messages().list(
            userId="me", q="is:unread in:inbox", maxResults=limit).execute()
        ids = [m["id"] for m in res.get("messages", [])]
        if not ids:
            return "هیچ ایمیلِ خوانده‌نشده‌ای نداری."
        lines = []
        for mid in ids:
            m = svc.users().messages().get(
                userId="me", id=mid, format="metadata",
                metadataHeaders=["From", "Subject"]).execute()
            hdr = {h["name"]: h["value"] for h in m["payload"]["headers"]}
            frm = hdr.get("From", "?").split("<")[0].strip()
            lines.append(f"از {frm}: {hdr.get('Subject', '(بدون موضوع)')}")
        return f"{len(lines)} ایمیلِ خوانده‌نشده:\n" + "\n".join(lines)
    except Exception as exc:
        log.warning("Gmail: %s", exc)
        return "دسترسی به ایمیل ناموفق بود."


def send_email(to: str, subject: str, body: str) -> str:
    try:
        svc = _svc("gmail", "v1")
        msg = MIMEText(body, _charset="utf-8")
        msg["to"] = to
        msg["subject"] = subject
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        svc.users().messages().send(userId="me", body={"raw": raw}).execute()
        log.info("ایمیل فرستاده شد به %s", to)
        return f"ایمیل به {to} فرستاده شد."
    except Exception as exc:
        log.warning("ارسال ایمیل: %s", exc)
        return "ارسال ایمیل ناموفق بود."


# ---------------- Calendar ----------------

def upcoming_events(limit: int = 5, days: int = 7) -> str:
    try:
        svc = _svc("calendar", "v3")
        now = datetime.datetime.now(datetime.UTC)
        end = now + datetime.timedelta(days=days)
        res = svc.events().list(
            calendarId="primary", timeMin=now.isoformat(), timeMax=end.isoformat(),
            singleEvents=True, orderBy="startTime", maxResults=limit).execute()
        items = res.get("items", [])
        if not items:
            return f"در {days} روزِ آینده رویدادی نداری."
        lines = []
        for ev in items:
            start = ev["start"].get("dateTime", ev["start"].get("date", ""))
            lines.append(f"{start[:16].replace('T', ' ')} — {ev.get('summary', '(بی‌عنوان)')}")
        return "رویدادهای پیشِ رو:\n" + "\n".join(lines)
    except Exception as exc:
        log.warning("Calendar: %s", exc)
        return "دسترسی به تقویم ناموفق بود."


def create_event(title: str, start_iso: str, end_iso: str = "") -> str:
    try:
        svc = _svc("calendar", "v3")
        if not end_iso:
            s = datetime.datetime.fromisoformat(start_iso)
            end_iso = (s + datetime.timedelta(hours=1)).isoformat()
        ev = {"summary": title,
              "start": {"dateTime": start_iso},
              "end": {"dateTime": end_iso}}
        svc.events().insert(calendarId="primary", body=ev).execute()
        return f"رویدادِ «{title}» در تقویم ثبت شد."
    except Exception as exc:
        log.warning("ساخت رویداد: %s", exc)
        return "ثبتِ رویداد ناموفق بود."
