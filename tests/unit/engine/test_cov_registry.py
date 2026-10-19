"""Registries: interface checks, lookup errors, and late interfaces."""

from __future__ import annotations

import pytest

from axelrod_wm.engine.registry import REGISTRIES, Registry, register, registry


class Iface:
    pass


def test_register_rejects_a_class_without_the_interface():
    reg = Registry("_cov", Iface)

    class Other:
        pass

    with pytest.raises(TypeError, match="Other does not implement Iface for slot _cov"):
        reg.register("other")(Other)

    @reg.register("ok")
    class Ok(Iface):
        def __init__(self, n: int = 1) -> None:
            self.n = n

    assert (Ok.registered_name, Ok.registered_slot) == ("ok", "_cov")
    assert reg.create("ok", n=3).n == 3


def test_get_names_the_known_components():
    reg = Registry("_cov")
    with pytest.raises(KeyError, match=r"slot '_cov' has no component named 'x'; known: \(none\)"):
        reg.get("x")
    reg.register("b")(type("B", (), {}))
    reg.register("a")(type("A", (), {}))
    with pytest.raises(KeyError, match="known: a, b"):
        reg.get("x")


def test_registry_adds_an_interface_later_but_never_replaces_one():
    try:
        reg = registry("_cov_late")
        assert reg.interface is None
        assert registry("_cov_late", Iface) is reg and reg.interface is Iface
        assert registry("_cov_late", object).interface is Iface
        register("_cov_late", "x")(type("X", (Iface,), {}))
        assert reg.names() == ["x"]
    finally:
        REGISTRIES.pop("_cov_late", None)
