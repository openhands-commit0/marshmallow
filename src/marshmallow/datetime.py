"""Datetime-related utilities."""
from __future__ import annotations
import datetime as dt

def is_aware(dt_obj: dt.datetime | dt.time) -> bool:
    """Return True if the datetime or time object has tzinfo.

    :param dt_obj: The datetime or time object to check.
    """
    return dt_obj.tzinfo is not None and dt_obj.tzinfo.utcoffset(None) is not None