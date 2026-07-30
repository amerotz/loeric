# This file is part of LOERIC.
#
# LOERIC is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# LOERIC is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
# See the GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with LOERIC. If not, see <https://www.gnu.org/licenses/>.


import json
import logging
import re
import typing
from dataclasses import dataclass

logger = logging.getLogger(__name__)


def readonly(attr: str):
    """Class decorator that makes a private attribute publicly readable but not writable.

    Generates a property named *attr* that reads from ``_{attr}`` and raises
    :exc:`AttributeError` on assignment.

    :param attr: the public attribute name to expose as readonly.
    :return: class decorator.
    """

    def decorator(cls):
        prop = property(
            lambda self: getattr(self, f"_{attr}"),
            lambda self, _: (_ for _ in ()).throw(
                AttributeError(f"'{type(self).__name__}.{attr}' is readonly")
            ),
        )
        prop.__doc__ = f"``{attr}`` is readonly and cannot be set at runtime."
        setattr(cls, attr, prop)
        return cls

    return decorator


def expose(private: str, public: str, validator=None):
    """Class decorator that creates a public property backed by a private attribute.

    The generated property reads from *private* and writes to it, with optional
    type coercion (inferred from the class's type hints) and value validation.
    A class may override the default getter or setter by defining ``_get_{public}``
    or ``_set_{public}`` methods respectively.

    :param private: name of the private backing attribute (e.g. ``'_samplerate'``).
    :param public: name of the generated property (e.g. ``'samplerate'``).
    :param validator: optional predicate ``(value) -> bool``. Raises :exc:`ValueError`
        if it returns ``False``.
    :return: class decorator.
    """

    def decorator(cls):
        def default_getter(self):
            return getattr(self, private)

        def default_setter(self, value):
            target_type = typing.get_type_hints(cls).get(private)

            if target_type is not None and not isinstance(value, target_type):
                try:
                    value = coerce(target_type, value)
                except Exception:
                    raise ValueError(f"Cannot coerce {value!r} to {target_type}")

            if validator is not None and not validator(value):
                raise ValueError(f"Invalid value {value!r} for '{public}'")

            setattr(self, private, value)

        # classes can expose _set_{attr} or _get_{attr} to override
        # default behaviour with properties, while still
        # allowing for decorators
        getter = getattr(cls, f"_get_{public}", default_getter)
        setter = getattr(cls, f"_set_{public}", default_setter)

        prop = property(getter, setter)
        prop.__doc__ = f"``{public}`` exposes ``{private}``."
        setattr(cls, public, prop)

        return cls

    return decorator


_INT_RE = re.compile(r"-?\d+")
_FLOAT_RE = re.compile(r"-?\d+(\.\d+)?")


def coerce(expected: type | None, value):
    """Coerce *value* to *expected* type using strict, explicit rules.

    Supports ``bool``, ``int``, ``float``, ``str``, ``list``, and ``dict``.
    String inputs are validated against literal patterns before conversion;
    no silent widening or narrowing between numeric types is performed.
    For ``list`` and ``dict``, JSON parsing is attempted on string inputs.
    Any other callable *expected* is invoked directly as a constructor.

    :param expected: the target type, or ``None`` to return *value* unchanged.
    :param value: the value to coerce.
    :return: *value* coerced to *expected*.
    :raises TypeError: if coercion is not possible or the value is not a valid literal.
    """
    if expected is None:
        return value

    # already correct type
    if isinstance(value, expected):
        return value

    try:
        if expected is bool:
            if value == "True":
                return True
            if value == "False":
                return False
            raise TypeError(
                f"Invalid bool literal {value!r} (expected 'True' or 'False')"
            )

        if expected is int:
            if isinstance(value, str):
                if not _INT_RE.fullmatch(value):
                    raise TypeError(f"Invalid int literal {value!r}")
                return int(value)
            raise TypeError(f"Cannot coerce {type(value).__name__} to int safely")

        if expected is float:
            if isinstance(value, str):
                if not _FLOAT_RE.fullmatch(value):
                    raise TypeError(f"Invalid float literal {value!r}")
                return float(value)
            raise TypeError(f"Cannot coerce {type(value).__name__} to float safely")

        if expected is str:
            if isinstance(value, str):
                return value
            raise TypeError(f"Cannot coerce {type(value).__name__} to str safely")

        if expected is list:
            return _parse_list(value)

        if expected is dict:
            if isinstance(value, dict):
                return value
            if isinstance(value, str):
                try:
                    parsed = json.loads(value)
                    if not isinstance(parsed, dict):
                        raise TypeError("JSON did not decode to dict")
                    return parsed
                except json.JSONDecodeError as e:
                    raise TypeError(f"Invalid JSON dict: {value!r}") from e

            raise TypeError(f"Cannot coerce {type(value).__name__} to dict safely")

        if callable(expected):
            return expected(value)

        raise TypeError(f"Unsupported coercion target: {expected}")

    except TypeError:
        raise
    except Exception as e:
        raise TypeError(
            f"Cannot coerce {value!r} ({type(value).__name__}) to {expected}"
        ) from e


def _parse_list(value):
    """Parse *value* into a Python list.

    Accepts an existing list (returned as-is) or a JSON-encoded string.

    :param value: a ``list`` or JSON string representing a list.
    :return: a Python ``list``.
    :raises TypeError: if *value* is not a list or a valid JSON list string.
    """
    if isinstance(value, list):
        return value

    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as e:
            raise TypeError(f"Invalid JSON list: {value!r}") from e

        if not isinstance(parsed, list):
            raise TypeError(f"JSON did not decode to list: {value!r}")

        return parsed

    raise TypeError(f"Cannot coerce {type(value).__name__} to list")


@dataclass(frozen=True)
class LOERICPath:
    """Immutable dot-free path into a nested structure of objects, dicts, and lists.

    Segments are separated by ``/``. Each segment is resolved in order against
    the current node via attribute access, dict key lookup, or integer index,
    making the path syntax uniform across heterogeneous nested structures.

    Example: ``'player/input/mic_input/analysers/loudness/responsiveness'``
    """

    path: str

    @property
    def parts(self) -> list[str]:
        """Path segments split on ``/``.

        :return: list of segment strings.
        """
        return self.path.split("/")

    @property
    def top(self) -> str:
        """First path segment (the root key).

        :return: the leading segment string.
        """
        return self.parts[0]

    @property
    def tail(self) -> "LOERICPath":
        """Path with the first segment removed.

        :return: a new :class:`LOERICPath` starting from the second segment.
        """
        return LOERICPath("/".join(self.parts[1:]))

    @staticmethod
    def _resolve(obj, key: str):
        """Resolve a single path segment *key* against *obj*.

        Tries in order:

        1. Attribute access via :func:`getattr` (objects, namespaces).
        2. Dict key lookup (config dicts).
        3. Integer index (lists and tuples).

        :param obj: the object to resolve against.
        :param key: the segment to resolve.
        :return: the child node.
        :raises AttributeError: if none of the three strategies succeed.
        """
        if hasattr(obj, key):
            return getattr(obj, key)
        if isinstance(obj, dict):
            if key in obj:
                return obj[key]
        if isinstance(obj, (list, tuple)):
            try:
                return obj[int(key)]
            except (ValueError, IndexError):
                pass
        raise AttributeError(f"Cannot resolve '{key}' on {type(obj).__name__}")

    @staticmethod
    def _assign(obj, key: str, value) -> bool:
        """Assign *value* to the child identified by *key* on *obj*.

        Checks type consistency against the container's type hint before assigning.
        Tries list/tuple index, then dict key, then :func:`setattr`.

        :param obj: the parent object.
        :param key: the attribute name, dict key, or list index (as string).
        :param value: the value to assign.
        :return: ``True`` on success, ``False`` if the key was not found,
            the index was out of range, or the value failed the type check.
        """
        # check type consistency based on hints
        expected = LOERICPath._container_type(obj, key)
        if expected and not isinstance(value, expected):
            logger.warning(
                f"Cannot set attribute {key} of {obj} (obtained type {type(value)}, expected {expected}"
            )
            return False
        if isinstance(obj, (list, tuple)):
            try:
                obj[int(key)] = value
                return True
            except (ValueError, IndexError):
                return False
        if isinstance(obj, dict):
            if key in obj:
                obj[key] = value
                return True
        if hasattr(obj, key):
            setattr(obj, key, value)
            return True
        return False

    def _container_type(obj, key: str) -> type | None:
        """Infer the expected value type for *key* on *obj* from type hints.

        For generic containers such as ``dict[str, OutputInterface]``, returns
        the last type argument (the value type). For plain annotations, returns
        the annotation directly.

        :param obj: the parent object.
        :param key: the attribute or key name to look up.
        :return: the expected type, or ``None`` if no hint is present.
        """
        hints = typing.get_type_hints(type(obj))
        if key not in hints:
            return None
        hint = hints[key]
        # e.g. dict[str, OutputInterface] -> (str, OutputInterface)
        args = typing.get_args(hint)
        return args[-1] if args else hint

    @staticmethod
    def get(obj, path: "LOERICPath"):
        """Retrieve the value at *path* starting from *obj*.

        :param obj: the root object to traverse from.
        :param path: the :class:`LOERICPath` to follow.
        :return: the value at the end of the path, or ``None`` if any segment
            could not be resolved.
        """
        try:
            for key in path.parts:
                obj = LOERICPath._resolve(obj, key)
            return obj
        except AttributeError as exc:
            logger.warning(f"get failed at '{path.path}': {exc}")
            return None

    @staticmethod
    def set(obj, path: "LOERICPath", value) -> bool:
        """Set the value at *path* starting from *obj*.

        Traverses all but the last segment via :meth:`_resolve`, then calls
        :meth:`_assign` on the leaf.

        :param obj: the root object to traverse from.
        :param path: the :class:`LOERICPath` identifying the target.
        :param value: the value to assign.
        :return: ``True`` on success, ``False`` if traversal or assignment failed.
        """
        parts = path.parts
        try:
            for key in parts[:-1]:
                obj = LOERICPath._resolve(obj, key)
        except AttributeError as exc:
            logger.warning(f"set failed traversing '{path.path}': {exc}")
            return False

        ok = LOERICPath._assign(obj, parts[-1], value)
        if ok:
            logger.info(f"Set '{path.path}' to {value!r}")
        else:
            logger.warning(f"Could not set '{path.path}' to {value!r}")
        return ok
