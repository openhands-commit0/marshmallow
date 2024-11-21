"""Utility methods for marshmallow."""
from __future__ import annotations

__all__ = [
    'is_generator', 'is_iterable_but_not_string', 'is_collection',
    'is_instance_or_subclass', 'is_keyed_tuple', 'pprint', 'from_rfc',
    'rfcformat', 'get_fixed_timezone', 'from_iso_datetime', 'from_iso_time',
    'from_iso_date', 'isoformat', 'pluck', 'get_value', 'set_value',
    'callable_or_raise', 'get_func_args', 'resolve_field_instance',
    'timedelta_to_microseconds', 'missing', 'EXCLUDE', 'INCLUDE', 'RAISE'
]
import collections
import datetime as dt
import functools
import inspect
import json
import re
import typing
import warnings
from collections.abc import Mapping
from email.utils import format_datetime, parsedate_to_datetime
from pprint import pprint as py_pprint
from marshmallow.base import FieldABC
from marshmallow.exceptions import FieldInstanceResolutionError
from marshmallow.warnings import RemovedInMarshmallow4Warning
EXCLUDE = 'exclude'
INCLUDE = 'include'
RAISE = 'raise'
_UNKNOWN_VALUES = {EXCLUDE, INCLUDE, RAISE}

class _Missing:

    def __bool__(self):
        return False

    def __copy__(self):
        return self

    def __deepcopy__(self, _):
        return self

    def __repr__(self):
        return '<marshmallow.missing>'
missing = _Missing()

def is_generator(obj) -> bool:
    """Return True if ``obj`` is a generator"""
    return inspect.isgenerator(obj)

def is_iterable_but_not_string(obj) -> bool:
    """Return True if ``obj`` is an iterable object that isn't a string."""
    return not isinstance(obj, (str, bytes)) and hasattr(obj, '__iter__')

def is_collection(obj) -> bool:
    """Return True if ``obj`` is a collection type, e.g list, tuple, queryset."""
    return is_iterable_but_not_string(obj) and not isinstance(obj, Mapping)

def is_instance_or_subclass(val, class_) -> bool:
    """Return True if ``val`` is either a subclass or instance of ``class_``."""
    try:
        return issubclass(val, class_)
    except TypeError:
        return isinstance(val, class_)

def is_keyed_tuple(obj) -> bool:
    """Return True if ``obj`` has keyed tuple behavior, such as
    namedtuples or SQLAlchemy's KeyedTuples.
    """
    return isinstance(obj, tuple) and hasattr(obj, '_fields')

def pprint(obj, *args, **kwargs) -> None:
    """Pretty-printing function that can pretty-print OrderedDicts
    like regular dictionaries. Useful for printing the output of
    :meth:`marshmallow.Schema.dump`.

    .. deprecated:: 3.7.0
        marshmallow.pprint will be removed in marshmallow 4.
    """
    warnings.warn(
        'marshmallow.pprint is deprecated and will be removed in marshmallow 4.',
        RemovedInMarshmallow4Warning,
        stacklevel=2
    )
    py_pprint(obj, *args, **kwargs)

def from_rfc(datestring: str) -> dt.datetime:
    """Parse a RFC822-formatted datetime string and return a datetime object.

    https://stackoverflow.com/questions/885015/how-to-parse-a-rfc-2822-date-time-into-a-python-datetime  # noqa: B950
    """
    return parsedate_to_datetime(datestring)

def rfcformat(datetime: dt.datetime) -> str:
    """Return the RFC822-formatted representation of a datetime object.

    :param datetime datetime: The datetime.
    """
    return format_datetime(datetime)
_iso8601_datetime_re = re.compile('(?P<year>\\d{4})-(?P<month>\\d{1,2})-(?P<day>\\d{1,2})[T ](?P<hour>\\d{1,2}):(?P<minute>\\d{1,2})(?::(?P<second>\\d{1,2})(?:\\.(?P<microsecond>\\d{1,6})\\d{0,6})?)?(?P<tzinfo>Z|[+-]\\d{2}(?::?\\d{2})?)?$')
_iso8601_date_re = re.compile('(?P<year>\\d{4})-(?P<month>\\d{1,2})-(?P<day>\\d{1,2})$')
_iso8601_time_re = re.compile('(?P<hour>\\d{1,2}):(?P<minute>\\d{1,2})(?::(?P<second>\\d{1,2})(?:\\.(?P<microsecond>\\d{1,6})\\d{0,6})?)?')

def get_fixed_timezone(offset: int | float | dt.timedelta) -> dt.timezone:
    """Return a tzinfo instance with a fixed offset from UTC."""
    if isinstance(offset, dt.timedelta):
        offset = offset.total_seconds()
    return dt.timezone(dt.timedelta(seconds=offset))

def from_iso_datetime(value):
    """Parse a string and return a datetime.datetime.

    This function supports time zone offsets. When the input contains one,
    the output uses a timezone with a fixed offset from UTC.
    """
    match = _iso8601_datetime_re.match(value)
    if not match:
        raise ValueError('Not a valid ISO8601-formatted datetime string')

    groups = match.groupdict()
    groups['year'] = int(groups['year'])
    groups['month'] = int(groups['month'])
    groups['day'] = int(groups['day'])
    groups['hour'] = int(groups['hour'])
    groups['minute'] = int(groups['minute'])
    groups['second'] = int(groups['second']) if groups['second'] else 0
    groups['microsecond'] = int(groups['microsecond'].ljust(6, '0')) if groups['microsecond'] else 0

    tzinfo = None
    if groups['tzinfo']:
        tzinfo_str = groups.pop('tzinfo')
        if tzinfo_str == 'Z':
            tzinfo = dt.timezone.utc
        else:
            offset_mins = 0
            if ':' in tzinfo_str:
                hours, minutes = map(int, tzinfo_str[1:].split(':'))
                offset_mins = hours * 60 + minutes
            else:
                offset_mins = int(tzinfo_str[1:]) * 60
            if tzinfo_str[0] == '-':
                offset_mins = -offset_mins
            tzinfo = get_fixed_timezone(offset_mins * 60)
    else:
        groups.pop('tzinfo')

    return dt.datetime(tzinfo=tzinfo, **groups)

def from_iso_time(value):
    """Parse a string and return a datetime.time.

    This function doesn't support time zone offsets.
    """
    match = _iso8601_time_re.match(value)
    if not match:
        raise ValueError('Not a valid ISO8601-formatted time string')

    groups = match.groupdict()
    groups['hour'] = int(groups['hour'])
    groups['minute'] = int(groups['minute'])
    groups['second'] = int(groups['second']) if groups['second'] else 0
    groups['microsecond'] = int(groups['microsecond'].ljust(6, '0')) if groups['microsecond'] else 0

    return dt.time(**groups)

def from_iso_date(value):
    """Parse a string and return a datetime.date."""
    match = _iso8601_date_re.match(value)
    if not match:
        raise ValueError('Not a valid ISO8601-formatted date string')

    groups = match.groupdict()
    return dt.date(
        int(groups['year']), int(groups['month']), int(groups['day'])
    )

def isoformat(datetime: dt.datetime) -> str:
    """Return the ISO8601-formatted representation of a datetime object.

    :param datetime datetime: The datetime.
    """
    return datetime.isoformat()

def pluck(dictlist: list[dict[str, typing.Any]], key: str):
    """Extracts a list of dictionary values from a list of dictionaries.
    ::

        >>> dlist = [{'id': 1, 'name': 'foo'}, {'id': 2, 'name': 'bar'}]
        >>> pluck(dlist, 'id')
        [1, 2]
    """
    return [d[key] for d in dictlist]

def get_value(obj, key: int | str, default=missing):
    """Helper for pulling a keyed value off various types of objects. Fields use
    this method by default to access attributes of the source object. For object `x`
    and attribute `i`, this method first tries to access `x[i]`, and then falls back to
    `x.i` if an exception is raised.

    .. warning::
        If an object `x` does not raise an exception when `x[i]` does not exist,
        `get_value` will never check the value `x.i`. Consider overriding
        `marshmallow.fields.Field.get_value` in this case.
    """
    if not hasattr(obj, '__getitem__'):
        return getattr(obj, key, default)

    try:
        return obj[key]
    except (KeyError, IndexError, TypeError, AttributeError):
        return getattr(obj, key, default)

def set_value(dct: dict[str, typing.Any], key: str, value: typing.Any):
    """Set a value in a dict. If `key` contains a '.', it is assumed
    be a path (i.e. dot-delimited string) to the value's location.

    ::

        >>> d = {}
        >>> set_value(d, 'foo.bar', 42)
        >>> d
        {'foo': {'bar': 42}}
    """
    if '.' not in key:
        dct[key] = value
        return

    parts = key.split('.')
    for i, part in enumerate(parts[:-1]):
        if part not in dct:
            dct[part] = {}
        else:
            if not isinstance(dct[part], dict):
                raise ValueError(
                    f"String path conflicts with current dictionary structure at {'.'.join(parts[:i+1])}"
                )
        dct = dct[part]

    dct[parts[-1]] = value

def callable_or_raise(obj):
    """Check that an object is callable, else raise a :exc:`TypeError`."""
    if not callable(obj):
        raise TypeError('Object {!r} is not callable'.format(obj))

def get_func_args(func: typing.Callable) -> list[str]:
    """Given a callable, return a list of argument names. Handles
    `functools.partial` objects and class-based callables.

    .. versionchanged:: 3.0.0a1
        Do not return bound arguments, eg. ``self``.
    """
    if isinstance(func, functools.partial):
        return get_func_args(func.func)

    if inspect.isfunction(func) or inspect.ismethod(func):
        return list(inspect.signature(func).parameters.keys())

    # Callable class
    return list(inspect.signature(func.__call__).parameters.keys())[1:]

def resolve_field_instance(cls_or_instance):
    """Return a Schema instance from a Schema class or instance.

    :param type|Schema cls_or_instance: Marshmallow Schema class or instance.
    """
    if isinstance(cls_or_instance, type) and issubclass(cls_or_instance, FieldABC):
        return cls_or_instance()
    if isinstance(cls_or_instance, FieldABC):
        return cls_or_instance
    raise FieldInstanceResolutionError(
        'Could not resolve field instance from {!r}'.format(cls_or_instance)
    )

def timedelta_to_microseconds(value: dt.timedelta) -> int:
    """Compute the total microseconds of a timedelta

    https://github.com/python/cpython/blob/bb3e0c240bc60fe08d332ff5955d54197f79751c/Lib/datetime.py#L665-L667  # noqa: B950
    """
    return (value.days * 86400 + value.seconds) * 1000000 + value.microseconds