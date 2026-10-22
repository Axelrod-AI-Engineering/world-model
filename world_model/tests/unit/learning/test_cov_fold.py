"""The folder's interface: a subclass that defers to it gets no result."""

from __future__ import annotations

from axelrod_wm.learning.fold import Folder


def test_the_abstract_fold_returns_nothing():
    class Deferring(Folder):
        def fold(self, parsed, analysis, wm, ctx, txn):
            return super().fold(parsed, analysis, wm, ctx, txn)

    assert Deferring().fold(None, None, None, None, None) is None
