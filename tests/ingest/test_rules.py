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
    ("FY26 and USD/JPY", []),                              # figures inside words are not numbers
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
    assert _licensed("the BoJ to raise") == "the BoJ to raise"
    assert _licensed("(BoJ) to raise") == "(BoJ) to raise"
    assert _licensed("its portfolio to reduce") == "its portfolio "


def test_heading_and_labelled_parens():
    assert _heading("Brent Crude Rises Sharply Today") and not _heading("Brent crude rose today")
    assert not _heading("Oil Up")
    s = "Volatility jumped (VIX +12%) and fell (-3%)."
    assert _labelled_parens(s, 0, s.index("+12")) and not _labelled_parens(s, 0, s.index("-3"))
    assert not _labelled_parens(s, 0, 5)


# -- levels and moves -------------------------------------------------------------------------------------------------------
def test_a_target_is_not_the_value(rules):
    assert read(rules, "Komatsu share price target raised to ¥9,000.") == []
    assert read(rules, "The ten-year Treasury target is 4.8%.") == []
    # though a forecaster's revised target for a rate moves its view of the rate
    assert read(rules, "We revise our ten-year Treasury target from 4.35% to 4.80%.") == [
        ("move", "us_treasuries.yield_10y", 0.45, "absolute")]


@pytest.mark.parametrize("text", [
    "In 2024 Brent crude rose 10%.",                       # only earlier years: history
    "Historically, Brent crude rose in winter.",
    "Will Brent crude rise?",
    "Yen borrowing rose sharply.",                         # the value's name modifies another measure
    "Global implied volatility rose.",                     # a value named without its entity, after another noun
    "Global equity market volatility rose.",
    "US interest rates rose.",                             # the rate environment: a cause, never a move
    "Revenue of 500 bn yen fell.",                         # a currency's name as a unit
    "Brent crude, we think, moved from $90 to $95.",
    "Brent crude may rise.",
])
def test_no_claim(rules, text):
    assert read(rules, text, date=OCT) == []


def test_policy_rates_by_the_documents_region_are_for_channels_only(rules):
    assert read(rules, "Policy rates rose.", region="US") == []


def test_sector_wide_figures_belong_to_no_one_company(rules):
    assert read(rules, "We raised our NII forecasts for select banks.", subject="unicredit") == []
    assert read(rules, "We raised our NII forecasts.", subject="unicredit") == [
        ("move", "unicredit.net_interest_income", 0.5, "standardized")]


def test_a_value_named_with_its_own_word_is_not_modified(rules):
    assert read(rules, "TSF growth slowed to 7.3%.") == [("observe", "china_economy.credit_growth", 7.3)]


@pytest.mark.parametrize("text,want", [
    ("We cut our Komatsu operating profit forecast to ¥600bn from ¥650bn.",
     ("move", "komatsu.operating_profit", -0.0769, "relative")),
    ("Komatsu operating profit was revised from ¥650bn to ¥700bn.", ("move", "komatsu.operating_profit", 0.0769,
                                                                     "relative")),
    ("The UST 10Y yield target was cut to 4.2% (from 4.5%).", ("move", "us_treasuries.yield_10y", -0.3, "absolute")),
])
def test_revisions(rules, text, want):
    assert read(rules, text) == [want]


@pytest.mark.parametrize("text", [
    "UST 10Y yield moved from 4.5% to 4.5%.",              # no change
    "UST 10Y yield moved from 1% to 4%.",                  # more than a rate moves at once
    "Brent crude moved from $90 to 95%.",                  # different units
    "Brent crude moved from $90 to €95.",                  # different currencies
    "Brent crude moved from $10 to $95.",                  # out of any plausible band
    "Brent crude moved from 0 to $5.",
])
def test_revisions_that_do_not_read(rules, text):
    assert [s[0] for s in read(rules, text)] in ([], ["move"]) and not any(
        s[3] in ("relative", "absolute") for s in read(rules, text) if s[0] == "move")


@pytest.mark.parametrize("text,date", [
    ("Brent crude at $120 in 2029.", OCT),                 # a long-range forecast
    ("Brent crude was $95 on 3 Jan 2026.", OCT),           # a figure half a year old
    ("The ten-year Treasury forecast is 4.4%.", None),     # a market level's forecast
    ("We forecast USD/JPY at 150.", None),
    ("UniCredit CET1 ratio of 14.5% at YE26e.", None),
    ("The target for Komatsu operating profit is ¥700bn.", None),
    ("JPMorgan net interest income was $26bn in 3Q.", None),            # a quarter's flow is not a year's
    ("JPMorgan net interest income (ex markets) was $96bn.", None),     # another metric
    ("Euro area inflation ranged from 3.4% in one state to 5% in another.", None),
    ("Japan real GDP growth was 1.4% QoQ.", None),         # not a y/y rate
    ("Brent crude, which is volatile, is $95.", None),
    ("Brent crude is near the levels last seen in a very long while, when it was $95.", None),
])
def test_no_level(rules, text, date):
    assert not [s for s in read(rules, text, date=date) if s[0] == "observe"]


def test_a_forecast_of_a_market_level_is_neither_a_level_nor_a_move(rules):
    assert read(rules, "Ten-year Treasury yields are projected to fall to 4.45%.", region="US") == []


def test_a_level_after_a_move_size(rules):
    assert read(rules, "Brent crude rose 7% and was $95.") == [("move", "oil.brent", 0.07, "relative")]


def test_key_data_line(rules):
    assert read(rules, "Price (26 Aug 2026) 240 JPY", subject="softbank_corp", date=OCT) == [
        ("observe", "softbank_corp.share_price", 240.0)]


def test_sizes(rules):
    assert read(rules, "Market volatility jumped (VIX +12%).") == [
        ("move", "us_capital_markets.market_volatility", 0.5, "standardized")]
    assert read(rules, "We revise Komatsu operating profit by +10%.") == [
        ("move", "komatsu.operating_profit", 0.1, "relative")]


@pytest.mark.parametrize("text", [
    "Brent Crude Rises Sharply Today",                    # a heading
    "Exporters are exposed to a weaker yen.",
    "A weaker yen leads to higher costs.",
    "Brent crude points to weaker manufacturing activity.",
    "The yen raises import costs.",
    "Higher imports of Brent crude.",
    "Insurers use swaps to reduce volatility.",
])
def test_no_bare_direction(rules, text):
    assert read(rules, text) == []


def test_licensed_infinitives_are_the_values_moves(rules):
    assert read(rules, "Brent crude is expected to rise.") == [("move", "oil.brent", 0.5, "standardized")]
    assert read(rules, "We expect the BoJ to raise its policy rate.") == [
        ("move", "boj.policy_rate", 0.5, "standardized")]


# -- table rows ---------------------------------------------------------------------------------------------------------------
FY = header_of("Fiscal Year Ending 03/26 03/27e 03/28e")


def test_a_row_is_read_in_the_documents_fiscal_year(rules):
    assert read(rules, "Operating profit (¥bn) 3,766.2 3,843.4 4,260.8", subject="toyota", header=FY, date=OCT) == [
        ("observe", "toyota.operating_profit", 3.8434)]


@pytest.mark.parametrize("text,reading", [
    ("Operating profit (¥bn) Old 3,766.2 3,843.4 4,260.8", {"header": FY}),          # old figures
    ("Komatsu share price target 9,000 9,500 9,700", {"header": FY}),
    ("Operating profit (¥bn) 3,766.2 3,843.4 4,260.8", {}),                         # no header
    ("Operating profit (¥bn) 3,766.2 3,843.4", {"header": FY}),                     # cells and columns differ
    ("Operating profit (¥bn) 3,766.2 3,843.4 4,260.8", {"header": header_of("12/25 12/26E 12/27E")}),  # a Dec year
    ("Operating profit (¥bn) 3,766.2 3,843.4 4,260.8", {"header": header_of("03/22 03/23 03/24")}),    # no column now
    ("Operating profit (¥bn) 37,662 38,434 42,608", {"header": FY}),                 # implausible as a level
])
def test_rows_that_claim_nothing(rules, text, reading):
    assert read(rules, text, subject="toyota", date=OCT, **reading) == []


def test_a_flipped_value_in_a_row_claims_nothing(rules):
    assert read(rules, "The yen 150.0 151.0 152.0", header=FY, date=OCT) == []


def test_a_row_label_with_words_is_a_sentence(rules):
    # "spot and futures" is not a label: the line is read as a sentence, and as a table line it claims nothing
    assert read(rules, "Brent crude spot and futures 95.1 96.2 97.3", header=FY, date=OCT) == []
    assert read(rules, "Brent crude rose 3% and 4%.", header=FY, date=OCT) == [("move", "oil.brent", 0.03, "relative")]


def test_a_stale_dated_column(rules):
    h = header_of("31-Dec-2025 31-Mar-2026")
    assert read(rules, "Brent crude 90.1 95.2", header=h, date=OCT) == []
    assert read(rules, "Brent crude 90.1 95.2", header=h, date=datetime(2026, 4, 2, tzinfo=UTC)) == [
        ("observe", "oil.brent", 95.2)]


def test_a_revision_row(rules):
    h = header_of("(¥) Previous Current")
    assert read(rules, "Op. profit (m) 1,110,000.0 1,140,000.0", subject="softbank_corp", header=h) == [
        ("move", "softbank_corp.operating_profit", 0.027, "relative")]
    assert read(rules, "Op. profit (m) ¥1,110,000.0 $1,140,000.0", subject="softbank_corp", header=h) == []


@pytest.mark.parametrize("label,want", [
    ("Net interest income (€ mn)", 14.805),                # a scale in the label
    ("Net interest income", 14.805),                       # the one scale that makes it plausible
])
def test_cell_scales(rules, label, want):
    h = header_of("2025 2026E 2027E")
    assert read(rules, f"{label} 14,472 14,805 15,734", subject="unicredit", header=h, date=OCT) == [
        ("observe", "unicredit.net_interest_income", want)]


def test_cell_scales_from_hints(rules):
    h = header_of("FY2026 FY2027 FY2028")
    assert read(rules, "Vehicle sales (000s) 9,600 9,700 9,800", subject="toyota", header=h, date=OCT) == [
        ("observe", "toyota.vehicle_sales", 9.7)]
    assert read(rules, "Vehicle sales (k) 9,600 9,700 9,800", subject="toyota", header=h, date=OCT) == [
        ("observe", "toyota.vehicle_sales", 9.7)]
    assert read(rules, "Brent crude $90 $95", header=header_of("30 Sep 1 Oct"), date=OCT) == [
        ("observe", "oil.brent", 95.0)]
    # a level is read in the latest actual period passed, never an estimate, even for a quarter just ended
    assert read(rules, "UniCredit CET1 ratio (%) 14.7 15.0", header=header_of("6/26 9/26E"), date=OCT) == [
        ("observe", "unicredit.cet1_ratio", 14.7)]


# -- spreadsheet rows ------------------------------------------------------------------------------------------------------
SHEET = header_of("USD |  | Q1-2026 | Q2-2026 | FY2026")


def test_sheet_row_by_position(rules):
    row = "Common Equity Tier 1 Capital Ratio, % |  | 0.1428 | 0.1419 | 0.15"
    assert read(rules, row, subject="jpmorgan", header=SHEET, date=OCT) == [("observe", "jpmorgan.cet1_ratio", 14.19)]
    row = "Net Interest Income, mm |  | 25000 | 26000 | 102112"
    assert read(rules, row, subject="jpmorgan", header=SHEET, date=OCT) == [
        ("observe", "jpmorgan.net_interest_income", 102.112)]


@pytest.mark.parametrize("row,reading", [
    ("Net Interest Income, mm |  | n/a | n/a | n/a", {"header": SHEET}),            # no figures under the columns
    ("Net Interest Income, mm |  | 25000", {"header": header_of("USD | FY2026 | Q1-2026 | Q2-2026 | FY2027")}),
    ("Net Interest Income, mm |  | 25000 | 26000 | 102112", {}),                     # no header
    ("Net Interest Income, mm |  | 25000 | 26000 | 102112", {"header": FY}),         # a line's header has no cells
    ("Net Interest Income consensus, mm |  | 25000 | 26000 | 102112", {"header": SHEET}),
])
def test_sheet_rows_that_claim_nothing(rules, row, reading):
    assert read(rules, row, subject="jpmorgan", date=OCT, **reading) == []


def test_sheet_row_with_its_own_period(rules):
    row = "732 | Forward |  | EBIT | id | FY2027 |  |  | 3400000 | 3400000"
    assert read(rules, row, subject="toyota", date=OCT) == [("observe", "toyota.operating_profit", 3.4)]
    assert read(rules, "Forward |  | EBIT | FY2027", subject="toyota", date=OCT) == []
    assert read(rules, "Forward |  | EBIT | FY2027 | FY2028 | 3400000", subject="toyota", date=OCT) == []


# -- channels -------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("text,want", [
    ("UniCredit net interest income rose 5%, thanks to a higher ECB deposit rate.",
     ("support", "ecb.policy_rate", "unicredit.net_interest_income")),
    ("BoJ hikes are unlikely to strengthen the JPY.", ("contradict", "boj.policy_rate", "dollar_yen.usd_jpy")),
])
def test_channels(rules, text, want):
    assert want in read(rules, text)


@pytest.mark.parametrize("text", [
    "UniCredit net interest income, thanks to the ECB deposit rate.",            # the effect has no direction
    "UniCredit net interest income rose but fell as the ECB deposit rate rose.",
    "Brent crude and other inputs helped Komatsu operating profit.",             # the verb is not the first's
    "Brent crude in the second half of this year sharply lifts Komatsu operating profit.",   # too far for a link
    "Brent crude does not lift Komatsu operating profit.",                       # a denied channel proposes nothing
    "Brent crude | lifts | Komatsu operating profit",                            # across cells of a table
    "Euro area unemployment raises the ECB deposit rate.",                       # a name modifying another noun
])
def test_no_channel(rules, text):
    assert not [s for s in read(rules, text) if s[0] in ("support", "contradict", "link")]


def test_a_new_link_needs_both_values_named(rules):
    assert read(rules, "Brent crude lifts operating profit.", subject="komatsu") == []


# -- chunks -------------------------------------------------------------------------------------------------------------------
def test_a_page_change_clears_the_header(rules):
    r = Reading(header=FY, page=1)
    claims_of_chunk(rules, 0, "Nothing.", r, page=2)
    assert r.header is None and r.page == 2
    claims_of_chunk(rules, 1, "Fiscal Year Ending 03/26 03/27e 03/28e", r, page=2)
    assert r.header == FY


def test_figure_runs_are_table_cells(rules):
    assert read(rules, "BoJ hike and soft data, unwind 0.9027 0.8522 +6.3% over five weeks") == []


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
    assert read(rules, "UST 10Y yield 4.50 4.60", header=h, date=OCT) == []
    assert read(rules, "UST 10Y yield (%) 4.50 4.60", header=h, date=OCT) == [("observe", "us_treasuries.yield_10y", 4.6)]


def test_a_disclaimer_claims_nothing(rules):
    assert read(rules, "This report is not an offer to buy Brent crude, which rose 3%.") == []


def test_a_level_beside_its_figure_in_a_sheet(rules):
    assert read(rules, "Komatsu Ltd. | 6301 JP | USD/JPY | 158.054 | FY2025 | 7397", date=OCT) == [
        ("observe", "dollar_yen.usd_jpy", 158.054)]
    assert read(rules, "Last Price | 6940", subject="tokio_marine", date=OCT) == [
        ("observe", "tokio_marine.share_price", 6940.0)]
    assert read(rules, "Last Price | 69400000", subject="tokio_marine", date=OCT) == []
    # a projection, or a past episode's row, is no level
    assert read(rules, "Year-end USD/JPY | 157.6", date=OCT) == []
    assert read(rules, "2007-09 oil spike | Brent | 132.72", date=OCT) == []


def test_since_a_year_dates_nothing(rules):
    assert read(rules, "The ten-year hit 5.14%, the highest since 2007.", date=OCT, region="US") == [
        ("observe", "us_treasuries.yield_10y", 5.14)]


# -- round 2: general reading rules ----------------------------------------------------------------------------------------
def test_a_growth_rate_is_read_as_its_level(rules):
    assert read(rules, "Excluding fresh food, Japan core CPI rose 1.7% y-o-y.") == [("observe", "japan_economy.core_cpi", 1.7)]
    assert read(rules, "TSF growth (+7.2% YoY) remained supported by bonds.") == [
        ("observe", "china_economy.credit_growth", 7.2)]


def test_a_figure_against_consensus_is_no_move(rules):
    assert read(rules, "JPMorgan net interest income is 2% higher than consensus.") == []


@pytest.mark.parametrize("text", [
    "Key risks include higher Brent crude lifting Japan core CPI.",       # a list of risks joins nothing
    "The US weakened due to the US.",                                      # one entity named twice
    "US EV demand weakened due to US EV subsidies.",                       # names modifying other nouns
])
def test_no_channel_round_two(rules, text):
    assert not [s for s in read(rules, text) if s[0] in ("support", "contradict", "link")]


@pytest.mark.parametrize("text", [
    "Higher Brent crude should aid exporters.",           # the value is the cause here, not a mover
    "Deal and issuance activity at $78.",                 # an index is in no currency
    "USD/JPY at 197.5.",                                  # far outside its own band
    "FX shocks: +5 = weaker yen.",                        # a definition
    "Absent a significant decline in Brent crude, rates stay high.",
    "Positive catalysts are a strong recovery in home sales.",
    "JPMorgan net interest income rises 1.7% for a 100bp move up in rates.",
])
def test_no_claim_round_two(rules, text):
    assert read(rules, text, region="CN") == []


def test_sector_wide_in_aggregate(rules):
    assert read(rules, "NII estimates rose on a median basis.", subject="unicredit") == []


FY4 = header_of("FY3/24 FY3/25 FY3/26 FY3/27")


def test_rows_with_footnotes_and_empty_cells(rules):
    row = "Adjusted net income *1 - 812.0 881.5 979.3"                   # a footnote mark, an empty first cell
    assert read(rules, row, subject="tokio_marine", header=FY4, date=OCT) == [
        ("observe", "tokio_marine.operating_profit", 979.3)]
    assert read(rules, "Adjusted net income 750.0 - 881.5 979.3", subject="tokio_marine", header=FY4, date=OCT) == [
        ("observe", "tokio_marine.operating_profit", 979.3)]
    # the document's column is empty; a lone figure is no row; words between cells end the row
    assert read(rules, "Adjusted net income 750.0 812.0 881.5 -", subject="tokio_marine", header=FY4, date=OCT) == []
    assert read(rules, "Adjusted net income 750.0 812.0 881.5 - x", subject="tokio_marine", header=FY4, date=OCT) == []
    assert read(rules, "Adjusted net income - - - 979.3", subject="tokio_marine", header=FY4, date=OCT) == []
    assert read(rules, "Adjusted net income 750.0 812.0 or 881.5 979.3", subject="tokio_marine", header=FY4,
                date=OCT) == []


def test_new_and_old_estimates(rules):
    r = Reading(subject="tokio_marine", date=OCT)
    text = "FY3/27 FY3/28 FY3/27 FY3/28\nJPMe (New) JPMe (New) JPMe (Old) JPMe (Old)\nJapan P&C 219.6 239.8 225.2 244.2"
    claims, r = claims_of_chunk(rules, 0, text, r)
    assert [(f.type, round(f.value or f.delta, 4)) for f in claims.found] == [("observe", 219.6), ("move", -0.0249)]
    # marks with no old column for the period, or that cannot be compared
    text = "FY3/27 FY3/28 FY3/29\nNew New Old\nJapan P&C 219.6 239.8 225.2"
    claims, _ = claims_of_chunk(rules, 0, text, Reading(subject="tokio_marine", date=OCT))
    assert [f.type for f in claims.found] == ["observe"]
    text = "FY3/27 FY3/27\nNew Old\nJapan P&C ¥219.6 $225.2"
    claims, _ = claims_of_chunk(rules, 0, text, Reading(subject="tokio_marine", date=OCT))
    assert [f.type for f in claims.found] == ["observe"]
    text = "FY3/25 FY3/26\nNew Old\nJapan P&C 219.6 225.2"                 # no column for now
    claims, _ = claims_of_chunk(rules, 0, text, Reading(subject="tokio_marine", date=OCT))
    assert claims.found == []


# -- round 3: generic table reading ----------------------------------------------------------------------------------------
def found_of(rules: Rules, text: str, **reading) -> list[tuple]:
    claims, _ = claims_of_chunk(rules, 0, text, Reading(**reading))
    return [(f.type, f.value_of, round(f.value if f.type == "observe" else f.delta, 4)) for f in claims.found]


MACRO = "\n".join([
    "Series | Unit | 30-Jun-2026 | 30-Sep-2026 | Current | As of | Source | Notes",
    "BoJ policy rate | % | 0.5 | 0.5 | 1.0 | 2026-10-01 | central bank | Raised in September. Held in July.",
    "UST 10Y (constant maturity) | % | 4.1 | 4.2 | 4.9 | 2026-10-01 | treasury",
    "US CPI (headline) YoY | % YoY | | | 3.5 | 2026-09 | statistics office",
    "US CPI (core) YoY | % YoY | | | 2.5 | 2026-09 | statistics office",
    "Japan core CPI (excl. fresh food) YoY | % YoY | | | 1.9 | 2026-08",
    "Euro Stoxx 50 | index | 5000 | 5100 | 5600 | 2026-10-01",
    "Interest Rate on Borrowings, % | | 0.1 | 0.1 | 0.2",
    "Fed Dec-2026 hike probability | % | | | 80 | 2026-10-01 | futures | +20bp priced for the December meeting.",
])


def test_a_sheet_of_inputs_is_read_in_its_current_column(rules):
    """A header row of dated columns and a "Current" one, among labels; the unit in its own column; a growth rate's
    YoY row is its level, a "(core)" row is not headline CPI, a generic rate names no agency."""
    assert found_of(rules, MACRO, date=OCT, region="JP") == [
        ("observe", "boj.policy_rate", 1.0), ("observe", "us_treasuries.yield_10y", 4.9),
        ("observe", "us_economy.headline_cpi", 3.5), ("observe", "japan_economy.core_cpi", 1.9),
        ("observe", "europe_capital_markets.equity_index", 5600.0), ("move", "federal_reserve.policy_rate", 0.2)]


@pytest.mark.parametrize("text,want", [
    ("Markets have 25bp of ECB cuts priced in by March.", []),                  # "of ECB cuts": not the pattern
    ("For the ECB, 25bp of cuts are priced by March.", [("move", "ecb.policy_rate", -0.25)]),
    ("For the BoJ, -10bp is priced for October.", [("move", "boj.policy_rate", -0.1)]),
    ("The BoJ has no 10bp priced for October.", []),
    ("Oil has 25bp priced.", []),                                              # no policy rate named
])
def test_a_move_priced_by_the_market(rules, text, want):
    assert [x for x in found_of(rules, text, date=OCT) if x[0] == "move"] == want


def test_an_average_is_no_level_and_a_past_cycle_no_move(rules):
    assert read(rules, "In 2Q26 deposit costs averaged 2.3% against an average effective Fed Funds rate of 3.6%.",
                date=OCT, region="US") == []
    assert read(rules, "In the last cycle (the Fed cut rates from September 2024 through December 2025) and up to "
                       "the start of the recent hiking cycle, deposit betas were low.", date=OCT, region="US") == []


def test_a_key_figure_with_its_label_after_it(rules):
    assert read(rules, "Komatsu Ltd. (6301 JP)\n¥6,900 (Stock Price as of 10/01/2026)", subject="komatsu",
                date=OCT) == [("observe", "komatsu.share_price", 6900.0)]
    assert read(rules, "Komatsu Ltd. (6301 JP)\n¥6,900 (Stock Price target)", subject="komatsu", date=OCT) == []


DASHBOARD = "\n".join([
    "| | | | | | | CET1 Ratio, % | | | Stock Price, $ | | |",
    "Company Name | Ticker | Static Price (1 Oct) | Price a Week Ago | Price on 2/1/2025 | "
    "Static Price (1 Oct) (USD) | FY-1 | FY | CET1 Ratio, % | 2024-12-31 | Current | Forward EPS (Consensus) | Avg.",
    "Loans",
    "Deposits, mm | Net Interest Income, mm",
    "JPMorgan Chase & Co. | JPM US | 310.5 | 305 | 250 | 310.5 | 0.15 | 0.149 | 0.152 | 240 | 311 | 20.5 | 9 | 90000",
    "Other Bank plc | OB LN | 5.1 | 5 | 4 | 6.4 | 0.13 | 0.13 | 0.14 | 4 | 5 | 1 | 2 | 3",
    "Citigroup Inc. | C US | 120.5 | 118 | 90 | 120.5 | 0.14 | 0.139 | 0.141 | 70 | 121 | 9.5 | 5 | 60000",
])


def test_an_entity_row_table(rules):
    """Rows of companies under header rows that name each column's measure: a level in its latest column (named by
    the measure, or "Current" under a group header), never a past or forward period, consensus, a converted copy, or a
    flow; a header cell written on several lines is joined back into its row."""
    assert found_of(rules, DASHBOARD, date=OCT) == [
        ("observe", "jpmorgan.share_price", 310.5), ("observe", "jpmorgan.cet1_ratio", 15.2),
        ("observe", "citigroup.share_price", 120.5), ("observe", "citigroup.cet1_ratio", 14.1)]   # Citi's since its construction


def test_an_entity_row_needs_its_header_rows(rules):
    row = "JPMorgan Chase & Co. | JPM US | 310.5 | 305 | 250"
    assert found_of(rules, row, date=OCT) == []
    assert found_of(rules, "Name | Ticker | Static Price (1 Oct) | x | y\n3M Co | MMM | 310.5 | 305 | 250",
                    date=OCT) == []
    assert found_of(rules, "Name | Ticker | Static Price (1 Oct) | x | y\nJPMorgan | JPM US | 99999 | 305 | 250",
                    date=OCT) == []                                                     # an implausible price
    # "Current" first in its row: no group header to its left names a measure
    assert found_of(rules, "Current | Ticker | Name\n1 | 2 | 3 | JPMorgan", date=OCT) == []


def test_a_revised_plan_row_for_the_current_year(rules):
    text = "Plan item | Unit | Initial (1-May-26) | Revised (1-Sep-26) | Source\nUnit sales FY3/27 | k units | 9500 | 9650"
    assert found_of(rules, text, subject="toyota", date=OCT) == [
        ("observe", "toyota.vehicle_sales", 9.65), ("move", "toyota.vehicle_sales", 0.0158)]
    # another year's row: only the revision
    text = "Plan item | Unit | Initial (1-May-26) | Revised (1-Sep-26) | Source\nUnit sales FY3/29 | k units | 9500 | 9650"
    assert found_of(rules, text, subject="toyota", date=OCT) == [("move", "toyota.vehicle_sales", 0.0158)]


# -- causal claims in prose -------------------------------------------------------------------------------------------------
def channels(rules: Rules, text: str, **reading) -> set[tuple]:
    return {s for s in read(rules, text, **reading) if s[0] in ("support", "contradict", "link")}


@pytest.mark.parametrize("text,want", [
    # an entity named for its values stands for the one value whose link has the sign the sentence states
    ("Higher JGB yields lift Tokio Marine.", {("support", "jgbs.yield_30y", "tokio_marine.japan_pc_profit")}),
    ("A weaker yen lifts Tokio Marine.", {("support", "dollar_yen.usd_jpy", "tokio_marine.international_profit")}),
    # a sector with its region: each of the model's companies in it, by the value after a possessive if any
    ("Higher super-long JGB yields lift Japanese insurers.",
     {("support", "jgbs.yield_30y", "tokio_marine.japan_pc_profit"), ("support", "jgbs.yield_30y", "msad.domestic_profit")}),
    ("A weaker yen lifts Japanese insurers' overseas profit.",
     {("support", "dollar_yen.usd_jpy", "tokio_marine.international_profit"),
      ("support", "dollar_yen.usd_jpy", "msad.international_profit")}),
    ("A stronger yen hurts Japanese automakers.", {("support", "dollar_yen.usd_jpy", "toyota.operating_profit")}),
    # bare "yields": the bond market of the region in view
    ("Higher yields lift Japanese insurers' investment income.",
     {("support", "jgbs.yield_30y", "tokio_marine.japan_pc_profit"), ("support", "jgbs.yield_30y", "msad.domestic_profit")}),
    ("Higher yields lift UniCredit's net interest income.", {("support", "bunds.yield_10y", "unicredit.net_interest_income")}),
    # connectors that name the cause after the effect, with their own sign
    ("Toyota's operating profit was hurt by the stronger yen.",
     {("support", "dollar_yen.usd_jpy", "toyota.operating_profit")}),
    ("Tokio Marine's international business benefits from a weaker yen.",
     {("support", "dollar_yen.usd_jpy", "tokio_marine.international_profit")}),
    ("USD/JPY fell amid talk of BoJ tightening.", {("support", "boj.policy_rate", "dollar_yen.usd_jpy")}),
    # predicates, and verbs with no sign of their own
    ("A weaker yen is a tailwind for Toyota's operating profit.",
     {("support", "dollar_yen.usd_jpy", "toyota.operating_profit")}),
    ("Lower ECB deposit rates may lead to UniCredit net interest income pressure.",
     {("support", "ecb.policy_rate", "unicredit.net_interest_income")}),
    ("Higher JGB yields, which lift Tokio Marine's Japan P&C profit, are a theme.",
     {("support", "jgbs.yield_30y", "tokio_marine.japan_pc_profit")}),
    ("Following the BoJ's rate hike, the yen rose 3%.", {("support", "boj.policy_rate", "dollar_yen.usd_jpy")}),
    ("USD/JPY fell 2% after the BoJ's rate hike.", {("support", "boj.policy_rate", "dollar_yen.usd_jpy")}),
    ("As the yen strengthened, Japan equities fell 3%.",
     {("support", "dollar_yen.usd_jpy", "japan_capital_markets.equity_index")}),
    # new links
    ("Higher Brent crude has driven US 10-year yields higher.", {("link", "oil.brent", "us_treasuries.yield_10y")}),
    ("The Fed kept hiking, triggering a slide in the yen.",
     {("link", "federal_reserve.policy_rate", "dollar_yen.usd_jpy")}),
])
def test_causal_claims(rules, text, want):
    assert channels(rules, text) == want


def test_a_market_value_by_the_documents_region_may_end_a_new_link(rules):
    assert channels(rules, "Higher Brent crude lifts 10-year yields.", region="US") == {
        ("link", "oil.brent", "us_treasuries.yield_10y")}


def test_help_takes_the_sign_of_the_verb_it_helps(rules):
    def effect(text):
        claims, _ = claims_of_chunk(rules, 0, text, Reading())
        return [f.effect for f in claims.found if f.type == "link"]
    assert effect("Lower Brent crude would help moderate Fed rate hikes.") == [0.3]
    assert effect("Lower Brent crude would help lift Fed rate hikes.") == [-0.3]
    assert effect("Lower Brent crude would help stabilise Fed rate hikes.") == [-0.3]


@pytest.mark.parametrize("text", [
    "We push back on the notion that a stronger yen lifts Toyota's operating profit.",   # a view doubted
    "Measures to support the yen lifted Toyota's operating profit.",                     # the yen is an aim's object
    "Fed rate hikes follow a 25bp increase in 2-year Treasury yields.",                  # a causal word as a noun
    "US 10-year yields are 5bp lower than 2-year Treasury yields.",                      # "lower" as a predicate
    "Higher 30-year yields lift Tokio Marine.",                                          # yields of a tenor not modelled
    "Higher yields lift Komatsu.",                                                       # no link from any yield
    "Japanese insurers lift JGB yields.",                                                # a sector is moved, not mover
    "Higher JGB yields lift Korean insurers.",                                           # no such region's sector
    "Higher JGB yields lift Chinese insurers.",                                          # no such company in the model
    "Lower ECB deposit rates may lead to UniCredit net interest income.",                # led where?
    "Following the BoJ meeting, the yen rose 3%.",                                       # no direction for the event
    "Following the BoJ's rate hike, the yen could rise.",                                # a supposition
    "Following the BoJ's rate hike the yen rose.",                                       # no clause to read
    "The BoJ and help stabilise JGBs.",
    "USD/JPY fell 2% after the BoJ meeting.",                                            # an event with no direction
    "As of today, the yen rose and Japan equities fell.",
    "The yen strengthened, Japan equities fell.",                                        # the verb has no object
])
def test_no_causal_claim(rules, text):
    assert channels(rules, text) == set()


@pytest.mark.parametrize("text,want", [
    # a report of what happened claims the directions on both sides; a mechanism claims neither
    ("A weaker yen lifted Toyota's operating profit.",
     [("move", "dollar_yen.usd_jpy", 0.5, "standardized"), ("move", "toyota.operating_profit", 0.5, "standardized")]),
    ("A weaker yen lifts Toyota's operating profit.", []),
    ("Toyota's operating profit rose, thanks to a weaker yen.",
     [("move", "toyota.operating_profit", 0.5, "standardized"), ("move", "dollar_yen.usd_jpy", 0.5, "standardized")]),
    ("Toyota's operating profit rose, given a weaker yen.", [("move", "toyota.operating_profit", 0.5, "standardized")]),
    ("Toyota's operating profit rose 5%, thanks to a weaker yen.",
     [("move", "toyota.operating_profit", 0.05, "relative"), ("move", "dollar_yen.usd_jpy", 0.5, "standardized")]),
    # the cause's word is not the effect's ("flat due to weaker demand")
    ("Komatsu's profit was flat due to weaker construction demand.",
     [("move", "komatsu.construction_demand", -0.5, "standardized")]),
    ("The yen appreciated 4%.", [("move", "dollar_yen.usd_jpy", -0.04, "relative")]),
    ("USD/JPY fell amid talk of BoJ tightening.", [("move", "dollar_yen.usd_jpy", -0.5, "standardized")]),
    # a figure before a connector is not the cause's size
    ("USD/JPY fell 2% after the BoJ's rate hike.",
     [("move", "dollar_yen.usd_jpy", -0.02, "relative"), ("move", "boj.policy_rate", 0.5, "standardized")]),
])
def test_moves_in_a_causal_claim(rules, text, want):
    assert [s for s in read(rules, text) if s[0] == "move"] == want


def test_a_values_totals_are_every_value_it_adds_into_once_even_by_two_routes():
    r = object.__new__(Rules)
    r._into = {"a.part": {"a.segment", "a.region"}, "a.segment": {"a.total"}, "a.region": {"a.total"}}
    assert r._totals_of("a.part") == {"a.segment", "a.region", "a.total"}
    assert r._totals_of("a.total") == set()
