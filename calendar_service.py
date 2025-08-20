import os
import json
from datetime import datetime, timedelta, time
from typing import List, Tuple, Optional

from google.oauth2 import service_account
from googleapiclient.discovery import build

try:
    from zoneinfo import ZoneInfo  # Python 3.9+
except Exception:  # pragma: no cover
    ZoneInfo = None


GOOGLE_SCOPES = ["https://www.googleapis.com/auth/calendar"]
CALENDAR_ID = os.getenv("GOOGLE_CALENDAR_ID", "primary")
SERVICE_ACCOUNT_JSON = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
TIMEZONE = os.getenv("TIMEZONE", "America/Sao_Paulo")
BUSINESS_START_HOUR = int(os.getenv("BUSINESS_START_HOUR", "9"))
BUSINESS_END_HOUR = int(os.getenv("BUSINESS_END_HOUR", "18"))


def _get_service():
    if not SERVICE_ACCOUNT_JSON:
        raise RuntimeError("GOOGLE_SERVICE_ACCOUNT_JSON nÃ£o configurado.")
    if SERVICE_ACCOUNT_JSON.strip().startswith("{"):
        credentials = service_account.Credentials.from_service_account_info(
            json.loads(SERVICE_ACCOUNT_JSON), scopes=GOOGLE_SCOPES
        )
    else:
        credentials = service_account.Credentials.from_service_account_file(
            SERVICE_ACCOUNT_JSON, scopes=GOOGLE_SCOPES
        )
    return build("calendar", "v3", credentials=credentials, cache_discovery=False)


def _tz() -> Optional[ZoneInfo]:
    try:
        return ZoneInfo(TIMEZONE)
    except Exception:
        return None


def _rfc3339(dt: datetime) -> str:
    if dt.tzinfo is None:
        tz = _tz()
        if tz is not None:
            dt = dt.replace(tzinfo=tz)
    return dt.isoformat()


def _business_hours_for_day(day: datetime) -> Tuple[datetime, datetime]:
    tz = _tz()
    start = datetime.combine(day.date(), time(BUSINESS_START_HOUR, 0))
    end = datetime.combine(day.date(), time(BUSINESS_END_HOUR, 0))
    if tz:
        start = start.replace(tzinfo=tz)
        end = end.replace(tzinfo=tz)
    return start, end


def _is_business_day(dt: datetime) -> bool:
    return dt.weekday() < 5  # Mon-Fri


def _list_busy_intervals(service, time_min: datetime, time_max: datetime) -> List[Tuple[datetime, datetime]]:
    body = {
        "timeMin": _rfc3339(time_min),
        "timeMax": _rfc3339(time_max),
        "timeZone": TIMEZONE,
        "items": [{"id": CALENDAR_ID}],
    }
    resp = service.freebusy().query(body=body).execute()
    busy_items = resp.get("calendars", {}).get(CALENDAR_ID, {}).get("busy", [])
    intervals: List[Tuple[datetime, datetime]] = []
    for b in busy_items:
        # Google returns RFC3339 with timezone
        start = datetime.fromisoformat(b["start"].replace("Z", "+00:00"))
        end = datetime.fromisoformat(b["end"].replace("Z", "+00:00"))
        intervals.append((start, end))
    return intervals


def _generate_candidate_slots(day: datetime, duration_minutes: int = 60) -> List[Tuple[datetime, datetime]]:
    start, end = _business_hours_for_day(day)
    slots: List[Tuple[datetime, datetime]] = []
    cursor = start
    delta = timedelta(minutes=duration_minutes)
    # step igual à duração => apenas 1 consulta por hora quando duration_minutes=60
    step = timedelta(minutes=duration_minutes)
    while cursor + delta <= end:
        slots.append((cursor, cursor + delta))
        cursor += step
    return slots


def _filter_free_slots(candidates: List[Tuple[datetime, datetime]], busy: List[Tuple[datetime, datetime]]) -> List[Tuple[datetime, datetime]]:
    free: List[Tuple[datetime, datetime]] = []
    for c_start, c_end in candidates:
        conflict = False
        for b_start, b_end in busy:
            if not (c_end <= b_start or c_start >= b_end):
                conflict = True
                break
        if not conflict:
            free.append((c_start, c_end))
    return free


def get_next_available_slots(
    count: int = 3,
    duration_minutes: int = 60,
    preferred_period: Optional[str] = None,
    start_offset_days: int = 0,
) -> List[Tuple[datetime, datetime]]:
    service = _get_service()
    tz = _tz()
    now = datetime.now(tz) if tz else datetime.now()
    found: List[Tuple[datetime, datetime]] = []
    day = now + timedelta(days=start_offset_days)
    horizon_days = 14
    for _ in range(horizon_days):
        if not _is_business_day(day):
            day += timedelta(days=1)
            continue
        bh_start, bh_end = _business_hours_for_day(day)
        busy = _list_busy_intervals(service, bh_start, bh_end)
        candidates = _generate_candidate_slots(day, duration_minutes)
        # se for hoje, considerar apenas slots a partir de agora + 60min
        if day.date() == now.date():
            min_start = now + timedelta(minutes=60)
            candidates = [(s, e) for (s, e) in candidates if s >= min_start]
        # filtra por período preferido
        if preferred_period:
            if preferred_period.lower().startswith("man"):
                candidates = [(s, e) for (s, e) in candidates if 9 <= s.hour < 12]
            elif preferred_period.lower().startswith("tar"):
                candidates = [(s, e) for (s, e) in candidates if 13 <= s.hour < 18]
        free_slots = _filter_free_slots(candidates, busy)
        for slot in free_slots:
            if len(found) < count:
                found.append(slot)
        if len(found) >= count:
            break
        day += timedelta(days=1)
    return found


def create_event(title: str, start_datetime: datetime, end_datetime: datetime, description: Optional[str] = None,
                 attendees: Optional[List[str]] = None) -> str:
    service = _get_service()
    event_body = {
        "summary": title,
        "description": description or "",
        "start": {"dateTime": _rfc3339(start_datetime), "timeZone": TIMEZONE},
        "end": {"dateTime": _rfc3339(end_datetime), "timeZone": TIMEZONE},
    }
    if attendees:
        event_body["attendees"] = [{"email": e} for e in attendees if e]
    created = service.events().insert(calendarId=CALENDAR_ID, body=event_body, sendUpdates="all").execute()
    return created.get("id")


def get_next_business_days(count: int = 5, start_offset_days: int = 0) -> List[datetime]:
    tz = _tz()
    now = datetime.now(tz) if tz else datetime.now()
    days: List[datetime] = []
    cursor = now + timedelta(days=start_offset_days)
    horizon = 30
    for _ in range(horizon):
        if _is_business_day(cursor):
            days.append(cursor)
            if len(days) >= count:
                break
        cursor += timedelta(days=1)
    return days


def get_available_slots_for_date(target_date: datetime, duration_minutes: int = 60, preferred_period: Optional[str] = None) -> List[Tuple[datetime, datetime]]:
    service = _get_service()
    tz = _tz()
    # normalize to local midnight
    day = target_date
    if tz and day.tzinfo is None:
        day = day.replace(tzinfo=tz)
    bh_start, bh_end = _business_hours_for_day(day)
    now = datetime.now(tz) if tz else datetime.now()
    busy = _list_busy_intervals(service, bh_start, bh_end)
    candidates = _generate_candidate_slots(day, duration_minutes)
    if day.date() == now.date():
        min_start = now + timedelta(minutes=60)
        candidates = [(s, e) for (s, e) in candidates if s >= min_start]
    if preferred_period:
        if preferred_period.lower().startswith("man"):
            candidates = [(s, e) for (s, e) in candidates if 9 <= s.hour < 12]
        elif preferred_period.lower().startswith("tar"):
            candidates = [(s, e) for (s, e) in candidates if 13 <= s.hour < 18]
    return _filter_free_slots(candidates, busy)


