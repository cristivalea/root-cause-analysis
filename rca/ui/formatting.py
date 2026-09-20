"""How values are written on screen.

Dates, durations and numbers are formatted in one place, so the same moment is never
written two different ways on two screens. The interface shows times in UTC, because that
is how the incidents, changes and logs are recorded.
"""

from datetime import datetime, timezone

from rca.ui.strings import t

DATE_TIME = "%d %b %Y, %H:%M"
DATE = "%d %b %Y"


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def date_time(value: datetime | None) -> str:
    """A moment, to the minute: 14 Jul 2026, 14:32 UTC."""
    return f"{_utc(value).strftime(DATE_TIME)} UTC" if value else t("common.unknown")


def date(value: datetime | None) -> str:
    """A day: 14 Jul 2026."""
    return _utc(value).strftime(DATE) if value else t("common.unknown")


def minutes(count: int | None) -> str:
    """A length of time written the way a person says it: 45 min, 1 h 35 min, 2 h."""
    if count is None:
        return t("common.unknown")
    hours, rest = divmod(int(count), 60)
    if not hours:
        return t("format.minutes", count=rest)
    if not rest:
        return t("format.hours", count=hours)
    return t("format.hours_minutes", hours=hours, minutes=rest)


def seconds(count: float | None) -> str:
    """How long something took: 48 s, or the same as `minutes` once past a minute."""
    if count is None:
        return t("common.unknown")
    return t("format.seconds", count=round(count)) if count < 60 else minutes(round(count / 60))


def number(value: int | None) -> str:
    """A count with thousands separated: 18,420."""
    return f"{value:,}" if value is not None else t("common.unknown")
