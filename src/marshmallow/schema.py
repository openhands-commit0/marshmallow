"""The :class:`Schema` class, including its metaclass and options (class Meta)."""
from __future__ import annotations
import copy
import datetime as dt
import decimal
import inspect
import json
import typing
import uuid
import warnings
from abc import ABCMeta
from collections import OrderedDict, defaultdict
from collections.abc import Mapping
from marshmallow import base, class_registry, types
from marshmallow.decorators import POST_DUMP, POST_LOAD, PRE_DUMP, PRE_LOAD, VALIDATES, VALIDATES_SCHEMA
from marshmallow.error_store import ErrorStore
from marshmallow.exceptions import StringNotCollectionError, ValidationError
from marshmallow.orderedset import OrderedSet
from marshmallow.utils import EXCLUDE, INCLUDE, RAISE, get_value, is_collection, is_instance_or_subclass, missing, set_value, validate_unknown_parameter_value
from marshmallow import fields as ma_fields
from marshmallow.warnings import RemovedInMarshmallow4Warning
_T = typing.TypeVar('_T')

def _get_fields(attrs):
    """Get fields from a class

    :param attrs: Mapping of class attributes
    """
    pass

def _get_fields_by_mro(klass):
    """Collect fields from a class, following its method resolution order. The
    class itself is excluded from the search; only its parents are checked. Get
    fields from ``_declared_fields`` if available, else use ``__dict__``.

    :param type klass: Class whose fields to retrieve
    """
    pass

class SchemaMeta(ABCMeta):
    """Metaclass for the Schema class. Binds the declared fields to
    a ``_declared_fields`` attribute, which is a dictionary mapping attribute
    names to field objects. Also sets the ``opts`` class attribute, which is
    the Schema class's ``class Meta`` options.
    """

    def __new__(mcs, name, bases, attrs):
        meta = attrs.get('Meta')
        ordered = getattr(meta, 'ordered', False)
        if not ordered:
            for base_ in bases:
                if hasattr(base_, 'Meta') and hasattr(base_.Meta, 'ordered'):
                    ordered = base_.Meta.ordered
                    break
            else:
                ordered = False
        cls_fields = _get_fields(attrs)
        for field_name, _ in cls_fields:
            del attrs[field_name]
        klass = super().__new__(mcs, name, bases, attrs)
        inherited_fields = _get_fields_by_mro(klass)
        meta = klass.Meta
        klass.opts = klass.OPTIONS_CLASS(meta, ordered=ordered)
        cls_fields += list(klass.opts.include.items())
        klass._declared_fields = mcs.get_declared_fields(klass=klass, cls_fields=cls_fields, inherited_fields=inherited_fields, dict_cls=dict)
        return klass

    @classmethod
    def get_declared_fields(mcs, klass: type, cls_fields: list, inherited_fields: list, dict_cls: type=dict):
        """Returns a dictionary of field_name => `Field` pairs declared on the class.
        This is exposed mainly so that plugins can add additional fields, e.g. fields
        computed from class Meta options.

        :param klass: The class object.
        :param cls_fields: The fields declared on the class, including those added
            by the ``include`` class Meta option.
        :param inherited_fields: Inherited fields.
        :param dict_cls: dict-like class to use for dict output Default to ``dict``.
        """
        pass

    def __init__(cls, name, bases, attrs):
        super().__init__(name, bases, attrs)
        if name and cls.opts.register:
            class_registry.register(name, cls)
        cls._hooks = cls.resolve_hooks()

    def resolve_hooks(cls) -> dict[types.Tag, list[str]]:
        """Add in the decorated processors

        By doing this after constructing the class, we let standard inheritance
        do all the hard work.
        """
        pass

class SchemaOpts:
    """class Meta options for the :class:`Schema`. Defines defaults."""

    def __init__(self, meta, ordered: bool=False):
        self.fields = getattr(meta, 'fields', ())
        if not isinstance(self.fields, (list, tuple)):
            raise ValueError('`fields` option must be a list or tuple.')
        self.additional = getattr(meta, 'additional', ())
        if not isinstance(self.additional, (list, tuple)):
            raise ValueError('`additional` option must be a list or tuple.')
        if self.fields and self.additional:
            raise ValueError('Cannot set both `fields` and `additional` options for the same Schema.')
        self.exclude = getattr(meta, 'exclude', ())
        if not isinstance(self.exclude, (list, tuple)):
            raise ValueError('`exclude` must be a list or tuple.')
        self.dateformat = getattr(meta, 'dateformat', None)
        self.datetimeformat = getattr(meta, 'datetimeformat', None)
        self.timeformat = getattr(meta, 'timeformat', None)
        if hasattr(meta, 'json_module'):
            warnings.warn('The json_module class Meta option is deprecated. Use render_module instead.', RemovedInMarshmallow4Warning, stacklevel=2)
            render_module = getattr(meta, 'json_module', json)
        else:
            render_module = json
        self.render_module = getattr(meta, 'render_module', render_module)
        self.ordered = getattr(meta, 'ordered', ordered)
        self.index_errors = getattr(meta, 'index_errors', True)
        self.include = getattr(meta, 'include', {})
        self.load_only = getattr(meta, 'load_only', ())
        self.dump_only = getattr(meta, 'dump_only', ())
        self.unknown = validate_unknown_parameter_value(getattr(meta, 'unknown', RAISE))
        self.register = getattr(meta, 'register', True)

class Schema(base.SchemaABC, metaclass=SchemaMeta):
    """Base schema class with which to define custom schemas.

    Example usage:

    .. code-block:: python

        import datetime as dt
        from dataclasses import dataclass

        from marshmallow import Schema, fields


        @dataclass
        class Album:
            title: str
            release_date: dt.date


        class AlbumSchema(Schema):
            title = fields.Str()
            release_date = fields.Date()


        album = Album("Beggars Banquet", dt.date(1968, 12, 6))
        schema = AlbumSchema()
        data = schema.dump(album)
        data  # {'release_date': '1968-12-06', 'title': 'Beggars Banquet'}

    :param only: Whitelist of the declared fields to select when
        instantiating the Schema. If None, all fields are used. Nested fields
        can be represented with dot delimiters.
    :param exclude: Blacklist of the declared fields to exclude
        when instantiating the Schema. If a field appears in both `only` and
        `exclude`, it is not used. Nested fields can be represented with dot
        delimiters.
    :param many: Should be set to `True` if ``obj`` is a collection
        so that the object will be serialized to a list.
    :param context: Optional context passed to :class:`fields.Method` and
        :class:`fields.Function` fields.
    :param load_only: Fields to skip during serialization (write-only fields)
    :param dump_only: Fields to skip during deserialization (read-only fields)
    :param partial: Whether to ignore missing fields and not require
        any fields declared. Propagates down to ``Nested`` fields as well. If
        its value is an iterable, only missing fields listed in that iterable
        will be ignored. Use dot delimiters to specify nested fields.
    :param unknown: Whether to exclude, include, or raise an error for unknown
        fields in the data. Use `EXCLUDE`, `INCLUDE` or `RAISE`.

    .. versionchanged:: 3.0.0
        `prefix` parameter removed.

    .. versionchanged:: 2.0.0
        `__validators__`, `__preprocessors__`, and `__data_handlers__` are removed in favor of
        `marshmallow.decorators.validates_schema`,
        `marshmallow.decorators.pre_load` and `marshmallow.decorators.post_dump`.
        `__accessor__` and `__error_handler__` are deprecated. Implement the
        `handle_error` and `get_attribute` methods instead.
    """
    TYPE_MAPPING = {str: ma_fields.String, bytes: ma_fields.String, dt.datetime: ma_fields.DateTime, float: ma_fields.Float, bool: ma_fields.Boolean, tuple: ma_fields.Raw, list: ma_fields.Raw, set: ma_fields.Raw, int: ma_fields.Integer, uuid.UUID: ma_fields.UUID, dt.time: ma_fields.Time, dt.date: ma_fields.Date, dt.timedelta: ma_fields.TimeDelta, decimal.Decimal: ma_fields.Decimal}
    error_messages = {}
    _default_error_messages = {'type': 'Invalid input type.', 'unknown': 'Unknown field.'}
    OPTIONS_CLASS = SchemaOpts
    set_class = OrderedSet
    opts = None
    _declared_fields = {}
    _hooks = {}

    class Meta:
        """Options object for a Schema.

        Example usage: ::

            class Meta:
                fields = ("id", "email", "date_created")
                exclude = ("password", "secret_attribute")

        Available options:

        - ``fields``: Tuple or list of fields to include in the serialized result.
        - ``additional``: Tuple or list of fields to include *in addition* to the
            explicitly declared fields. ``additional`` and ``fields`` are
            mutually-exclusive options.
        - ``include``: Dictionary of additional fields to include in the schema. It is
            usually better to define fields as class variables, but you may need to
            use this option, e.g., if your fields are Python keywords. May be an
            `OrderedDict`.
        - ``exclude``: Tuple or list of fields to exclude in the serialized result.
            Nested fields can be represented with dot delimiters.
        - ``dateformat``: Default format for `Date <fields.Date>` fields.
        - ``datetimeformat``: Default format for `DateTime <fields.DateTime>` fields.
        - ``timeformat``: Default format for `Time <fields.Time>` fields.
        - ``render_module``: Module to use for `loads <Schema.loads>` and `dumps <Schema.dumps>`.
            Defaults to `json` from the standard library.
        - ``ordered``: If `True`, output of `Schema.dump` will be a `collections.OrderedDict`.
        - ``index_errors``: If `True`, errors dictionaries will include the index
            of invalid items in a collection.
        - ``load_only``: Tuple or list of fields to exclude from serialized results.
        - ``dump_only``: Tuple or list of fields to exclude from deserialization
        - ``unknown``: Whether to exclude, include, or raise an error for unknown
            fields in the data. Use `EXCLUDE`, `INCLUDE` or `RAISE`.
        - ``register``: Whether to register the `Schema` with marshmallow's internal
            class registry. Must be `True` if you intend to refer to this `Schema`
            by class name in `Nested` fields. Only set this to `False` when memory
            usage is critical. Defaults to `True`.
        """

    def __init__(self, *, only: types.StrSequenceOrSet | None=None, exclude: types.StrSequenceOrSet=(), many: bool=False, context: dict | None=None, load_only: types.StrSequenceOrSet=(), dump_only: types.StrSequenceOrSet=(), partial: bool | types.StrSequenceOrSet | None=None, unknown: str | None=None):
        if only is not None and (not is_collection(only)):
            raise StringNotCollectionError('"only" should be a list of strings')
        if not is_collection(exclude):
            raise StringNotCollectionError('"exclude" should be a list of strings')
        self.declared_fields = copy.deepcopy(self._declared_fields)
        self.many = many
        self.only = only
        self.exclude: set[typing.Any] | typing.MutableSet[typing.Any] = set(self.opts.exclude) | set(exclude)
        self.ordered = self.opts.ordered
        self.load_only = set(load_only) or set(self.opts.load_only)
        self.dump_only = set(dump_only) or set(self.opts.dump_only)
        self.partial = partial
        self.unknown = self.opts.unknown if unknown is None else validate_unknown_parameter_value(unknown)
        self.context = context or {}
        self._normalize_nested_options()
        self.fields = {}
        self.load_fields = {}
        self.dump_fields = {}
        self._init_fields()
        messages = {}
        messages.update(self._default_error_messages)
        for cls in reversed(self.__class__.__mro__):
            messages.update(getattr(cls, 'error_messages', {}))
        messages.update(self.error_messages or {})
        self.error_messages = messages

    def __repr__(self) -> str:
        return f'<{self.__class__.__name__}(many={self.many})>'

    @classmethod
    def from_dict(cls, fields: dict[str, ma_fields.Field | type], *, name: str='GeneratedSchema') -> type:
        """Generate a `Schema` class given a dictionary of fields.

        .. code-block:: python

            from marshmallow import Schema, fields

            PersonSchema = Schema.from_dict({"name": fields.Str()})
            print(PersonSchema().load({"name": "David"}))  # => {'name': 'David'}

        Generated schemas are not added to the class registry and therefore cannot
        be referred to by name in `Nested` fields.

        :param dict fields: Dictionary mapping field names to field instances.
        :param str name: Optional name for the class, which will appear in
            the ``repr`` for the class.

        .. versionadded:: 3.0.0
        """
        pass

    def handle_error(self, error: ValidationError, data: typing.Any, *, many: bool, **kwargs):
        """Custom error handler function for the schema.

        :param error: The `ValidationError` raised during (de)serialization.
        :param data: The original input data.
        :param many: Value of ``many`` on dump or load.
        :param partial: Value of ``partial`` on load.

        .. versionadded:: 2.0.0

        .. versionchanged:: 3.0.0rc9
            Receives `many` and `partial` (on deserialization) as keyword arguments.
        """
        pass

    def get_attribute(self, obj: typing.Any, attr: str, default: typing.Any):
        """Defines how to pull values from an object to serialize.

        .. versionadded:: 2.0.0

        .. versionchanged:: 3.0.0a1
            Changed position of ``obj`` and ``attr``.
        """
        pass

    @staticmethod
    def _call_and_store(getter_func, data, *, field_name, error_store, index=None):
        """Call ``getter_func`` with ``data`` as its argument, and store any `ValidationErrors`.

        :param callable getter_func: Function for getting the serialized/deserialized
            value from ``data``.
        :param data: The data passed to ``getter_func``.
        :param str field_name: Field name.
        :param int index: Index of the item being validated, if validating a collection,
            otherwise `None`.
        """
        pass

    def _serialize(self, obj: _T | typing.Iterable[_T], *, many: bool=False):
        """Serialize ``obj``.

        :param obj: The object(s) to serialize.
        :param bool many: `True` if ``data`` should be serialized as a collection.
        :return: A dictionary of the serialized data

        .. versionchanged:: 1.0.0
            Renamed from ``marshal``.
        """
        pass

    def dump(self, obj: typing.Any, *, many: bool | None=None):
        """Serialize an object to native Python data types according to this
        Schema's fields.

        :param obj: The object to serialize.
        :param many: Whether to serialize `obj` as a collection. If `None`, the value
            for `self.many` is used.
        :return: Serialized data

        .. versionadded:: 1.0.0
        .. versionchanged:: 3.0.0b7
            This method returns the serialized data rather than a ``(data, errors)`` duple.
            A :exc:`ValidationError <marshmallow.exceptions.ValidationError>` is raised
            if ``obj`` is invalid.
        .. versionchanged:: 3.0.0rc9
            Validation no longer occurs upon serialization.
        """
        pass

    def dumps(self, obj: typing.Any, *args, many: bool | None=None, **kwargs):
        """Same as :meth:`dump`, except return a JSON-encoded string.

        :param obj: The object to serialize.
        :param many: Whether to serialize `obj` as a collection. If `None`, the value
            for `self.many` is used.
        :return: A ``json`` string

        .. versionadded:: 1.0.0
        .. versionchanged:: 3.0.0b7
            This method returns the serialized data rather than a ``(data, errors)`` duple.
            A :exc:`ValidationError <marshmallow.exceptions.ValidationError>` is raised
            if ``obj`` is invalid.
        """
        pass

    def _deserialize(self, data: typing.Mapping[str, typing.Any] | typing.Iterable[typing.Mapping[str, typing.Any]], *, error_store: ErrorStore, many: bool=False, partial=None, unknown=RAISE, index=None) -> _T | list[_T]:
        """Deserialize ``data``.

        :param dict data: The data to deserialize.
        :param ErrorStore error_store: Structure to store errors.
        :param bool many: `True` if ``data`` should be deserialized as a collection.
        :param bool|tuple partial: Whether to ignore missing fields and not require
            any fields declared. Propagates down to ``Nested`` fields as well. If
            its value is an iterable, only missing fields listed in that iterable
            will be ignored. Use dot delimiters to specify nested fields.
        :param unknown: Whether to exclude, include, or raise an error for unknown
            fields in the data. Use `EXCLUDE`, `INCLUDE` or `RAISE`.
        :param int index: Index of the item being serialized (for storing errors) if
            serializing a collection, otherwise `None`.
        :return: A dictionary of the deserialized data.
        """
        pass

    def load(self, data: typing.Mapping[str, typing.Any] | typing.Iterable[typing.Mapping[str, typing.Any]], *, many: bool | None=None, partial: bool | types.StrSequenceOrSet | None=None, unknown: str | None=None):
        """Deserialize a data structure to an object defined by this Schema's fields.

        :param data: The data to deserialize.
        :param many: Whether to deserialize `data` as a collection. If `None`, the
            value for `self.many` is used.
        :param partial: Whether to ignore missing fields and not require
            any fields declared. Propagates down to ``Nested`` fields as well. If
            its value is an iterable, only missing fields listed in that iterable
            will be ignored. Use dot delimiters to specify nested fields.
        :param unknown: Whether to exclude, include, or raise an error for unknown
            fields in the data. Use `EXCLUDE`, `INCLUDE` or `RAISE`.
            If `None`, the value for `self.unknown` is used.
        :return: Deserialized data

        .. versionadded:: 1.0.0
        .. versionchanged:: 3.0.0b7
            This method returns the deserialized data rather than a ``(data, errors)`` duple.
            A :exc:`ValidationError <marshmallow.exceptions.ValidationError>` is raised
            if invalid data are passed.
        """
        pass

    def loads(self, json_data: str, *, many: bool | None=None, partial: bool | types.StrSequenceOrSet | None=None, unknown: str | None=None, **kwargs):
        """Same as :meth:`load`, except it takes a JSON string as input.

        :param json_data: A JSON string of the data to deserialize.
        :param many: Whether to deserialize `obj` as a collection. If `None`, the
            value for `self.many` is used.
        :param partial: Whether to ignore missing fields and not require
            any fields declared. Propagates down to ``Nested`` fields as well. If
            its value is an iterable, only missing fields listed in that iterable
            will be ignored. Use dot delimiters to specify nested fields.
        :param unknown: Whether to exclude, include, or raise an error for unknown
            fields in the data. Use `EXCLUDE`, `INCLUDE` or `RAISE`.
            If `None`, the value for `self.unknown` is used.
        :return: Deserialized data

        .. versionadded:: 1.0.0
        .. versionchanged:: 3.0.0b7
            This method returns the deserialized data rather than a ``(data, errors)`` duple.
            A :exc:`ValidationError <marshmallow.exceptions.ValidationError>` is raised
            if invalid data are passed.
        """
        pass

    def validate(self, data: typing.Mapping[str, typing.Any] | typing.Iterable[typing.Mapping[str, typing.Any]], *, many: bool | None=None, partial: bool | types.StrSequenceOrSet | None=None) -> dict[str, list[str]]:
        """Validate `data` against the schema, returning a dictionary of
        validation errors.

        :param data: The data to validate.
        :param many: Whether to validate `data` as a collection. If `None`, the
            value for `self.many` is used.
        :param partial: Whether to ignore missing fields and not require
            any fields declared. Propagates down to ``Nested`` fields as well. If
            its value is an iterable, only missing fields listed in that iterable
            will be ignored. Use dot delimiters to specify nested fields.
        :return: A dictionary of validation errors.

        .. versionadded:: 1.1.0
        """
        pass

    def _do_load(self, data: typing.Mapping[str, typing.Any] | typing.Iterable[typing.Mapping[str, typing.Any]], *, many: bool | None=None, partial: bool | types.StrSequenceOrSet | None=None, unknown: str | None=None, postprocess: bool=True):
        """Deserialize `data`, returning the deserialized result.
        This method is private API.

        :param data: The data to deserialize.
        :param many: Whether to deserialize `data` as a collection. If `None`, the
            value for `self.many` is used.
        :param partial: Whether to validate required fields. If its
            value is an iterable, only fields listed in that iterable will be
            ignored will be allowed missing. If `True`, all fields will be allowed missing.
            If `None`, the value for `self.partial` is used.
        :param unknown: Whether to exclude, include, or raise an error for unknown
            fields in the data. Use `EXCLUDE`, `INCLUDE` or `RAISE`.
            If `None`, the value for `self.unknown` is used.
        :param postprocess: Whether to run post_load methods..
        :return: Deserialized data
        """
        pass

    def _normalize_nested_options(self) -> None:
        """Apply then flatten nested schema options.
        This method is private API.
        """
        pass

    def __apply_nested_option(self, option_name, field_names, set_operation) -> None:
        """Apply nested options to nested fields"""
        pass

    def _init_fields(self) -> None:
        """Update self.fields, self.load_fields, and self.dump_fields based on schema options.
        This method is private API.
        """
        pass

    def on_bind_field(self, field_name: str, field_obj: ma_fields.Field) -> None:
        """Hook to modify a field when it is bound to the `Schema`.

        No-op by default.
        """
        pass

    def _bind_field(self, field_name: str, field_obj: ma_fields.Field) -> None:
        """Bind field to the schema, setting any necessary attributes on the
        field (e.g. parent and name).

        Also set field load_only and dump_only values if field_name was
        specified in ``class Meta``.
        """
        pass
BaseSchema = Schema