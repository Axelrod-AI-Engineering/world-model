"""The repair fixtures of Fixes 7 to 14 (hypothetical inputs only, not Toyota figures)."""

import pytest

from axelrod_wm.model.period_math import (
    DisruptionPeriod,
    average_exposed_share_uniform,
    buyback_capacity,
    delta_nii,
    disruption,
    elimination_roll,
    hybrid_mix_op,
    liquidity_close,
    matched_share,
    npv,
    operating_years_needed,
    payback_years,
    pricing_by_period,
    project_cash_flows,
    translate,
)


def test_hybrid_fixture():
    assert hybrid_mix_op(10_000, 0, spread=50_000) == 500_000_000
    assert hybrid_mix_op(10_000, 0, spread=0) == 0


def test_pricing_delay():
    apr = pricing_by_period(120, 60, 0.0)
    octo = pricing_by_period(120, 60, 0.5)
    assert apr.recovery_in_year == pytest.approx(60) and octo.recovery_in_year == pytest.approx(30)
    assert apr.cost_in_year == octo.cost_in_year == pytest.approx(120)
    assert octo.net_op == pytest.approx(-90) and octo.recovery_next_year_if_persisting == 60
    emb = pricing_by_period(120, 60, 0.0, baseline_recovery_in_year=60)
    assert emb.net_op == pytest.approx(-120)            # the embedded recovery is not added a second time
    with pytest.raises(ValueError):
        pricing_by_period(120, 60, 0.0, cost_weights=(0.5, 0.5, 0.5, 0.5))


def test_financing():
    r = delta_nii(10_000.0, 1.0, 6_000.0, 1.0, 1.0)  # +100 income, +60 expense (millions)
    assert r["delta_nii"] == pytest.approx(40.0)
    assert delta_nii(0, 1.0, 0, 1.0, 1.0)["delta_nii"] == 0
    assert average_exposed_share_uniform(0.3) == pytest.approx(0.15)


def test_translation_signs():
    assert translate(1.0, 160) == pytest.approx(0.160) and translate(1.0, 145) == pytest.approx(0.145)
    assert translate(-1.0, 160) == pytest.approx(-0.160) and translate(-1.0, 145) == pytest.approx(-0.145)


def test_disruption():
    with_buf = disruption(30_000, [DisruptionPeriod("Jan-Mar", 80_000), DisruptionPeriod("Apr-Jun", 0, catch_up_deliveries=20_000)])
    assert with_buf[0]["delivery_shortfall"] == 50_000 and with_buf[1]["cumulative_shortfall"] == 30_000 and with_buf[1]["lost_cumulative"] == 0
    no_buf = disruption(0, [DisruptionPeriod("Jan-Mar", 80_000), DisruptionPeriod("Apr-Jun", 0, catch_up_deliveries=20_000)])
    assert no_buf[0]["delivery_shortfall"] == 80_000 and no_buf[1]["cumulative_shortfall"] == 60_000
    assert all(p["stock_close"] >= 0 for p in with_buf + no_buf)
    assert elimination_roll(10, 5, 8) == 7


def test_matched_share():
    m = matched_share(100, 72, 100, 66, 0.10)
    assert m["company_unit_growth"] == pytest.approx(-0.28) and m["relative_share_change"] == pytest.approx(0.090909, abs=1e-6)
    assert m["closing_share"] == pytest.approx(0.109091, abs=1e-6) and m["change_pp"] == pytest.approx(0.9091, abs=1e-4)
    assert m["growth_difference_shortcut"] == pytest.approx(-0.28 + 0.34)


def test_sourcing():
    assert payback_years(200, 60, 20) == pytest.approx(5)
    assert operating_years_needed(200, 60, 20) == pytest.approx(5) and payback_years(200, 60, 20, 2) == pytest.approx(7)
    now = npv(project_cash_flows(200, 60, 20, 0, 10), 0.08)
    late = npv(project_cash_flows(200, 60, 20, 2, 10), 0.08)
    assert late < now


def test_cash():
    assert liquidity_close(15, 4.5, 2.3, 0, 1.2, 0.5) == pytest.approx(15.5)
    assert liquidity_close(15, 4.5, 2.3, 0, 1.2, 0.5, collection_delay=1.0) == pytest.approx(14.5)
    assert liquidity_close(15, 4.5, 2.3, 0, 1.2, 0.0, collection_delay=1.0) == pytest.approx(15.0)
    cap = buyback_capacity(1.0, 0.1, 5.0, 14.5 - 15.0)
    assert cap["permitted_spend"] == 0.0 and cap["binding"] == "eligible_headroom"
