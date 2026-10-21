"""Reading rules, each with invented sentences: what a careful reader takes from a sentence, a table row, or a
channel, and what it leaves alone (targets, forecasts of market levels, history, hypotheticals, other companies)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from axelrod_wm.ingest.extract import (
    ChunkClaims,
    Found,
    Reading,
    Rules,
    _dates_in,
    _heading,
    _labelled_parens,
    _licensed,
    _unit_scale,
    claims_of_chunk,
    keep_best,
    numbers,
)
from axelrod_wm.ingest.tables import header_of

OCT = datetime(2026, 10, 5, tzinfo=UTC)


def read(rules: Rules, text: str, **reading) -> list[tuple]:
    """(type, value or ends, level or delta, mode) for each signal the rules find in `text`."""
    claims, _ = claims_of_chunk(rules, 0, text, Reading(**reading))
    out = []
    for f in claims.found:
        assert f.quote in text
        if f.type == "observe":
            out.append(("observe", f.value_of, round(f.value, 4)))
        elif f.type == "move":
            out.append(("move", f.value_of, round(f.delta, 4), f.mode))
        else:
            out.append((f.type, f.source, f.target))
    return out


# -- numbers --------------------------------------------------------------------------------------------------------------
def nums(text: str) -> list[tuple]:
    return [(round(n.value, 4), n.unit, n.currency, n.scale, n.range) for n in numbers(text)]


@pytest.mark.parametrize("text,want", [
    ("EUR 84.50", [(84.5, "", "€", 1.0, False)]),
    ("240 JPY", [(240.0, "", "¥", 1.0, False)]),
    ("US$1.5bn", [(1.5, "", "$", 1e9, False)]),
    ("CNY 11.06", [(11.06, "", "CNY", 1.0, False)]),
    ("3.75-4.0%", [(3.875, "%", "", 1.0, True)]),
    ("5-10bp", [(7.5, "bp", "", 1.0, True)]),
    ("$4.06-4.16b", [(4.11, "", "$", 1e9, True)]),
    ("a 10-basis-point cut", [(10.0, "bp", "", 1.0, False)]),
    ("¥8.2tr and 5 tr", [(8.2, "", "¥", 1e12, False), (5.0, "", "", 1.0, False)]),
    ("$6.4b", [(6.4, "", "$", 1e9, False)]),
    ("FY26 and EUR/GBP", []),                              # figures inside words are not numbers
    ("9-5 split", [(9.0, "", "", 1.0, False), (5.0, "", "", 1.0, False)]),   # a falling pair is no range
    ("$5-€9", [(5.0, "", "$", 1.0, False), (9.0, "", "€", 1.0, False)]),     # nor two currencies
])
def test_numbers(text, want):
    assert nums(text) == want


def test_unit_scale():
    assert _unit_scale("m units/yr") == 1e6 and _unit_scale("CNY bn/yr") == 1e9 and _unit_scale("¥tn/yr") == 1e12
    assert _unit_scale("index") == 1.0


# -- helpers --------------------------------------------------------------------------------------------------------------
def test_dates_in():
    assert _dates_in("on 31-Jul-2026, as of Sep. 18, 2026, and 9 Jan 24") == [
        datetime(2026, 9, 18, tzinfo=UTC), datetime(2026, 7, 31, tzinfo=UTC), datetime(2024, 1, 9, tzinfo=UTC)]


def test_licensed_infinitives():
    assert _licensed("is expected to rise") == "is expected to rise"
    assert _licensed(" to rise") == " to rise"                         # right after the value: its own
    assert _licensed("the ACB to raise") == "the ACB to raise"
    assert _licensed("(ACB) to raise") == "(ACB) to raise"
    assert _licensed("its portfolio to reduce") == "its portfolio "


def test_heading_and_labelled_parens():
    assert _heading("Crude Oil Rises Sharply Today") and not _heading("Crude oil rose today")
    assert not _heading("Oil Up")
    s = "Volatility jumped (VIX +12%) and fell (-3%)."
    assert _labelled_parens(s, 0, s.index("+12")) and not _labelled_parens(s, 0, s.index("-3"))
    assert not _labelled_parens(s, 0, 5)


# -- levels and moves -------------------------------------------------------------------------------------------------------
def test_a_target_is_not_the_value(rules):
    assert read(rules, "Ridge Energy share price target raised to $60.") == []
    assert read(rules, "The Acme 10Y yield target is 4.8%.") == []
    # though a forecaster's revised target for a rate moves its view of the rate
    assert read(rules, "We revise our Acme 10Y yield target from 4.35% to 4.80%.") == [
        ("move", "gov_bonds.yield_10y", 0.45, "absolute")]


@pytest.mark.parametrize("text", [
    "In 2024 crude oil rose 10%.",                         # only earlier years: history
    "Historically, crude oil rose in winter.",
    "Will crude oil rise?",
    "Freight borrowing rose sharply.",                     # the value's name modifies another measure
    "Global implied volatility rose.",                     # a value named without its entity, after another noun
    "Global equity market volatility rose.",
    "Acme interest rates rose.",                           # the rate environment: a cause, never a move
    "Revenue of 500 bn dollars fell.",                     # a currency's name as a unit
    "Crude oil, we think, moved from $90 to $95.",
    "Crude oil may rise.",
])
def test_no_claim(rules, text):
    assert read(rules, text, date=OCT) == []


def test_policy_rates_by_the_documents_region_are_for_channels_only(rules):
    assert read(rules, "Policy rates rose.", region="US") == []


def test_sector_wide_figures_belong_to_no_one_company(rules):
    assert read(rules, "We raised our NII forecasts for select banks.", subject="harvest_bank") == []
    assert read(rules, "We raised our NII forecasts.", subject="harvest_bank") == [
        ("move", "harvest_bank.net_interest_income", 0.5, "standardized")]


def test_a_value_named_with_its_own_word_is_not_modified(rules):
    assert read(rules, "Acme GDP growth slowed to 1.2%.") == [("observe", "economy.gdp_growth", 1.2)]


@pytest.mark.parametrize("text,want", [
    ("We cut our Ridge Energy operating profit forecast to $5.5bn from $6.0bn.",
     ("move", "ridge_energy.operating_profit", -0.0833, "relative")),
    ("Ridge Energy operating profit was revised from $6bn to $6.5bn.", ("move", "ridge_energy.operating_profit", 0.0833,
                                                                      "relative")),
    ("The Acme 10Y yield target was cut to 4.2% (from 4.5%).", ("move", "gov_bonds.yield_10y", -0.3, "absolute")),
])
def test_revisions(rules, text, want):
    assert read(rules, text) == [want]


@pytest.mark.parametrize("text", [
    "Acme 10Y yield moved from 4.5% to 4.5%.",             # no change
    "Acme 10Y yield moved from 1% to 4%.",                 # more than a rate moves at once
    "Crude oil moved from $90 to 95%.",                    # different units
    "Crude oil moved from $90 to €95.",                    # different currencies
    "Crude oil moved from $10 to $95.",                    # out of any plausible band
    "Crude oil moved from 0 to $5.",
])
def test_revisions_that_do_not_read(rules, text):
    assert [s[0] for s in read(rules, text)] in ([], ["move"]) and not any(
        s[3] in ("relative", "absolute") for s in read(rules, text) if s[0] == "move")


@pytest.mark.parametrize("text,date", [
    ("Crude oil at $120 in 2029.", OCT),                   # a long-range forecast
    ("Crude oil was $95 on 3 Jan 2026.", OCT),             # a figure half a year old
    ("The Acme 10Y yield forecast is 4.4%.", None),        # a market level's forecast
    ("We forecast the dollar index at 105.", None),
    ("Harvest Bank CET1 ratio of 14.5% at YE26e.", None),
    ("The target for Ridge Energy operating profit is $7bn.", None),
    ("Acme Bank net interest income was $26bn in 3Q.", None),            # a quarter's flow is not a year's
    ("Acme Bank net interest income (ex markets) was $96bn.", None),     # another metric
    ("Union inflation ranged from 3.4% in one state to 5% in another.", None),
    ("Acme GDP growth was 1.4% QoQ.", None),               # not a y/y rate
    ("Crude oil, which is volatile, is $95.", None),
    ("Crude oil is near the levels last seen in a very long while, when it was $95.", None),
])
def test_no_level(rules, text, date):
    assert not [s for s in read(rules, text, date=date) if s[0] == "observe"]


def test_a_forecast_of_a_market_level_is_neither_a_level_nor_a_move(rules):
    assert read(rules, "Acme 10Y yields are projected to fall to 4.45%.", region="US") == []


def test_a_level_after_a_move_size(rules):
    assert read(rules, "Crude oil rose 7% and was $95.") == [("move", "crude_oil.price", 0.07, "relative")]


def test_key_data_line(rules):
    assert read(rules, "Price (26 Aug 2026) 48 EUR", subject="ridge_energy", date=OCT) == [
        ("observe", "ridge_energy.share_price", 48.0)]


def test_sizes(rules):
    assert read(rules, "Market volatility jumped (VIX +12%).") == [
        ("move", "capital_markets.market_volatility", 0.5, "standardized")]
    assert read(rules, "We revise Ridge Energy operating profit by +10%.") == [
        ("move", "ridge_energy.operating_profit", 0.1, "relative")]


@pytest.mark.parametrize("text", [
    "Crude Oil Rises Sharply Today",                      # a heading
    "Exporters are exposed to a stronger dollar.",
    "A stronger dollar leads to higher costs.",
    "Crude oil points to weaker manufacturing activity.",
    "The dollar raises import costs.",
    "Higher imports of crude oil.",
    "Insurers use swaps to reduce volatility.",
])
def test_no_bare_direction(rules, text):
    assert read(rules, text) == []


def test_licensed_infinitives_are_the_values_moves(rules):
    assert read(rules, "Crude oil is expected to rise.") == [("move", "crude_oil.price", 0.5, "standardized")]
    assert read(rules, "We expect the ACB to raise its policy rate.") == [
        ("move", "central_bank.policy_rate", 0.5, "standardized")]


# -- table rows ---------------------------------------------------------------------------------------------------------------
FY = header_of("Fiscal Year Ending 12/25 12/26e 12/27e")


def test_a_row_is_read_in_the_documents_fiscal_year(rules):
    assert read(rules, "Operating profit ($m) 3,766.2 3,843.4 4,260.8", subject="acme_motors", header=FY, date=OCT) == [
        ("observe", "acme_motors.operating_profit", 3.8434)]


@pytest.mark.parametrize("text,reading", [
    ("Operating profit ($m) Old 3,766.2 3,843.4 4,260.8", {"header": FY}),           # old figures
    ("Ridge Energy share price target 50 52 55", {"header": FY}),
    ("Operating profit ($m) 3,766.2 3,843.4 4,260.8", {}),                          # no header
    ("Operating profit ($m) 3,766.2 3,843.4", {"header": FY}),                      # cells and columns differ
    ("Operating profit ($m) 3,766.2 3,843.4 4,260.8", {"header": header_of("03/26 03/27E 03/28E")}),  # another year-end
    ("Operating profit ($m) 3,766.2 3,843.4 4,260.8", {"header": header_of("12/22 12/23 12/24")}),    # no column now
    ("Operating profit ($m) 37,662 38,434 42,608", {"header": FY}),                  # implausible as a level
])
def test_rows_that_claim_nothing(rules, text, reading):
    assert read(rules, text, subject="acme_motors", date=OCT, **reading) == []


def test_a_flipped_value_in_a_row_claims_nothing(rules):
    assert read(rules, "The dollar 100.0 101.0 102.0", header=FY, date=OCT) == []


def test_a_row_label_with_words_is_a_sentence(rules):
    # "spot and futures" is not a label: the line is read as a sentence, and as a table line it claims nothing
    assert read(rules, "Crude oil spot and futures 95.1 96.2 97.3", header=FY, date=OCT) == []
    assert read(rules, "Crude oil rose 3% and 4%.", header=FY, date=OCT) == [("move", "crude_oil.price", 0.03, "relative")]


def test_a_stale_dated_column(rules):
    h = header_of("31-Dec-2025 31-Mar-2026")
    assert read(rules, "Crude oil 90.1 95.2", header=h, date=OCT) == []
    assert read(rules, "Crude oil 90.1 95.2", header=h, date=datetime(2026, 4, 2, tzinfo=UTC)) == [
        ("observe", "crude_oil.price", 95.2)]


def test_a_revision_row(rules):
    h = header_of("($) Previous Current")
    assert read(rules, "Operating profit (m) 5,800.0 6,100.0", subject="ridge_energy", header=h) == [
        ("move", "ridge_energy.operating_profit", 0.0517, "relative")]
    assert read(rules, "Operating profit (m) $5,800.0 €6,100.0", subject="ridge_energy", header=h) == []


@pytest.mark.parametrize("label,want", [
    ("Net interest income (€ mn)", 14.805),                # a scale in the label
    ("Net interest income", 14.805),                       # the one scale that makes it plausible
])
def test_cell_scales(rules, label, want):
    h = header_of("2025 2026E 2027E")
    assert read(rules, f"{label} 14,472 14,805 15,734", subject="harvest_bank", header=h, date=OCT) == [
        ("observe", "harvest_bank.net_interest_income", want)]


def test_cell_scales_from_hints(rules):
    h = header_of("FY2026 FY2027 FY2028")
    assert read(rules, "Vehicle sales (000s) 9,600 9,700 9,800", subject="acme_motors", header=h, date=OCT) == [
        ("observe", "acme_motors.vehicle_sales", 9.6)]
    assert read(rules, "Vehicle sales (k) 9,600 9,700 9,800", subject="acme_motors", header=h, date=OCT) == [
        ("observe", "acme_motors.vehicle_sales", 9.6)]
    assert read(rules, "Crude oil $90 $95", header=header_of("30 Sep 1 Oct"), date=OCT) == [
        ("observe", "crude_oil.price", 95.0)]
    # a level is read in the latest actual period passed, never an estimate, even for a quarter just ended
    assert read(rules, "Harvest Bank CET1 ratio (%) 14.7 15.0", header=header_of("6/26 9/26E"), date=OCT) == [
        ("observe", "harvest_bank.cet1_ratio", 14.7)]


# -- spreadsheet rows ------------------------------------------------------------------------------------------------------
SHEET = header_of("USD |  | Q1-2026 | Q2-2026 | FY2026")


def test_sheet_row_by_position(rules):
    row = "Common Equity Tier 1 Capital Ratio, % |  | 0.1428 | 0.1419 | 0.15"
    assert read(rules, row, subject="acme_bank", header=SHEET, date=OCT) == [("observe", "acme_bank.cet1_ratio", 14.19)]
    row = "Net Interest Income, mm |  | 25000 | 26000 | 102112"
    assert read(rules, row, subject="acme_bank", header=SHEET, date=OCT) == [
        ("observe", "acme_bank.net_interest_income", 102.112)]


@pytest.mark.parametrize("row,reading", [
    ("Net Interest Income, mm |  | n/a | n/a | n/a", {"header": SHEET}),            # no figures under the columns
    ("Net Interest Income, mm |  | 25000", {"header": header_of("USD | FY2026 | Q1-2026 | Q2-2026 | FY2027")}),
    ("Net Interest Income, mm |  | 25000 | 26000 | 102112", {}),                     # no header
    ("Net Interest Income, mm |  | 25000 | 26000 | 102112", {"header": FY}),         # a line's header has no cells
    ("Net Interest Income consensus, mm |  | 25000 | 26000 | 102112", {"header": SHEET}),
])
def test_sheet_rows_that_claim_nothing(rules, row, reading):
    assert read(rules, row, subject="acme_bank", date=OCT, **reading) == []


def test_sheet_row_with_its_own_period(rules):
    row = "732 | Forward |  | EBIT | id | FY2026 |  |  | 3400000 | 3400000"
    assert read(rules, row, subject="acme_motors", date=OCT) == [("observe", "acme_motors.operating_profit", 3.4)]
    assert read(rules, "Forward |  | EBIT | FY2026", subject="acme_motors", date=OCT) == []
    assert read(rules, "Forward |  | EBIT | FY2026 | FY2027 | 3400000", subject="acme_motors", date=OCT) == []


# -- channels -------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("text,want", [
    ("Harvest Bank net interest income rose 5%, thanks to a higher UCB policy rate.",
     ("support", "union_bank.policy_rate", "harvest_bank.net_interest_income")),
    ("ACB hikes are unlikely to strengthen the dollar.", ("contradict", "central_bank.policy_rate", "dollar.index")),
])
def test_channels(rules, text, want):
    assert want in read(rules, text)


@pytest.mark.parametrize("text", [
    "Harvest Bank net interest income, thanks to the UCB policy rate.",              # the effect has no direction
    "Harvest Bank net interest income rose but fell as the UCB policy rate rose.",
    "Crude oil and other inputs helped Blue Freight operating profit.",               # the verb is not the first's
    "Crude oil in the second half of this year sharply lifts Blue Freight operating profit.",   # too far for a link
    "Crude oil does not lift Blue Freight operating profit.",                         # a denied channel proposes nothing
    "Crude oil | lifts | Blue Freight operating profit",                              # across cells of a table
    "The union unemployment raises the UCB policy rate.",                             # a name modifying another noun
])
def test_no_channel(rules, text):
    assert not [s for s in read(rules, text) if s[0] in ("support", "contradict", "link")]


def test_a_new_link_needs_both_values_named(rules):
    assert read(rules, "Crude oil lifts operating profit.", subject="blue_freight") == []


# -- chunks -------------------------------------------------------------------------------------------------------------------
def test_a_page_change_clears_the_header(rules):
    r = Reading(header=FY, page=1)
    claims_of_chunk(rules, 0, "Nothing.", r, page=2)
    assert r.header is None and r.page == 2
    claims_of_chunk(rules, 1, "Fiscal Year Ending 12/25 12/26e 12/27e", r, page=2)
    assert r.header == FY


def test_figure_runs_are_table_cells(rules):
    assert read(rules, "ACB hike and soft data, unwind 0.9027 0.8522 +6.3% over five weeks") == []


def test_keep_best_keeps_a_level_and_a_move_per_value():
    a = Found("observe", value_of="x", value=1.0, confidence=0.75)
    b = Found("move", value_of="x", delta=0.1, confidence=0.8)
    c = Found("move", value_of="x", delta=0.2, confidence=0.45)
    d = Found("support", source="x", target="y", confidence=0.6)
    e = Found("support", source="x", target="y", confidence=0.6)
    cl = [ChunkClaims(0, "", found=[a, c]), ChunkClaims(1, "", found=[b, d, e])]
    keep_best(cl)
    assert cl[0].found == [a] and cl[1].found == [b, d]


def test_a_rate_in_a_row_needs_a_percent(rules):
    h = header_of("30 Sep 1 Oct")
    assert read(rules, "The Acme 10Y yield 4.50 4.60", header=h, date=OCT) == []
    assert read(rules, "Acme 10Y yield (%) 4.50 4.60", header=h, date=OCT) == [("observe", "gov_bonds.yield_10y", 4.6)]


def test_a_disclaimer_claims_nothing(rules):
    assert read(rules, "This report is not an offer to buy crude oil, which rose 3%.") == []


def test_a_level_beside_its_figure_in_a_sheet(rules):
    assert read(rules, "Ridge Energy Ltd. | RDGE | dollar index | 104.054 | FY2025 | 7397", date=OCT) == [
        ("observe", "dollar.index", 104.054)]
    assert read(rules, "Last Price | 6940", subject="acme_re", date=OCT) == [
        ("observe", "acme_re.share_price", 6940.0)]
    assert read(rules, "Last Price | 69400000", subject="acme_re", date=OCT) == []
    # a projection, or a past episode's row, is no level
    assert read(rules, "Year-end dollar index | 107.6", date=OCT) == []
    assert read(rules, "2007-09 oil spike | crude oil | 132.72", date=OCT) == []


def test_since_a_year_dates_nothing(rules):
    assert read(rules, "The ten-year hit 5.14%, the highest since 2007.", date=OCT, region="US") == [
        ("observe", "gov_bonds.yield_10y", 5.14)]


# -- round 2: general reading rules ----------------------------------------------------------------------------------------
def test_a_growth_rate_is_read_as_its_level(rules):
    assert read(rules, "Excluding energy, Union core CPI rose 1.7% y-o-y.") == [("observe", "union_economy.core_inflation", 1.7)]
    assert read(rules, "Acme GDP growth (+2.2% YoY) remained supported by services.") == [
        ("observe", "economy.gdp_growth", 2.2)]


def test_a_figure_against_consensus_is_no_move(rules):
    assert read(rules, "Acme Bank net interest income is 2% higher than consensus.") == []


@pytest.mark.parametrize("text", [
    "Key risks include higher crude oil lifting Union core CPI.",         # a list of risks joins nothing
    "The Acme economy weakened due to the Acme economy.",                  # one entity named twice
    "Acme economy EV demand weakened due to Acme economy EV subsidies.",   # names modifying other nouns
])
def test_no_channel_round_two(rules, text):
    assert not [s for s in read(rules, text) if s[0] in ("support", "contradict", "link")]


@pytest.mark.parametrize("text", [
    "Higher crude oil should aid exporters.",             # the value is the cause here, not a mover
    "Deal and issuance activity at $78.",                 # an index is in no currency
    "The dollar index at 197.5.",                         # far outside its own band
    "FX shocks: +5 = stronger dollar.",                   # a definition
    "Absent a significant decline in crude oil, rates stay high.",
    "Positive catalysts are a strong recovery in home sales.",
    "Acme Bank net interest income rises 1.7% for a 100bp move up in rates.",
])
def test_no_claim_round_two(rules, text):
    assert read(rules, text, region="EU") == []


def test_sector_wide_in_aggregate(rules):
    assert read(rules, "NII estimates rose on a median basis.", subject="harvest_bank") == []


FY4 = header_of("FY12/24 FY12/25 FY12/26 FY12/27")


def test_rows_with_footnotes_and_empty_cells(rules):
    row = "Adjusted net income *1 - 812.0 881.5 979.3"                   # a footnote mark, an empty first cell
    assert read(rules, row, subject="acme_re", header=FY4, date=OCT) == [
        ("observe", "acme_re.operating_profit", 881.5)]
    assert read(rules, "Adjusted net income 750.0 - 881.5 979.3", subject="acme_re", header=FY4, date=OCT) == [
        ("observe", "acme_re.operating_profit", 881.5)]
    # the document's column is empty; a lone figure is no row; words between cells end the row
    assert read(rules, "Adjusted net income 750.0 812.0 - 979.3", subject="acme_re", header=FY4, date=OCT) == []
    assert read(rules, "Adjusted net income 750.0 812.0 - -", subject="acme_re", header=FY4, date=OCT) == []
    assert read(rules, "Adjusted net income 750.0 812.0 881.5 - x", subject="acme_re", header=FY4, date=OCT) == []
    assert read(rules, "Adjusted net income - - - 979.3", subject="acme_re", header=FY4, date=OCT) == []
    assert read(rules, "Adjusted net income 750.0 812.0 or 881.5 979.3", subject="acme_re", header=FY4,
                date=OCT) == []


def test_new_and_old_estimates(rules):
    r = Reading(subject="acme_re", date=OCT)
    text = "FY12/26 FY12/27 FY12/26 FY12/27\nBrokerMe (New) BrokerMe (New) BrokerMe (Old) BrokerMe (Old)\nDomestic P&C 219.6 239.8 225.2 244.2"
    claims, r = claims_of_chunk(rules, 0, text, r)
    assert [(f.type, round(f.value or f.delta, 4)) for f in claims.found] == [("observe", 219.6), ("move", -0.0249)]
    # marks with no old column for the period, or that cannot be compared
    text = "FY12/26 FY12/27 FY12/28\nNew New Old\nDomestic P&C 219.6 239.8 225.2"
    claims, _ = claims_of_chunk(rules, 0, text, Reading(subject="acme_re", date=OCT))
    assert [f.type for f in claims.found] == ["observe"]
    text = "FY12/26 FY12/26\nNew Old\nDomestic P&C $219.6 €225.2"
    claims, _ = claims_of_chunk(rules, 0, text, Reading(subject="acme_re", date=OCT))
    assert [f.type for f in claims.found] == ["observe"]
    text = "FY12/24 FY12/25\nNew Old\nDomestic P&C 219.6 225.2"                 # no column for now
    claims, _ = claims_of_chunk(rules, 0, text, Reading(subject="acme_re", date=OCT))
    assert claims.found == []


# -- round 3: generic table reading ----------------------------------------------------------------------------------------
def found_of(rules: Rules, text: str, **reading) -> list[tuple]:
    claims, _ = claims_of_chunk(rules, 0, text, Reading(**reading))
    return [(f.type, f.value_of, round(f.value if f.type == "observe" else f.delta, 4)) for f in claims.found]


MACRO = "\n".join([
    "Series | Unit | 30-Jun-2026 | 30-Sep-2026 | Current | As of | Source | Notes",
    "Acme policy rate | % | 3.5 | 3.5 | 4.0 | 2026-10-01 | central bank | Raised in September. Held in July.",
    "Acme 10Y yield (constant maturity) | % | 4.1 | 4.2 | 4.9 | 2026-10-01 | treasury",
    "Acme CPI (headline) YoY | % YoY | | | 3.5 | 2026-09 | statistics office",
    "Acme CPI (core) YoY | % YoY | | | 2.5 | 2026-09 | statistics office",
    "Union core CPI (excl. energy) YoY | % YoY | | | 1.9 | 2026-08",
    "Union equity index | index | 5000 | 5100 | 5600 | 2026-10-01",
    "Interest Rate on Borrowings, % | | 0.1 | 0.1 | 0.2",
    "ACB Dec-2026 hike probability | % | | | 80 | 2026-10-01 | futures | +20bp priced for the December meeting.",
])


def test_a_sheet_of_inputs_is_read_in_its_current_column(rules):
    """A header row of dated columns and a "Current" one, among labels; the unit in its own column; a growth rate's
    YoY row is its level, a "(core)" row is not headline CPI, a generic rate names no agency."""
    assert found_of(rules, MACRO, date=OCT, region="EU") == [
        ("observe", "central_bank.policy_rate", 4.0), ("observe", "gov_bonds.yield_10y", 4.9),
        ("observe", "economy.headline_inflation", 3.5), ("observe", "union_economy.core_inflation", 1.9),
        ("observe", "union_capital_markets.equity_index", 5600.0), ("move", "central_bank.policy_rate", 0.2)]


@pytest.mark.parametrize("text,want", [
    ("Markets have 25bp of UCB cuts priced in by March.", []),                  # "of UCB cuts": not the pattern
    ("For the UCB, 25bp of cuts are priced by March.", [("move", "union_bank.policy_rate", -0.25)]),
    ("For the ACB, -10bp is priced for October.", [("move", "central_bank.policy_rate", -0.1)]),
    ("The ACB has no 10bp priced for October.", []),
    ("Oil has 25bp priced.", []),                                              # no policy rate named
])
def test_a_move_priced_by_the_market(rules, text, want):
    assert [x for x in found_of(rules, text, date=OCT) if x[0] == "move"] == want


def test_an_average_is_no_level_and_a_past_cycle_no_move(rules):
    assert read(rules, "In 2Q26 deposit costs averaged 2.3% against an average effective policy rate of 3.6%.",
                date=OCT, region="US") == []
    assert read(rules, "In the last cycle (the ACB cut rates from September 2024 through December 2025) and up to "
                       "the start of the recent hiking cycle, deposit betas were low.", date=OCT, region="US") == []


def test_a_key_figure_with_its_label_after_it(rules):
    assert read(rules, "Ridge Energy Ltd. (RDGE)\n$48 (Stock Price as of 10/01/2026)", subject="ridge_energy",
                date=OCT) == [("observe", "ridge_energy.share_price", 48.0)]
    assert read(rules, "Ridge Energy Ltd. (RDGE)\n$48 (Stock Price target)", subject="ridge_energy", date=OCT) == []


DASHBOARD = "\n".join([
    "| | | | | | | CET1 Ratio, % | | | Stock Price, $ | | |",
    "Company Name | Ticker | Static Price (1 Oct) | Price a Week Ago | Price on 2/1/2025 | "
    "Static Price (1 Oct) (USD) | FY-1 | FY | CET1 Ratio, % | 2024-12-31 | Current | Forward EPS (Consensus) | Avg.",
    "Loans",
    "Deposits, mm | Net Interest Income, mm",
    "Acme Bank Corp | ACBK US | 310.5 | 305 | 250 | 310.5 | 0.15 | 0.149 | 0.152 | 240 | 311 | 20.5 | 9 | 90000",
    "Other Bank plc | OB LN | 5.1 | 5 | 4 | 6.4 | 0.13 | 0.13 | 0.14 | 4 | 5 | 1 | 2 | 3",
    "Delta Bank Inc. | DLTB US | 120.5 | 118 | 90 | 120.5 | 0.14 | 0.139 | 0.141 | 70 | 121 | 9.5 | 5 | 60000",
])


def test_an_entity_row_table(rules):
    """Rows of companies under header rows that name each column's measure: a level in its latest column (named by
    the measure, or "Current" under a group header), never a past or forward period, consensus, a converted copy, or a
    flow; a header cell written on several lines is joined back into its row."""
    assert found_of(rules, DASHBOARD, date=OCT) == [
        ("observe", "acme_bank.share_price", 310.5), ("observe", "acme_bank.cet1_ratio", 15.2),
        ("observe", "delta_bank.share_price", 120.5), ("observe", "delta_bank.cet1_ratio", 14.1)]   # Delta's since its construction


def test_an_entity_row_needs_its_header_rows(rules):
    row = "Acme Bank Corp | ACBK US | 310.5 | 305 | 250"
    assert found_of(rules, row, date=OCT) == []
    assert found_of(rules, "Name | Ticker | Static Price (1 Oct) | x | y\n3M Co | MMM | 310.5 | 305 | 250",
                    date=OCT) == []
    assert found_of(rules, "Name | Ticker | Static Price (1 Oct) | x | y\nAcme Bank | ACBK US | 99999 | 305 | 250",
                    date=OCT) == []                                                     # an implausible price
    # "Current" first in its row: no group header to its left names a measure
    assert found_of(rules, "Current | Ticker | Name\n1 | 2 | 3 | Acme Bank", date=OCT) == []


def test_a_revised_plan_row_for_the_current_year(rules):
    text = "Plan item | Unit | Initial (1-May-26) | Revised (1-Sep-26) | Source\nUnit sales FY2026 | k units | 9500 | 9650"
    assert found_of(rules, text, subject="acme_motors", date=OCT) == [
        ("observe", "acme_motors.vehicle_sales", 9.65), ("move", "acme_motors.vehicle_sales", 0.0158)]
    # another year's row: only the revision
    text = "Plan item | Unit | Initial (1-May-26) | Revised (1-Sep-26) | Source\nUnit sales FY2028 | k units | 9500 | 9650"
    assert found_of(rules, text, subject="acme_motors", date=OCT) == [("move", "acme_motors.vehicle_sales", 0.0158)]


# -- causal claims in prose -------------------------------------------------------------------------------------------------
def channels(rules: Rules, text: str, **reading) -> set[tuple]:
    return {s for s in read(rules, text, **reading) if s[0] in ("support", "contradict", "link")}


@pytest.mark.parametrize("text,want", [
    # an entity named for its values stands for the one value whose link has the sign the sentence states
    ("Higher Acme 10Y yields lift Acme Re.", {("support", "gov_bonds.yield_10y", "acme_re.domestic_pc_profit")}),
    ("A stronger dollar lifts Acme Re.", {("support", "dollar.index", "acme_re.international_profit")}),
    # a sector with its region: each of the model's companies in it, by the value after a possessive if any
    ("Higher Acme 10Y yields lift US insurers.", {("support", "gov_bonds.yield_10y", "acme_re.domestic_pc_profit")}),
    ("A higher ACB policy rate lifts US banks' net interest income.",
     {("support", "central_bank.policy_rate", "acme_bank.net_interest_income"),
      ("support", "central_bank.policy_rate", "delta_bank.net_interest_income")}),
    ("A stronger dollar lifts US insurers' overseas profit.", {("support", "dollar.index", "acme_re.international_profit")}),
    ("A stronger dollar hurts US automakers.", {("support", "dollar.index", "acme_motors.operating_profit")}),
    # bare "yields": the bond market of the region in view
    ("Higher yields lift US insurers' investment income.",
     {("support", "gov_bonds.yield_10y", "acme_re.domestic_pc_profit")}),
    ("Higher yields lift Harvest Bank's net interest income.",
     {("support", "union_bonds.yield_10y", "harvest_bank.net_interest_income")}),
    # connectors that name the cause after the effect, with their own sign
    ("Acme Motors's operating profit was hurt by the stronger dollar.",
     {("support", "dollar.index", "acme_motors.operating_profit")}),
    ("Acme Re's international business benefits from a stronger dollar.",
     {("support", "dollar.index", "acme_re.international_profit")}),
    ("The dollar rose amid talk of ACB tightening.", {("support", "central_bank.policy_rate", "dollar.index")}),
    # predicates, and verbs with no sign of their own
    ("A weaker dollar is a tailwind for Acme Motors's operating profit.",
     {("support", "dollar.index", "acme_motors.operating_profit")}),
    ("Lower UCB policy rates may lead to Harvest Bank net interest income pressure.",
     {("support", "union_bank.policy_rate", "harvest_bank.net_interest_income")}),
    ("Higher Acme 10Y yields, which lift Acme Re's domestic P&C profit, are a theme.",
     {("support", "gov_bonds.yield_10y", "acme_re.domestic_pc_profit")}),
    ("Following the ACB's rate hike, the dollar rose 3%.", {("support", "central_bank.policy_rate", "dollar.index")}),
    ("The dollar rose 2% after the ACB's rate hike.", {("support", "central_bank.policy_rate", "dollar.index")}),
    ("As the dollar strengthened, US equities fell 3%.",
     {("support", "dollar.index", "capital_markets.equity_index")}),
    # new links
    ("Higher crude oil has driven Acme 10Y yields higher.", {("link", "crude_oil.price", "gov_bonds.yield_10y")}),
    ("The ACB kept hiking, triggering a slide in freight rates.",
     {("link", "central_bank.policy_rate", "shipping.freight_cost")}),
])
def test_causal_claims(rules, text, want):
    assert channels(rules, text) == want


def test_a_market_value_by_the_documents_region_may_end_a_new_link(rules):
    assert channels(rules, "Higher crude oil lifts 10-year yields.", region="US") == {
        ("link", "crude_oil.price", "gov_bonds.yield_10y")}


def test_help_takes_the_sign_of_the_verb_it_helps(rules):
    def effect(text):
        claims, _ = claims_of_chunk(rules, 0, text, Reading())
        return [f.effect for f in claims.found if f.type == "link"]
    assert effect("Lower crude oil would help moderate ACB rate hikes.") == [0.3]
    assert effect("Lower crude oil would help lift ACB rate hikes.") == [-0.3]
    assert effect("Lower crude oil would help stabilise ACB rate hikes.") == [-0.3]


@pytest.mark.parametrize("text", [
    "We push back on the notion that a stronger dollar lifts Acme Re's international profit.",   # a view doubted
    "Measures to support the dollar lifted Acme Re's international profit.",                      # the dollar is an aim's object
    "ACB rate hikes follow a 25bp increase in Acme 2Y yields.",                  # a causal word as a noun
    "Acme 10Y yields are 5bp lower than Acme 2Y yields.",                        # "lower" as a predicate
    "Higher 30-year yields lift Acme Re.",                                        # yields of a tenor not modelled
    "Higher yields lift Ridge Energy.",                                           # no link from any yield
    "US insurers lift Acme 10Y yields.",                                          # a sector is moved, not mover
    "Higher Acme 10Y yields lift Korean insurers.",                               # no such region's sector
    "Higher Acme 10Y yields lift European insurers.",                             # no such company in the model
    "Lower UCB policy rates may lead to Harvest Bank net interest income.",       # led where?
    "Following the ACB meeting, the dollar rose 3%.",                             # no direction for the event
    "Following the ACB's rate hike, the dollar could rise.",                      # a supposition
    "Following the ACB's rate hike the dollar rose.",                             # no clause to read
    "The ACB and help stabilise Acme bonds.",
    "The dollar rose 2% after the ACB meeting.",                                  # an event with no direction
    "As of today, the dollar rose and US equities fell.",
    "The dollar strengthened, US equities fell.",                                 # the verb has no object
])
def test_no_causal_claim(rules, text):
    assert channels(rules, text) == set()


@pytest.mark.parametrize("text,want", [
    # a report of what happened claims the directions on both sides; a mechanism claims neither
    ("A stronger dollar index lifted Acme Re's international profit.",
     [("move", "dollar.index", 0.5, "standardized"), ("move", "acme_re.international_profit", 0.5, "standardized")]),
    ("A stronger dollar index lifts Acme Re's international profit.", []),
    ("Acme Re's international profit rose, thanks to a stronger dollar index.",
     [("move", "dollar.index", 0.5, "standardized"), ("move", "acme_re.international_profit", 0.5, "standardized")]),
    ("Acme Re's international profit rose, given a stronger dollar index.", [("move", "acme_re.international_profit", 0.5, "standardized")]),
    ("Acme Re's international profit rose 5%, thanks to a stronger dollar index.",
     [("move", "acme_re.international_profit", 0.05, "relative"), ("move", "dollar.index", 0.5, "standardized")]),
    # the cause's word is not the effect's ("flat due to weaker demand")
    ("Blue Freight's profit was flat due to weaker freight revenue.",
     [("move", "blue_freight.freight_revenue", -0.5, "standardized")]),
    ("The dollar appreciated 4%.", [("move", "dollar.index", 0.04, "relative")]),
    ("The dollar rose amid talk of ACB tightening.", [("move", "dollar.index", 0.5, "standardized")]),
    # a figure before a connector is not the cause's size
    ("The dollar rose 2% after the ACB's rate hike.",
     [("move", "dollar.index", 0.02, "relative"), ("move", "central_bank.policy_rate", 0.5, "standardized")]),
])
def test_moves_in_a_causal_claim(rules, text, want):
    assert [s for s in read(rules, text) if s[0] == "move"] == want


def test_a_values_totals_are_every_value_it_adds_into_once_even_by_two_routes():
    r = object.__new__(Rules)
    r._into = {"a.part": {"a.segment", "a.region"}, "a.segment": {"a.total"}, "a.region": {"a.total"}}
    assert r._totals_of("a.part") == {"a.segment", "a.region", "a.total"}
    assert r._totals_of("a.total") == set()
