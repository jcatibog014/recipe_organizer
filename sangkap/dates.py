"""Time helpers. Plain functions without Flask.

The database stores times in UTC without a time zone (SQLite can't keep
one), so compare them with utcnow(), never with a local time.
"today" is worked out in Philippine time, for the meal plan.
"""
from datetime import date, datetime, timedelta, timezone

# The Philippines is UTC+8 all year (no daylight saving). The live server's
# clock runs on UTC, so a new day would otherwise start at 8 AM.
PH_TIME = timezone(timedelta(hours=8), "PHT")


def utcnow():
    """Now in UTC, without tzinfo: the form the database keeps."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def today():
    return datetime.now(PH_TIME).date()


def week_start(day):
    """The Monday of day's week."""
    return day - timedelta(days=day.weekday())


def parse_day(text):
    """ "2026-10-28" -> date(2026, 10, 28), or None if it isn't a date."""
    try:
        return date.fromisoformat(text or "")
    except ValueError:
        return None
