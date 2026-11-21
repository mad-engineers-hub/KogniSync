"""Timezone and Timestamp Integrity Utility for KogniSync Backend

Implements strict UTC instant persistence with local interpretation for India Standard Time (IST / Asia/Kolkata).
IST is UTC+05:30 (fixed +330 minutes offset, no DST).
"""

from datetime import datetime, timezone, timedelta
from typing import Any

IST = timezone(timedelta(hours=5, minutes=30), name="IST")
IST_OFFSET_MINUTES = 330


def ist_to_utc_instant(date_str: str, time_str: str) -> datetime:
    """Converts local date ('YYYY-MM-DD') and local time ('HH:mm') in IST into a UTC datetime instant.

    Example: '2026-11-15' and '20:00' -> 2026-11-15 14:30:00+00:00
    """
    try:
        parts = [int(p) for p in date_str.split("-")]
        if len(parts) == 3:
            year, month, day = parts[0], parts[1], parts[2]
        else:
            year, month, day = 2026, 11, 15
    except Exception:
        year, month, day = 2026, 11, 15

    hour = 20
    minute = 0
    if time_str and ":" in time_str:
        try:
            t_parts = [int(p) for p in time_str.split(":")]
            if len(t_parts) >= 2:
                hour = min(23, max(0, t_parts[0]))
                minute = min(59, max(0, t_parts[1]))
        except Exception:
            pass

    local_dt = datetime(year, month, day, hour, minute, 0, tzinfo=IST)
    return local_dt.astimezone(timezone.utc)


def utc_to_ist_components(dt: datetime | str) -> dict[str, Any]:
    """Converts a UTC instant (datetime or ISO string) into its local IST components."""
    if isinstance(dt, str):
        # Handle trailing Z or offset
        iso_str = dt.replace("Z", "+00:00")
        dt_obj = datetime.fromisoformat(iso_str)
    else:
        dt_obj = dt

    if dt_obj.tzinfo is None:
        dt_obj = dt_obj.replace(tzinfo=timezone.utc)

    ist_dt = dt_obj.astimezone(IST)
    display_time = ist_dt.strftime("%I:%M %p").lstrip("0")
    display_dt = f"{ist_dt.strftime('%d-%b')} {display_time}"

    return {
        "date_str": ist_dt.strftime("%Y-%m-%d"),
        "time_str": ist_dt.strftime("%H:%M"),
        "hour": ist_dt.hour,
        "minute": ist_dt.minute,
        "iso_with_offset": ist_dt.isoformat(),
        "display_time": display_time,
        "display_date_time": display_dt,
    }


def format_ist_time(dt: datetime | str) -> str:
    """Formats a UTC instant into a clean local IST time string for UI display."""
    try:
        return utc_to_ist_components(dt)["display_time"]
    except Exception:
        return str(dt)
