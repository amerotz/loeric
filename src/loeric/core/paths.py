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


import logging
import typing
from dataclasses import dataclass

logger = logging.getLogger(__name__)


def readonly(attr: str):
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
    def decorator(cls):
        def getter(self):
            return getattr(self, private)

        def setter(self, value):
            if validator is not None and not validator(value):
                raise ValueError(f"Invalid value {value!r} for '{public}'")
            setattr(self, private, value)

        prop = property(getter, setter)
        prop.__doc__ = f"``{public}`` exposes ``{private}``."
        setattr(cls, public, prop)
        return cls

    return decorator


@dataclass(frozen=True)
class LOERICPath:
    path: str

    @property
    def parts(self) -> list[str]:
        return self.path.split("/")

    @property
    def top(self) -> str:
        return self.parts[0]

    @property
    def tail(self) -> "LOERICPath":
        return LOERICPath("/".join(self.parts[1:]))

    @staticmethod
    def _resolve(obj, key: str):
        """Resolve one path segment against *obj*.

        Tries, in order:
          1. attribute access  (object / namespace)
          2. dict key          (config dicts)
          3. integer index     (lists)

        Raises ``AttributeError`` if none succeeds.
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
        """Assign *value* to the leaf node identified by *key* on *obj*."""
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
        hints = typing.get_type_hints(type(obj))
        if key not in hints:
            return None
        hint = hints[key]
        # e.g. dict[str, OutputInterface] -> (str, OutputInterface)
        args = typing.get_args(hint)
        return args[-1] if args else hint

    @staticmethod
    def get(obj, path: "LOERICPath"):
        """Return the value at *path* starting from *obj*, or ``None``."""
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

        Returns ``True`` on success, ``False`` otherwise.
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
