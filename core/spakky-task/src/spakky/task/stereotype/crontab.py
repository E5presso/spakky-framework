"""Crontab value object for schedule specification."""

from dataclasses import dataclass
from enum import IntEnum


class Weekday(IntEnum):
    """Day of the week (ISO 8601: Monday=0)."""

    MONDAY = 0
    TUESDAY = 1
    WEDNESDAY = 2
    THURSDAY = 3
    FRIDAY = 4
    SATURDAY = 5
    SUNDAY = 6


class Month(IntEnum):
    """Month of the year (1-12)."""

    JANUARY = 1
    FEBRUARY = 2
    MARCH = 3
    APRIL = 4
    MAY = 5
    JUNE = 6
    JULY = 7
    AUGUST = 8
    SEPTEMBER = 9
    OCTOBER = 10
    NOVEMBER = 11
    DECEMBER = 12


@dataclass(frozen=True)
class Crontab:
    """Cron-like schedule specification using Python native types.

    Fields use ``None`` to mean "every" (wildcard).
    A single ``int`` means exactly that value; a ``tuple`` means multiple values.

    Example:
        # Every Monday at 03:00
        Crontab(weekday=Weekday.MONDAY, hour=3)

        # Mon/Wed/Fri at 09:00
        Crontab(weekday=(Weekday.MONDAY, Weekday.WEDNESDAY, Weekday.FRIDAY), hour=9)

        # 1st and 15th of every month at midnight
        Crontab(day=(1, 15))
    """

    month: Month | tuple[Month, ...] | None = None
    """Month of the year. None means every month."""

    day: int | tuple[int, ...] | None = None
    """Day of the month (1-31). None means every day."""

    weekday: Weekday | tuple[Weekday, ...] | None = None
    """Day of the week. None means every day."""

    hour: int = 0
    """Hour of the day (0-23)."""

    minute: int = 0
    """Minute of the hour (0-59)."""
