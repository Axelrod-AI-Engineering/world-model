"""Precision rules (Oct 18), each with invented sentences and tables: an observation is a reported current level,
a move is a reported change or a revision, and neither comes from a forecast, guidance, a scenario, an earlier
episode, another actor's figure, a part taken for the whole, or a figure on another basis."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from axelrod_wm.ingest.extract import Reading, Rules, _aim, _modelled, _part, claims_of_chunk
from axelrod_wm.ingest.tables import header_of

OCT = datetime(2026, 10, 5, tzinfo=UTC)


def read(rules: Rules, text: str, **reading) -> list[tuple]:
    claims, _ = claims_of_chunk(rules, 0, text, Reading(**reading))
    out = []
    for f in claims.found:
        if f.type == "observe":
            out.append(("observe", f.value_of, round(f.value, 4)))
        elif f.type == "move":
            out.append(("move", f.value_of, round(f.delta, 4), f.mode))
        else:
            out.append((f.type, f.source, f.target))
    return out


def moves(rules: Rules, text: str, **reading) -> list[tuple]:
    return [s for s in read(rules, text, **reading) if s[0] in ("observe", "move")]


# -- forecasts are not observations ----------------------------------------------------------------------------------------
@pytest.mark.parametrize("text,reading", [
    ("Delta net interest income is seen up 4% y/y.", {}),                                   # a preview
    ("Credit spreads preview: a 25bp central bank rate hike incoming", {}),
    ("Core inflation is projected to accelerate.", {}),                               # a projection
    ("Our base case is a further central bank rate hike, taking the policy rate to 4.50%.", {}),
    ("Markets are pricing in four central bank rate hikes of 25bp.", {}),             # the market's pricing
    ("Guidance based on a policy rate of 4.00%.", {}),                                # an assumption
    ("Management expects Delta markets revenue up mid-single digits.", {}),            # another's expectation
    ("Others have guided to lower M&A.", {}),
    ("There should be a coming acceleration of M&A.", {}),
    ("Ridge Energy operating profit will grow by 10%.", {}),                                 # a prediction
    ("Industrial output over FY26-28E is 0.5% higher.", {}),                          # a change over estimated years
    ("We see a downward bias to our GDP growth forecast.", {}),                       # the forecast's direction
])
def test_previews_and_predictions_claim_nothing(rules, text, reading):
    assert moves(rules, text, date=OCT, **reading) == []


@pytest.mark.parametrize("text,want", [
    # a revision of a forecast or of guidance is news
    ("Acme Bank raised its NII guidance to $105.5bn from $103bn.",
     ("move", "acme_bank.net_interest_income", 0.0243, "relative")),
    ("We raised our Delta NII forecasts.", ("move", "delta_bank.net_interest_income", 0.5, "standardized")),
    # what is said around a mention, not past it, frames it
    ("Following the September hike, the central bank raised rates 25bp; markets are pricing in more hikes.",
     ("move", "central_bank.policy_rate", 0.25, "absolute")),
    ("Ridge Energy operating profit rose 5% and will increasingly depend on pumped volumes.",
     ("move", "ridge_energy.operating_profit", 0.05, "relative")),
])
def test_revisions_and_reports_still_count(rules, text, want):
    assert want in moves(rules, text, date=OCT)


def test_the_part_of_a_sentence_that_frames_a_mention():
    text = "NII rose 5%; we expect more\no At the meeting, mgmt guided higher"
    assert _part(text, 0, 3) == "NII rose 5%;"[:3] + " rose 5%"
    assert _part(text, text.index("mgmt"), text.index("mgmt") + 4) == "At the meeting, mgmt guided higher"


# -- tables: the latest actual column ---------------------------------------------------------------------------------
def test_a_year_end_level_before_a_later_quarter_is_history(rules):
    assert read(rules, "Delta CET1 ratio (%) 14.7 15.0", header=header_of("12/25 12/26E"), date=OCT) == []


def test_a_market_price_is_read_on_a_date_not_at_a_period_end(rules):
    assert read(rules, "Dollar index 104.1 105.3", header=header_of("2Q26 3Q26"), date=OCT) == []
    assert read(rules, "Dollar index 104.1 105.3", header=header_of("30 Sep 1 Oct"), date=OCT) == [
        ("observe", "dollar.index", 105.3)]


QUARTERS = header_of("USD |  | FY2025 | Q1-2026 | Q2-2026 | Q3-2026 | Q4-2026 | FY2026")


def test_a_model_completes_a_year_half_reported_with_less_confidence(rules):
    row = "Net Interest Income, mm |  | 95000 | 25000 | 26000 | 27000.5 | 28000.5 | 106001.0"
    claims, _ = claims_of_chunk(rules, 0, row, Reading(subject="acme_bank", header=QUARTERS, date=OCT))
    assert [(f.value_of, round(f.value, 3), f.confidence) for f in claims.found] == [
        ("acme_bank.net_interest_income", 106.001, 0.7)]


def test_a_model_completes_a_year_only_one_quarter_in(rules):
    row = "Net Interest Income, mm |  | 90000 | 95000 | 25000 | 26000.5 | 27000.5 | 28000.5 | 106001.5"
    header = header_of("USD |  | FY2024 | FY2025 | Q1-2026 | Q2-2026 | Q3-2026 | Q4-2026 | FY2026")
    assert read(rules, row, subject="acme_bank", header=header, date=OCT) == []


@pytest.mark.parametrize("row", [
    "Net Interest Income on IS = NII on CF, mm |  | 1 | 0 | -1 | 0 | 0 | 0",                # a model's check
    "Net Interest Income, mm |  | 0 | 0 | 0 | 0 | 0 | 0",                                    # a row of zeros
    "Net Interest Income, mm |  | 95000 | 25000 | 26000 | 27000 | 104000 | 104000",          # a balance: FY = Q4
    "Net Interest Income mix, % |  | 0.25 | 0.26 | 0.27 | 0.28 | 0.29 | 0.3",                 # a share of the value
    "Net income (incl. net interest income), mm |  | 95000 | 25000 | 26000 | 27000 | 28000 | 106000",
])
def test_sheet_rows_that_are_no_current_level(rules, row):
    assert read(rules, row, subject="acme_bank", header=QUARTERS, date=OCT) == []


def test_a_cumulative_row_reads_its_year(rules):
    row = "Cumulative Net Interest Income, mm |  | 95000 | 25000 | 51000 | 77000 | 103000 | 103000"
    assert read(rules, row, subject="acme_bank", header=QUARTERS, date=OCT) == [
        ("observe", "acme_bank.net_interest_income", 103.0)]


def test_a_level_whose_figures_run_past_the_dated_columns(rules):
    row = "Common Equity Tier 1 Capital Ratio, % |  | 0.1428 | 0.1419 | 0.1500 | 0.1510"
    assert read(rules, row, subject="acme_bank", header=header_of("USD |  | Q1-2026 | Q2-2026"), date=OCT) == []


def test_modelled_columns():
    assert _modelled(["NII", "1", "2", "3", "4.5", "6"], 0) == 4
    assert _modelled(["CET1", "0.1", "0.2", "0.3"], 0) == 4           # decimals throughout: a ratio
    assert _modelled(["NII", "1", "2.5", "x"], 0) == 4                # too few whole figures before


def test_side_by_side_blocks_of_the_same_periods(rules):
    row = "Delta net interest income 14.8 15.7 14.9 15.8 1% 1%"
    assert read(rules, row, header=header_of("2026E 2027E 2026E 2027E"), date=OCT) == []


# -- wrong value or entity ---------------------------------------------------------------------------------------------------
def test_a_part_in_a_mixed_list_is_not_the_whole(rules):
    text = "Equity vol (VIX -12%) fell, while credit volatility (MOVE +6%) rose."
    assert not [s for s in moves(rules, text) if s[1] == "capital_markets.market_volatility"]
    text = "MOVE (+6%) and OVX (+8%) rose."                                 # parts that moved one way
    m = next(x for x in rules.gz.find(text) if x.subentity_id)
    assert not rules._component(text, m)


@pytest.mark.parametrize("text", [
    "KEY FY26 NII up 9-11%.",                                    # another bank's line, by its ticker
    "The BCB lowered NII by 2%.",                                # another actor the model does not know
])
def test_a_value_after_an_unknown_actor_is_not_the_subject(rules, text):
    assert moves(rules, text, subject="acme_bank") == []


def test_a_known_acronym_is_no_other_actor(rules):
    assert moves(rules, "FY26 NII up 9%.", subject="acme_bank") == [
        ("move", "acme_bank.net_interest_income", 0.09, "relative")]


def test_its_after_a_stranger_is_the_stranger(rules):
    text = "Orchid's share price lagged. However, its share price rebounded."
    assert moves(rules, text, subject="blue_freight") == []
    assert moves(rules, "Prices lagged. However, its share price rebounded.", subject="blue_freight") == [
        ("move", "blue_freight.share_price", 0.5, "standardized")]


def test_another_basis_and_aims(rules):
    assert moves(rules, "Stripping out subsidies, core inflation was 2.3% y/y.") == []
    assert moves(rules, "Buybacks (up to $220bn) to improve Acme Re shareholder returns.") == []
    assert _aim("committed to reducing ") and not _aim("voted to raise the ") and not _aim("the Board to raise ")


# -- quarters, months, and pauses ------------------------------------------------------------------------------------------
@pytest.mark.parametrize("text", [
    "Relative to 2Q26, Delta net interest income is down 2%.",              # a quarter's sequential change
    "Core inflation rose 0.3% in August.",                                 # a month's print
    "Core inflation rose sequentially.",
    "Core inflation rose 1% m/m.",
    "The central bank rate cuts are on hold, unchanged since May.",        # a pause
])
def test_sequential_monthly_and_paused_are_no_moves(rules, text):
    assert [s for s in moves(rules, text) if s[0] == "move"] == []


def test_a_year_on_year_change_against_a_quarter_still_counts(rules):
    assert ("move", "delta_bank.net_interest_income", 0.18, "relative") in moves(
        rules, "Delta net interest income rose 18% y/y vs. 2Q26.")


def test_a_flow_after_its_change_is_a_period_unless_the_year_is_named(rules):
    text = "Acme Re domestic life adjusted net income rose 16% to $72bn after the March 2026 deal."
    assert moves(rules, text) == [("move", "acme_re.domestic_life_profit", 0.16, "relative")]
    text = "For the full year, Acme Re domestic life adjusted net income rose 16% to $72bn."
    assert ("observe", "acme_re.domestic_life_profit", 72.0) in moves(rules, text)


# -- scenarios and episodes ------------------------------------------------------------------------------------------------
def test_a_scenarios_bullets_are_supposed_until_prose_resumes(rules):
    text = ("Upside Scenario,\n$80, +42%\n• GDP growth stronger than expected\n"
            "The central bank raised rates by 25bp in September.")
    assert moves(rules, text, date=OCT) == [("move", "central_bank.policy_rate", 0.25, "absolute")]


def test_an_episode_dated_by_day_and_month_after_an_earlier_year(rules):
    text = ("The 2024 euro shock was sharp. As the government bonds 10Y yield rose 10bp between 30 July and 5 August, "
            "US equities fell 16%.")
    assert moves(rules, text, date=OCT) == []
    assert ("support", "gov_bonds.yield_10y", "capital_markets.equity_index") in read(rules, text, date=OCT)
    text = "The euro rose 10% between 30 July and 5 August."          # an inverted surface: the dollar index fell
    assert moves(rules, text, date=OCT) == [("move", "dollar.index", -0.1, "relative")]


def test_past_episodes_are_history(rules):
    assert moves(rules, "Across past episodes of euro strength, the euro appreciated by 25%.") == []


def test_an_estimated_end_of_a_channel_is_no_move(rules):
    text = "We est. slightly higher NII in 4Q due to higher central bank policy rates."
    assert moves(rules, text, subject="acme_bank") == []


def test_an_uncalibrated_link_has_its_mechanism_sign(rules):
    assert ("support", "acme_re.cross_holding_sales", "acme_re.cross_holding_book") in read(
        rules, "Acme Re is reducing business-related equities.")
