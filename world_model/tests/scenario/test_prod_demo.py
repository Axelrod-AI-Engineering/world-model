"""The production demo (Oct 8 restructure): the small demo's features, one for one, in the oil-shock world after its
history replay. Slow: it needs the oil world's init cache (about two minutes to build once)."""

from __future__ import annotations

import pytest

from axelrod_wm.sim.examples.prod import PROD
from axelrod_wm.sim.examples.session import run_examples
from axelrod_wm.sim.examples.small import SMALL


def test_the_two_catalogs_match_feature_for_feature():
    assert [(e.id, e.memory, e.feature) for e in PROD.examples] == [(e.id, e.memory, e.feature) for e in SMALL.examples]
    for ex in PROD.examples:
        if ex.kind == "event":
            assert ex.steps and all(st.ops in PROD.ops for st in ex.steps), ex.id
        if ex.kind == "edit":
            assert ex.edit in PROD.edits, ex.id
    for ev in PROD.library + SMALL.library:
        assert ev.step or ev.edit or ev.question, ev.id


@pytest.mark.slow
def test_every_feature_shows_in_the_busier_world():
    records, runner = run_examples("prod_demo")
    by = {r["example"].id: r for r in records}
    assert list(by) == [e.id for e in PROD.examples]
    ripple = by["ripple"]["review"]
    assert len(ripple.ripple) > 10 and max(a.order for a in ripple.ripple) >= 3
    assert by["analog"]["review"].recalled
    assert any("entity memory records a decision" in x for x in by["memory"]["review"].lessons)
    assert len(by["pending"]["review"].pending[0]["candidates"]) == 4        # three carriers and an open share
    assert sum(1 for it in by["pending"]["review"].items if it.hedge) == 3
    assert by["resolve"]["review"].kind == "refinement"
    assert by["resolve"]["review"].resolves["winner"]["id"] == "skybridge.operating_margin"
    assert by["superentity"]["review"].kind == "superentity_admission"
    assert by["frontier"]["review"].kind == "frontier_promotion"
    assert any("gains strength" in x for x in by["correlate"]["review"].lessons)
    assert by["retire_superentity"]["review"].kind == "superentity_dissolution"
    assert any("splits off" in x for x in by["split"]["review"].lessons)
    assert by["inference"]["forecast"]["based_on_version"] == by["inference"]["version_after"]
    from tests.scenario.test_small_demo import check_examples_show_what_their_articles_say

    assert not check_examples_show_what_their_articles_say(records, runner)


def test_every_sample_article_has_its_full_text():
    """Each example's and library event's article has a written-out version (articles.json) for the review pane, and
    it contains every phrase the translation quotes, so the same phrases are marked in it."""
    from axelrod_wm.sim.examples.catalog import full_text_of

    for cat in (SMALL, PROD):
        steps = [st for ex in cat.examples for st in ex.steps] + [ev.step for ev in cat.library if ev.step]
        for st in steps:
            text = full_text_of(st.article.headline)
            assert text, st.article.headline
            for phrase, _ops in st.article.quotes:
                assert phrase in text, (st.article.headline, phrase)
