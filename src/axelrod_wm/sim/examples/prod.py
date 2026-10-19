"""The production demo's examples: the small demo's features, one for one, in a busier world.

The world is the oil-shock demo's: 53 actors and ideas, 22 admitted superentities, and three years of synthetic
history (811 recallable days). Each example shows the same feature as its small-demo twin, so the two can be shown
side by side: what a feature does on a blank canvas, and what it does among everything else the model knows.

All articles and data are synthetic. Real company and agency names appear only in neutral items; SkyBridge Air,
Northwind Airways, Alpenflug, and Lumen Silicon are illustrative firms, made up for the demo.
"""

from __future__ import annotations

from typing import Any

from axelrod_wm.sim.examples.catalog import (
    Article,
    Catalog,
    Example,
    LibraryEvent,
    Step,
    dyn,
    entity,
    find_link,
    link,
    move,
    observe,
    reweight,
    value,
)
from axelrod_wm.sim.examples.small import EXAMPLES as SMALL_EXAMPLES

OIL = "resources_energy.oil_price"
CPI = "inflation.headline_cpi"
FED = "federal_reserve.policy_stance"
BOJ = "boj.policy_stance"


def _airline(eid: str, name: str, region: str, short: str, levels: tuple[float, float, float], aliases: list[str]) -> list[dict]:
    fuel, margin, price = levels
    return [entity(eid, name, "company", ["SD"], {"sector": "airlines", "region": region}, aliases),
            value(eid, "fuel_cost", f"{short} jet fuel cost", "cost_index", "$/gal", "lognormal", fuel, 0.08),
            value(eid, "operating_margin", f"{short} operating margin", "margin", "pct", "gaussian", margin, 2.0),
            value(eid, "share_price", f"{short} share price", "asset_price", "$", "lognormal", price, 0.08),
            link(OIL, f"new:{eid}.fuel_cost", "raises", 1),
            link(f"new:{eid}.fuel_cost", f"new:{eid}.operating_margin", "squeezes", -1),
            link(f"new:{eid}.operating_margin", f"new:{eid}.share_price", "drives", 1)]


def _jet_fuel(ctl: Any, at: Any) -> list[dict]:
    return [entity("jet_fuel", "Jet fuel (Gulf Coast)", "market", ["SC"], aliases=["jet fuel", "kerosene"]),
            value("jet_fuel", "price", "Jet fuel price (Gulf Coast)", "commodity_price", "$/gal", "lognormal", 2.5, 0.09)]


def _lumen(ctl: Any, at: Any) -> list[dict]:
    return [entity("lumen", "Lumen Silicon (illustrative)", "company", ["SC"], {"sector": "semiconductors", "region": "US"},
                   ["Lumen"]),
            value("lumen", "revenue", "Lumen revenue", "revenue_flow", "$bn/qtr", "lognormal", 2.0, 0.08),
            value("lumen", "operating_margin", "Lumen operating margin", "margin", "pct", "gaussian", 18.0, 3.0),
            value("lumen", "share_price", "Lumen share price", "asset_price", "$", "lognormal", 60.0, 0.1),
            link("new:lumen.revenue", "new:lumen.operating_margin", "lifts", 1, dyn(0.4, 30, 90)),
            link("new:lumen.operating_margin", "new:lumen.share_price", "drives", 1, dyn(0.5, 1, 14))]


def _ai_spend(ctl: Any, at: Any) -> list[dict]:
    fuzzy = {"kind": "abstract", "generalization_id": "gen:obj:cloud_platform", "attribute_kind": "spending_flow",
             "mention": "cloud platforms' AI spending"}
    return [link(fuzzy, "amd.datacenter_revenue", "buys accelerators from", 1, dyn(0.4, 30, 90))]


def _opec_cut(ctl: Any, at: Any) -> list[dict]:
    return [move(OIL, 0.2, at)]


def _carry_note(ctl: Any, at: Any) -> list[dict]:
    return [value("yen_carry", "funding_stress", "Carry funding stress", "stress_index", "index", "gaussian", 0.0, 1.0,
                  new_entity=False),
            link("yen_carry.usd_jpy", "new:yen_carry.funding_stress", "a falling dollar-yen raises", -1, dyn(-0.6, 1, 5)),
            link("new:yen_carry.funding_stress", "asset_prices.equity_volatility", "lifts", 1, dyn(0.5, 1, 7)),
            link("new:yen_carry.funding_stress", "nvidia.share_price", "weighs on", -1, dyn(-0.3, 1, 7)),
            link("new:yen_carry.funding_stress", "tokyo_electron.share_price", "weighs on", -1, dyn(-0.3, 1, 7))]


def _cpi(ctl: Any, at: Any) -> list[dict]:
    return [observe(CPI, 3.6, at)]


def _skybridge(ctl: Any, at: Any) -> list[dict]:
    return _airline("skybridge", "SkyBridge Air (illustrative)", "US", "SkyBridge", (2.6, 8.0, 30.0), ["SkyBridge"])


def _fed_hike(ctl: Any, at: Any) -> list[dict]:
    return [move(FED, 0.25, at, mode="absolute")]


def _second_shock(ctl: Any, at: Any) -> list[dict]:
    return [move(OIL, 0.12, at)]


def _vague(ctl: Any, at: Any) -> list[dict]:
    fuzzy = {"kind": "abstract", "candidate_entity_ids": ["delta", "united_airlines", "skybridge"],
             "attribute_kind": "margin", "mention": "a US carrier"}
    return [link(OIL, fuzzy, "squeezes", -1, dyn(-0.4, 7, 30))]


def _hedges_end(ctl: Any, at: Any) -> list[dict]:
    return [observe("skybridge.fuel_cost", 2.9, at)]


def _resolve(ctl: Any, at: Any) -> list[dict]:
    return [observe("skybridge.operating_margin", 3.0, at)]


def _guidance(ctl: Any, at: Any) -> list[dict]:
    return [observe("skybridge.operating_margin", 2.0, at)]


def _weaken(ctl: Any, at: Any) -> list[dict]:
    iid = find_link(ctl, OIL, "productivity_tech.tfp_growth")
    return [reweight(iid, False, 0.6)] if iid else []


def _climb(ctl: Any, at: Any) -> list[dict]:
    return [move(OIL, 0.06, at)]


def _fuel_index(ctl: Any, at: Any) -> list[dict]:
    return [observe("delta.fuel_cost", 3.0, at)]


def _fares_begin(ctl: Any, at: Any) -> list[dict]:
    return [value("delta", "avg_fare", "Delta average fare", "asset_price", "$", "lognormal", 250.0, 0.05,
                  aliases=["fare"], new_entity=False),
            observe("new:delta.avg_fare", 250.0, at)]


def _fare(v: float):
    return lambda ctl, at: [observe("delta.avg_fare", v, at)]


def _northwind(ctl: Any, at: Any) -> list[dict]:
    return _airline("northwind", "Northwind Airways (illustrative)", "US", "Northwind", (2.6, 7.0, 20.0), ["Northwind"])


def _alpenflug(ctl: Any, at: Any) -> list[dict]:
    return _airline("alpenflug", "Alpenflug (illustrative)", "EU", "Alpenflug", (2.7, 6.0, 15.0), ["Alpenflug"])


def _oil_fall(ctl: Any, at: Any) -> list[dict]:
    return [move(OIL, -0.15, at)]


def _quota_up(ctl: Any, at: Any) -> list[dict]:
    return [move("opec_plus.quota", 0.03, at)]


def _chip_rules(ctl: Any, at: Any) -> list[dict]:
    return [move("us_commerce.chip_rule_stringency", 1.5, at, mode="standardized")]


def _cpi_cool(ctl: Any, at: Any) -> list[dict]:
    return [observe(CPI, 3.0, at)]


def _boj_hike(ctl: Any, at: Any) -> list[dict]:
    return [move(BOJ, 0.25, at, mode="absolute")]


def _rumor(ctl: Any, at: Any) -> list[dict]:
    return [link(OIL, "delta.share_price", "lifts", 1, dyn(0.5, 1, 7))]


def _third_shock(ctl: Any, at: Any) -> list[dict]:
    return [move(OIL, 0.10, at)]


OPS = {"jet_fuel": _jet_fuel, "lumen": _lumen, "ai_spend": _ai_spend, "opec_cut": _opec_cut, "carry_note": _carry_note,
       "cpi": _cpi, "skybridge": _skybridge, "fed_hike": _fed_hike, "second_shock": _second_shock, "vague": _vague,
       "resolve": _resolve, "guidance": _guidance, "hedges_end": _hedges_end, "weaken": _weaken, "climb": _climb, "fuel_index": _fuel_index, "fares_begin": _fares_begin,
       "oil_up": lambda c, a: [move(OIL, 0.08, a)], "oil_down": lambda c, a: [move(OIL, -0.08, a)],
       "fare_up": _fare(264.0), "fare_down": _fare(244.0), "fare_up2": _fare(296.0), "fare_down2": _fare(208.0),
       "northwind": _northwind, "alpenflug": _alpenflug, "oil_fall": _oil_fall, "quota_up": _quota_up,
       "chip_rules": _chip_rules, "cpi_cool": _cpi_cool, "boj_hike": _boj_hike, "rumor": _rumor,
       "third_shock": _third_shock}


def _edit_group(ctl: Any, by: str) -> Any:
    return ctl.propose_group("AI buildout", ["microsoft", "nvidia"], pattern_id="SE-AI", by=by,
                             description="A cloud platform's AI spending is a chipmaker's data-center revenue.")


def _edit_nest(ctl: Any, by: str) -> Any:
    return ctl.propose_group("AI compute", [], parts=["SE-AI", "S12"], pattern_id="SE-NEST", by=by,
                             description="The AI buildout and the GPU rivalry share NVIDIA: cloud spending sets the "
                                         "prize the two chipmakers compete for.")


def _edit_dissolve(ctl: Any, by: str) -> Any:
    return ctl.propose_dissolve("SE-NEST", "show its two parts as themselves again", by=by)


def _edit_dissolve_provided(ctl: Any, by: str) -> Any:
    return ctl.propose_dissolve("S15", "it no longer earns its place: delete it, keep its members", by=by)


def _edit_retire(ctl: Any, by: str) -> Any:
    from axelrod_wm.control.controller import ControllerError

    iid = find_link(ctl, OIL, "productivity_tech.tfp_growth")
    if iid is None:
        raise ControllerError("there is no Oil price → TFP growth link to retire")
    return ctl.propose_retire(interaction_id=iid, reason="the study found no direct effect", by=by)


def _edit_retire_northwind(ctl: Any, by: str) -> Any:
    return ctl.propose_retire(entity_id="northwind", reason="the airline stopped flying (illustrative)", by=by)


EDITS = {"group": _edit_group, "nest": _edit_nest, "dissolve": _edit_dissolve, "dissolve_provided": _edit_dissolve_provided, "retire": _edit_retire,
         "retire_northwind": _edit_retire_northwind}


def A(headline: str, body: str = "", quotes: list | None = None, rationale: str = "", **kw: Any) -> Article:
    return Article(headline=headline, body=body, quotes=quotes or [], rationale=rationale, **kw)


def _twin(key: str, **kw: Any) -> Example:
    """The small demo's example `key`, with this world's articles and edits."""
    return next(e for e in SMALL_EXAMPLES if e.id == key).model_copy(update=kw)


EXAMPLES: list[Example] = [
    _twin("create", summary="The article introduces Gulf Coast jet fuel as a market of its own. One entity and one value; the "
                     "classifier sorts it among the world's supply factors.",
          watch=["Items: a new entity and a new value", "Lessons: a concept gains the new market"],
          steps=[Step(ops="jet_fuel", article=A(
              "Gulf Coast jet fuel becomes a benchmark of its own",
              "Traders now quote Gulf Coast jet fuel as its own market, near $2.50 a gallon.",
              [("Gulf Coast jet fuel", [0]), ("near $2.50 a gallon", [1])],
              "A market the model has not tracked: an entity and the value the article reports.",
              mentions=["jet fuel"], event_type="market_entry"))]),
    _twin("links", title="A chip designer and the links inside it", summary="Lumen Silicon, a chip designer made up for the demo, arrives with revenue, a margin, a share price, "
                     "and the two links between them. It is sorted among the seven chipmakers the model already knows.",
          watch=["Items: one entity, three values, two interactions", "Lessons: “Chipmaker” gains Lumen"],
          steps=[Step(ops="lumen", article=A(
              "Lumen Silicon lists its shares (illustrative)",
              "Lumen Silicon, a US chip designer made up for the demo, earns its margin on revenue, and investors price "
              "its shares off that margin.",
              [("Lumen Silicon", [0]), ("earns its margin on revenue", [1, 2, 4]),
               ("price its shares off that margin", [3, 5])],
              "One entity, its three values, and the two mechanisms inside it.", mentions=["Lumen"],
              event_type="market_entry"))]),
    _twin("refine", title="A fuzzy mention, refined to one value", summary="The article says “cloud platforms' AI spending” lifts AMD's data-center sales. The end starts at a "
                     "concept, cloud platforms; the refiner narrows it, and because the mention contains “AI spending”, "
                     "a name for Microsoft's AI capital spending (the one cloud platform the model knows), the article "
                     "names that value outright and the end binds instead of hedging.",
          watch=["Intake: the refinement steps, ending at a value the article names",
                 "Items: Microsoft AI capex → AMD data-center revenue"],
          steps=[Step(ops="ai_spend", article=A(
              "Cloud platforms' AI spending lifts chip designers' data-center sales",
              "Analysts expect cloud platforms' AI spending to flow to AMD's data-center business within a quarter.",
              [("cloud platforms' AI spending to flow to AMD's data-center business", [0])],
              "One link from a fuzzy end (“cloud platforms' AI spending”) to a value.", kind="analyst",
              source="Synthetic research note", mentions=["cloud", "AI spending", "AMD"], event_type="analysis"))]),
    _twin("ripple", summary="Brent jumps 20%. In this world the move reaches dozens of values: airline fuel costs and margins, "
                     "energy producers' revenue, inflation and through it the Fed. Check each order, not only the first.",
          watch=["Ripple: airlines and producers at first order", "The Fed at second or third order"],
          steps=[Step(ops="opec_cut", article=A(
              "OPEC+ announces a surprise cut; Brent jumps 20%",
              "Producers announced a surprise output cut, and Brent rose 20% over the week.",
              [("Brent rose 20%", [0])], "A step of +20% in the oil price.", mentions=["OPEC+", "Brent"],
              event_type="supply_shock"))]),
    _twin("expert_add", summary="You have run airline revenue for years, and you know something the model's sources have not said: "
                      "how many people want to fly drives the traffic both large US carriers report. Open the form, add "
                      "Air travel demand with a monthly US passenger count (prefilled: about 80 million, give or take "
                      "6%), and interactions from it to Delta's and United's passenger traffic, at 70% confidence. It is "
                      "staged and reviewed like any article.",
          watch=["The form: an entity, a value with its typical level and spread, two interactions, your confidence",
                 "Items: Air travel demand, US air passengers, and its two interactions, at your 70%"],
          manual={"entity": {"id": "air_travel", "name": "Air travel demand", "kind": "macro_factor", "tags": ["SD"],
                             "aliases": ["air travel", "travel demand", "passenger demand"]},
                  "values": [{"slug": "passengers", "name": "US air passengers", "attribute_kind": "traffic_flow",
                              "unit": "m/month", "family": "lognormal", "typical": 80.0, "spread": 0.06}],
                  "interactions": [{"source": "new:passengers", "target": "delta.passenger_traffic", "label": "fills seats for",
                                    "polarity": 1, "effect": 0.5, "delay_days": 7, "lag_days": 30},
                                   {"source": "new:passengers", "target": "united_airlines.passenger_traffic",
                                    "label": "fills seats for", "polarity": 1, "effect": 0.5, "delay_days": 7,
                                    "lag_days": 30}],
                  "confidence": 0.7,
                  "note": "From years in airline revenue management: national demand fills both carriers' planes."}),
    _twin("select", title="Five new items: keep only some", summary="A note adds a new value to the yen carry trade, funding stress, and four links: a falling dollar-yen "
                     "raises it, and it lifts equity volatility and weighs on two chip stocks. Deselect the new value and "
                     "every link goes with it.",
          watch=["Items: five, four of them needing the new value", "The canvas: the new links, dashed"],
          steps=[Step(ops="carry_note", article=A(
              "Strategists: a carry unwind would hit chip stocks first",
              "When the dollar falls against the yen, carry traders' funding stress rises; that stress lifts equity "
              "volatility and weighs on chip stocks such as NVIDIA and Tokyo Electron.",
              [("carry traders' funding stress", [0]), ("When the dollar falls against the yen", [1]),
               ("lifts equity volatility", [2]), ("NVIDIA", [3]), ("Tokyo Electron", [4])],
              "A new value and the four mechanisms the note describes.", kind="analyst",
              source="Synthetic research note", mentions=["yen", "carry", "NVIDIA"], event_type="analysis"))]),
    _twin("fold", summary="A month after the oil shock, CPI comes in at 3.6%. The fold updates inflation and the effects that "
                     "feed it, weighted by how active each was: oil's link most of all.",
          watch=["Learned: CPI's value and the effects into it"],
          steps=[Step(ops="cpi", days=29, article=A(
              "CPI rises to 3.6% y/y", "Consumer prices rose 3.6% from a year earlier, led by energy.",
              [("rose 3.6%", [0])], "A reported value: headline CPI at 3.6%.", kind="data",
              source="Synthetic statistics release", mentions=["CPI"], event_type="data_release"))]),
    _twin("inherit", summary="SkyBridge Air (made up) arrives with an airline's values and links but no effect sizes. Its links "
                     "start from what the concepts pooled from Delta and United, and from three years of history.",
          watch=["Items: SkyBridge, its values, three links", "Lessons: “Airline” gains SkyBridge"],
          steps=[Step(ops="skybridge", article=A(
              "SkyBridge Air, a low-cost carrier, starts US routes (illustrative)",
              "SkyBridge Air buys jet fuel like any airline, and its margin and shares move with it. The airline is made "
              "up for the demo.",
              [("SkyBridge Air", [0]), ("buys jet fuel like any airline", [1, 4]), ("its margin", [2, 5]),
               ("shares", [3, 6])], "A new airline; the concepts supply the sizes.", mentions=["SkyBridge"],
              event_type="market_entry"))]),
    _twin("expert_link", summary="Your demand idea is on its own: nothing in the model moves it. From experience, tighter money "
                       "cools discretionary travel within a quarter or two, but you are only half sure. Add one "
                       "interaction from the Fed's policy stance to US air passengers (prefilled: it lowers them, about a "
                       "quarter of a standard unit per standard unit, after a month), at 50% confidence. From now on, a "
                       "rate move reaches the airlines' traffic through your idea too.",
          watch=["The form: one interaction between existing values, its size and timing, your 50%",
                 "Items: Fed policy stance → US air passengers, at your 50%"],
          manual={"values": [], "interactions": [{"source": FED, "target": "air_travel.passengers", "label": "cools",
                                                  "polarity": -1, "effect": -0.25, "delay_days": 30, "lag_days": 60}],
                  "confidence": 0.5,
                  "note": "Tighter money cools discretionary travel within a quarter or two."}),
    _twin("memory", summary="The Fed raises its rate a quarter point with inflation hot. Its entity memory already holds three "
                     "years of decisions; this one is added under the same context.",
          watch=["Lessons: the Fed's entity memory records “raised”",
                 "Ripple: the US policy rate first, then real rates, bank funding costs, JPMorgan's margin, and credit; "
                 "and through your air travel demand to the airlines' traffic"],
          steps=[Step(ops="fed_hike", article=A(
              "The Fed raises its policy rate by a quarter point",
              "Citing inflation well above target, the Federal Reserve raised its policy rate by 25 basis points.",
              [("raised its policy rate by 25 basis points", [0])], "A decision by an actor: +0.25 points.",
              mentions=["Fed"], event_type="policy_decision"))]),
    _twin("analog", summary="Brent jumps again. Recall searches three years of days for the most similar ones, and what followed "
                     "them adjusts the effects before the ripple is simulated.",
          watch=["Recalled: past days like this one", "Adjusted: effects that moved after those days, such as the Fed's reaction "
                 "to CPI and airlines' margins"],
          steps=[Step(ops="second_shock", article=A(
              "Brent climbs 12% on a new supply scare", "A pipeline outage pushed Brent up 12% in two days.",
              [("pushed Brent up 12%", [0])], "Another step in the oil price.", mentions=["Brent"],
              event_type="supply_shock"))]),
    _twin("pending", summary="Fuel costs squeeze “a US carrier's” margin, unnamed. Three airlines fit, so the end is hedged: "
                     "a soft interaction to each margin, as strong as it is probable, and a share for a carrier not in "
                     "the graph yet. Every forecast hedges across them until evidence settles it.",
          watch=["Items: three fuzzy candidates, Delta, United, and SkyBridge, with a third of the weight kept for a carrier "
                 "not in the graph", "The canvas: one fuzzy interaction fanning to the three margins"],
          steps=[Step(ops="vague", article=A(
              "Fuel hedges are running out at a US carrier",
              "Analysts say a US carrier's fuel hedges are expiring, so oil will now squeeze its margin directly. The "
              "note does not name the airline.",
              [("oil will now squeeze its margin", [0])], "A link to “a US carrier's” margin: three airlines fit.",
              kind="analyst", source="Synthetic research note", mentions=["a US carrier"], event_type="analysis"))]),
    _twin("resolve", summary="Among three candidates the evidence has to do more. SkyBridge (made up) says its fuel hedges have "
                      "run out, which names it; oil climbs; then SkyBridge reports its margin falling, the way the "
                      "interaction predicts. Three checks carry SkyBridge past the bound, and the model proposes the "
                      "resolution: keep SkyBridge, retire Delta's and United's soft interactions.",
          watch=["The proposal: a refinement, keep SkyBridge, retire its two rivals' soft interactions"],
          steps=[Step(ops="hedges_end", days=2, article=A(
              "SkyBridge Air says its fuel hedges have run out (illustrative)",
              "SkyBridge Air said it no longer hedges fuel; its jet fuel cost rose to $2.90 a gallon.",
              [("its jet fuel cost rose to $2.90 a gallon", [0])], "A reported value for SkyBridge; the article names it.",
              kind="filing", source="Synthetic filing", mentions=["SkyBridge"], event_type="earnings")),
                 Step(ops="climb", days=10, article=A(
              "Brent edges up another 6%", "Oil rose again on tighter supply.", [("up another 6%", [0])],
              "A step in the oil price.", mentions=["Brent"], event_type="supply_shock")),
                 Step(ops="resolve", days=4, article=A(
              "SkyBridge Air's operating margin falls to 3% (illustrative)",
              "With fuel unhedged and oil high, SkyBridge Air reported an operating margin of 3%.",
              [("operating margin of 3%", [0])], "A reported value for SkyBridge's margin.", kind="filing",
              source="Synthetic filing", mentions=["SkyBridge"], event_type="earnings")),
                 # Oct 17: the busier world asks three articles of evidence (recognition 3), not two as the small demo
                 Step(ops="guidance", days=3, article=A(
              "SkyBridge Air cuts its margin outlook to 2% as fuel bites (illustrative)",
              "SkyBridge Air now expects an operating margin of 2% for the year, citing unhedged fuel costs.",
              [("an operating margin of 2%", [0])], "A further reported value for SkyBridge's margin.", kind="filing",
              source="Synthetic filing", mentions=["SkyBridge"], event_type="earnings"))]),
    _twin("weaken", summary="A study finds little sign that oil moves productivity growth. The belief that the link exists "
                      "falls, so it carries less of every later ripple.",
          steps=[Step(ops="weaken", article=A(
              "Study: oil prices explain little of productivity growth",
              "New research finds no clear effect of oil prices on productivity growth.",
              [("no clear effect of oil prices on productivity growth", [0])], "Evidence against Oil → TFP growth.",
              kind="analyst", source="Synthetic research note", mentions=["oil", "productivity"],
              event_type="analysis"))]),
    _twin("superentity", summary="Weeks pass while oil keeps climbing, and Delta reports its fuel cost index. In this world the "
                      "interactions that carry oil from its producers to an airline's fuel bill fire together day after "
                      "day; once their support crosses the threshold the model proposes them as a superentity: Oil, "
                      "ExxonMobil and Saudi Aramco on the supply side, and Delta's jet fuel cost.",
          watch=["The proposal: a collapse, raised by the model",
                 "The members: Resources, energy (oil), ExxonMobil, Saudi Aramco, and Delta"],
          steps=[Step(ops="climb", days=14, article=A(
              "Brent edges up another 6%", "Oil kept rising through the month.", [("up another 6%", [0])],
              "A smaller step in the oil price.", mentions=["Brent"], event_type="supply_shock")),
                 Step(ops="fuel_index", days=7, article=A(
              "Delta's jet fuel cost index rises to $3.00 a gallon",
              "The airline's fuel cost index rose with crude.", [("rises to $3.00 a gallon", [0])],
              "A reported value for Delta's fuel cost.", kind="data", source="Synthetic statistics release",
              mentions=["Delta", "jet fuel"], event_type="data_release"))]),
    _twin("correlate", summary="Delta starts reporting its average fare. After a quiet month and a half, oil rises and the fare "
                      "surprises upward, then oil falls and the fare surprises downward. Among many candidate sources the "
                      "frontier pairs oil with the fare; the second check it passes adds support and tightens the "
                      "correlation. Nothing is proposed yet.",
          steps=[Step(ops="fares_begin", article=A(
              "Delta starts publishing its average fare", "Delta's average fare was $250 last month.",
              [("average fare", [0]), ("$250", [1])], "A new value for Delta, and its first report.", kind="filing",
              source="Synthetic filing", mentions=["Delta", "fare"], event_type="earnings")),
              *[Step(ops=o, days=d, article=A(h, b, [(q, [0])], r, kind=k, source=src, mentions=m, event_type=et))
                for o, d, h, b, q, r, k, src, m, et in [
                  ("oil_up", 45, "Brent rises 8%", "Oil rose on tighter supply.", "rose", "A step in the oil price.",
                   "news", "Synthetic newswire", ["Brent"], "supply_shock"),
                  ("fare_up", 2, "Delta's average fare rises to $264", "Fares rose faster than expected.", "rises to $264",
                   "A fare report.", "data", "Synthetic statistics release", ["Delta", "fare"], "data_release"),
                  ("oil_down", 12, "Brent falls 8%", "Oil fell as supply returned.", "fell", "A step down in the oil price.",
                   "news", "Synthetic newswire", ["Brent"], "supply_shock"),
                  ("fare_down", 2, "Delta's average fare falls to $244", "Fares fell faster than expected.",
                   "falls to $244", "A fare report.", "data", "Synthetic statistics release", ["Delta", "fare"],
                   "data_release")]]]),
    _twin("frontier", summary="Oil rises and falls once more, and the fare follows each time. The pair has now held at enough "
                      "spaced checks, so the frontier proposes oil → fare as a learned interaction, for a person to judge.",
          watch=["The proposal: a learned link, raised by the model",
                 "Its evidence: four paired moves on one line (rise, fall, rise, fall)"],
          steps=[Step(ops=o, days=d, article=A(h, b, [(q, [0])], r, kind=k, source=src, mentions=m, event_type=et))
                 for o, d, h, b, q, r, k, src, m, et in [
                  ("oil_up", 12, "Brent rises 8% again", "Oil rose again.", "rose again", "A step in the oil price.",
                   "news", "Synthetic newswire", ["Brent"], "supply_shock"),
                  ("fare_up2", 2, "Delta's average fare rises to $296", "Fares rose again, by more than before.", "rises to $296",
                   "A fare report.", "data", "Synthetic statistics release", ["Delta", "fare"], "data_release"),
                  ("oil_down", 12, "Brent falls 8% again", "Oil fell again.", "fell again", "A step down in the oil price.",
                   "news", "Synthetic newswire", ["Brent"], "supply_shock"),
                  ("fare_down2", 2, "Delta's average fare falls to $208", "Fares fell again, by more than before.", "falls to $208",
                   "A fare report.", "data", "Synthetic statistics release", ["Delta", "fare"], "data_release")]]),
    _twin("split", summary="Northwind (US) and Alpenflug (Europe), both made up, join Delta, United, and SkyBridge. Four US "
                      "airlines share a region the Airline concept does not require, so they split off into a concept of their "
                      "own.",
          watch=["Lessons: a new concept, “Airline (region=US)”", "Its members: the four US airlines"],
          steps=[Step(ops="northwind", article=A(
              "Northwind Airways adds routes in the Midwest (illustrative)",
              "Northwind Airways, a US regional carrier made up for the demo, buys jet fuel like its rivals.",
              [("Northwind Airways", [0])], "Another US airline.", mentions=["Northwind"], event_type="market_entry")),
                 Step(ops="alpenflug", article=A(
              "Alpenflug opens a transatlantic route (illustrative)",
              "Alpenflug, a European airline made up for the demo, starts flying to New York.",
              [("Alpenflug", [0])], "An airline from another region.", mentions=["Alpenflug"],
              event_type="market_entry"))]),
    _twin("collapse", title="Collapse: a backend user groups two firms", edit="group",
          summary="A backend user groups Microsoft and NVIDIA into one superentity, the AI buildout. Approved, it is "
                  "admitted beside the 22 the model already holds.",
          watch=["Items: one collapse", "Lessons: the superentity is admitted"]),
    _twin("nest", summary="The AI buildout and the GPU rivalry the world came with share NVIDIA. A backend user nests both "
                          "in one superentity, AI compute: closed, it is one card; opened, it shows its two parts, and "
                          "each part opens into its firms."),
    _twin("expand", edit="dissolve", summary="The backend user dissolves AI compute; its two parts, the AI buildout and the "
                                       "GPU rivalry, show as themselves again, and the pattern stays in long-term memory, "
                                       "dissolved."),
    _twin("retire_superentity", title="Revision: delete a superentity the world came with", edit="dissolve_provided",
          summary="The world arrived with 22 superentities. One of them, Airlines (Delta and United trading travelers "
                  "and sharing fuel costs), was provided by construction rather than learned. A backend user deletes "
                  "it; the two airlines stay as themselves, and the pattern is kept, dissolved, with its history.",
          watch=["Items: one expansion of a provided superentity", "Lessons: “Airlines” is dissolved"]),
    _twin("delete", edit="retire", summary="After the study, the backend user retires the link from oil to productivity growth. "
                                     "The log keeps its whole history."),
    _twin("inference", summary="Ask what happens if Brent rises 30% next quarter. The forecast runs on a branch of the committed "
                      "version, by order and transmission path, across the whole world; the model does not change."),
]

LIBRARY: list[LibraryEvent] = [
    LibraryEvent(id="oil-falls", feature="ripple", title="Brent falls 15%", after="ripple", step=Step(
        ops="oil_fall", article=A("Brent falls 15% as output returns", "Producers restored output, and Brent fell 15%.",
                                  [("Brent fell 15%", [0])], "A step down in the oil price.", mentions=["Brent"],
                                  event_type="supply_shock"))),
    LibraryEvent(id="quota-up", feature="ripple", title="OPEC+ raises its quota", after="ripple", step=Step(
        ops="quota_up", article=A("OPEC+ raises its output quota by 3%", "The producers' group raised its quota by 3%.",
                                  [("raised its quota by 3%", [0])], "A move one order up the chain, at the quota.",
                                  mentions=["OPEC+"], event_type="policy_decision"))),
    LibraryEvent(id="chip-rules", feature="ripple", title="Chip export rules tighten", after="ripple", step=Step(
        ops="chip_rules", article=A("Chip export rules tighten (synthetic)",
                                    "The Commerce Department widened its chip export rules.",
                                    [("widened its chip export rules", [0])],
                                    "A move in rule stringency: a ripple through the chipmakers.",
                                    mentions=["export controls", "chips"], event_type="regulatory_action"))),
    LibraryEvent(id="cpi-cools", feature="observation", title="CPI eases to 3.0%", after="fold", step=Step(
        ops="cpi_cool", article=A("CPI eases to 3.0% y/y", "Consumer prices rose 3.0% from a year earlier.",
                                  [("rose 3.0%", [0])], "A reported value.", kind="data",
                                  source="Synthetic statistics release", mentions=["CPI"], event_type="data_release"))),
    LibraryEvent(id="boj-hikes", feature="decision", title="The BoJ raises its rate", after="memory", step=Step(
        ops="boj_hike", article=A("The Bank of Japan raises its policy rate by a quarter point",
                                  "The Bank of Japan raised its policy rate by 25 basis points.",
                                  [("raised its policy rate by 25 basis points", [0])],
                                  "Another central bank's decision, for its own memory.", mentions=["BoJ"],
                                  event_type="policy_decision"))),
    LibraryEvent(id="third-shock", feature="analogs", title="A third oil shock", after="analog", step=Step(
        ops="third_shock", article=A("Brent rises 10% as inventories fall", "Crude inventories fell, and Brent rose 10%.",
                                     [("Brent rose 10%", [0])], "Another step in the oil price.", mentions=["Brent"],
                                     event_type="supply_shock"))),
    LibraryEvent(id="rumor", feature="selection", title="A rumor to reject", after="ripple", step=Step(
        ops="rumor", article=A("Rumor: higher oil will lift Delta's shares (illustrative)",
                               "An anonymous post claims that higher oil prices will lift airline shares.",
                               [("higher oil prices will lift airline shares", [0])],
                               "A claim with no mechanism behind it: a link the reviewer should reject.",
                               source="Synthetic forum post", mentions=["oil", "Delta"], event_type="rumor"))),
    LibraryEvent(id="retire-northwind", feature="deletion", title="Northwind stops flying", after="split",
                 edit="retire_northwind"),
    LibraryEvent(id="ask-yen", feature="inference", title="What if the yen rose by 10% next month?",
                 after="select", question="What if the yen rose by 10% next month?"),
]

PROD = Catalog(name="prod", examples=EXAMPLES, library=LIBRARY, ops=OPS, edits=EDITS)

__all__ = ["PROD"]
