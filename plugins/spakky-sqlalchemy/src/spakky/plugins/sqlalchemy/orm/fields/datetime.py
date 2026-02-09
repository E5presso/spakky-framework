"""Date and time field metadata for SQLAlchemy ORM."""

from datetime import date, datetime, time, timedelta

from spakky.core.common.mutability import mutable

from spakky.plugins.sqlalchemy.orm.fields.base import AbstractField


@mutable
class Date(AbstractField[date]):
    """Metadata annotation for date fields.

    Maps to SQLAlchemy's Date type. Stores date values without time.

    Examples:
        >>> from typing import Annotated
        >>> from datetime import date
        >>> from spakky.plugins.sqlalchemy.orm.fields.datetime import Date
        >>>
        >>> class Event:
        ...     event_date: Annotated[date, Date()]
    """


@mutable
class DateTime(AbstractField[datetime]):
    """Metadata annotation for datetime fields.

    Maps to SQLAlchemy's DateTime type. Stores date and time values.

    Examples:
        >>> from typing import Annotated
        >>> from datetime import datetime
        >>> from spakky.plugins.sqlalchemy.orm.fields.datetime import DateTime
        >>>
        >>> class Post:
        ...     created_at: Annotated[datetime, DateTime(timezone=True)]
        ...     updated_at: Annotated[datetime, DateTime(timezone=True)]
    """

    timezone: bool = False
    """Whether to include timezone information."""


@mutable
class Time(AbstractField[time]):
    """Metadata annotation for time fields.

    Maps to SQLAlchemy's Time type. Stores time values without date.

    Examples:
        >>> from typing import Annotated
        >>> from datetime import time
        >>> from spakky.plugins.sqlalchemy.orm.fields.datetime import Time
        >>>
        >>> class Schedule:
        ...     start_time: Annotated[time, Time(timezone=True)]
    """

    timezone: bool = False
    """Whether to include timezone information."""


@mutable
class Interval(AbstractField[timedelta]):
    """Metadata annotation for time interval fields.

    Maps to SQLAlchemy's Interval type. Stores duration/interval values.

    Examples:
        >>> from typing import Annotated
        >>> from datetime import timedelta
        >>> from spakky.plugins.sqlalchemy.orm.fields.datetime import Interval
        >>>
        >>> class Task:
        ...     duration: Annotated[timedelta, Interval()]
        ...     processing_time: Annotated[timedelta, Interval(second_precision=6)]
    """

    native: bool = True
    """Use native INTERVAL type if available."""

    second_precision: int | None = None
    """Precision for seconds in the interval."""

    day_precision: int | None = None
    """Precision for days in the interval."""
