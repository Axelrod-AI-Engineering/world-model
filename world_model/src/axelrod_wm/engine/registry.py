"""Slots and registries (§8.1).

Every pluggable step is a slot with an abstract interface, a default implementation, and
optional alternatives, each registered under a name.
"""

from __future__ import annotations

from typing import Any, Callable, Generic, TypeVar

T = TypeVar("T")


class Registry(Generic[T]):
    def __init__(self, slot: str, interface: type | None = None) -> None:
        self.slot = slot
        self.interface = interface
        self._items: dict[str, type] = {}

    def register(self, name: str) -> Callable[[type], type]:
        def deco(cls: type) -> type:
            if self.interface is not None and not issubclass(cls, self.interface):
                raise TypeError(f"{cls.__name__} does not implement {self.interface.__name__} for slot {self.slot}")
            self._items[name] = cls
            cls.registered_name = name  # type: ignore[attr-defined]
            cls.registered_slot = self.slot  # type: ignore[attr-defined]
            return cls

        return deco

    def get(self, name: str) -> type:
        try:
            return self._items[name]
        except KeyError:
            raise KeyError(f"slot {self.slot!r} has no component named {name!r}; "
                           f"known: {', '.join(self.names()) or '(none)'}") from None

    def create(self, name: str, **kwargs: Any) -> T:
        return self.get(name)(**kwargs)

    def names(self) -> list[str]:
        return sorted(self._items)


REGISTRIES: dict[str, Registry[Any]] = {}


def registry(slot: str, interface: type | None = None) -> Registry[Any]:
    reg = REGISTRIES.get(slot)
    if reg is None:
        reg = REGISTRIES[slot] = Registry(slot, interface)
    elif interface is not None and reg.interface is None:
        reg.interface = interface
    return reg


def register(slot: str, name: str) -> Callable[[type], type]:
    """Class decorator, e.g. @register("unifier", "channels_and_rivals")."""
    return registry(slot).register(name)
