"""The small demo's examples: a blank canvas built up one feature at a time.

Each example shows one feature of the framework through one or more sample articles. They form a chain: oil, then
an airline, the link between them, a shock, the macro side, an observation, and so on, until the graph is busy
enough for long-term memory to find structure on its own (a superentity, a co-movement, a kind that splits).

    working memory     1 create · 2 internal links · 4 ripple · 7 fold · 14 weaken a link · 23 delete a link
    intake             3 refine a fuzzy end · 12 an ambiguous end waits
    your own knowledge 5 add an entity from experience · 9 connect it to the rest
    long-term memory   8 inherit priors · 10 entity memory · 11 analogs · 13 a later article resolves an end ·
                       15 a recurring group is proposed · 16 a correlation gains strength · 17 a co-movement is
                       proposed · 18 a kind splits · 19 collapse · 20 nest superentities · 21 expand · 22 delete a
                       superentity the model made
    review             6 keep only some of seven items
    inference          24 a what-if question

Each title names the idea the example tests ("Analogy: a new shock recalls an old one").

All articles and data are synthetic. Delta Air Lines appears only in neutral items; SkyBridge Air, Northwind Airways,
and Alpenflug are illustrative airlines, made up for the demo.
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

FED_RATE = "federal_reserve.policy_rate"
OIL = "resources_energy.oil_price"
CPI = "inflation.headline_cpi"


def _airline(eid: str, name: str, region: str, short: str, levels: tuple[float, float, float], aliases: list[str],
             links: bool = True, dynamics: bool = False) -> list[dict]:
    fuel, margin, price = levels
    ops = [entity(eid, name, "company", ["SD"], {"sector": "airlines", "region": region}, aliases),
           value(eid, "fuel_cost", f"{short} jet fuel cost", "cost_index", "$/gal", "lognormal", fuel, 0.08),
           value(eid, "operating_margin", f"{short} operating margin", "margin", "pct", "gaussian", margin, 2.0),
           value(eid, "share_price", f"{short} share price", "asset_price", "$", "lognormal", price, 0.08)]
    if links:
        ops += [link(OIL, f"new:{eid}.fuel_cost", "raises", 1, dyn(0.9, 7, 30) if dynamics else None),
                link(f"new:{eid}.fuel_cost", f"new:{eid}.operating_margin", "squeezes", -1,
                     dyn(-0.6, 14, 60) if dynamics else None),
                link(f"new:{eid}.operating_margin", f"new:{eid}.share_price", "drives", 1,
                     dyn(0.5, 1, 14) if dynamics else None)]
    return ops


# -- the builders: (controller, at) -> operations ------------------------------------------------------
def _oil(ctl: Any, at: Any) -> list[dict]:
    return [entity("resources_energy", "Oil", "market", ["SC"], aliases=["oil", "crude", "Brent"]),
            value("resources_energy", "oil_price", "Oil price (Brent)", "commodity_price", "$/bbl", "lognormal", 75.0,
                  0.08, aliases=["Brent", "crude"])]


def _delta(ctl: Any, at: Any) -> list[dict]:
    ops = _airline("delta", "Delta Air Lines", "US", "Delta", (2.6, 10.0, 55.0), ["Delta"], links=False)
    return ops + [link("new:delta.fuel_cost", "new:delta.operating_margin", "squeezes", -1, dyn(-0.6, 14, 60)),
                  link("new:delta.operating_margin", "new:delta.share_price", "drives", 1, dyn(0.5, 1, 14))]


def _connect(ctl: Any, at: Any) -> list[dict]:
    fuzzy = {"kind": "abstract", "generalization_id": "gen:obj:airline", "attribute_kind": "cost_index",
             "mention": "airlines' jet fuel costs"}
    return [link(OIL, fuzzy, "raises", 1, dyn(0.9, 7, 30))]


def _shock(ctl: Any, at: Any) -> list[dict]:
    return [move(OIL, 0.2, at)]


def _macro(ctl: Any, at: Any) -> list[dict]:
    return [entity("inflation", "Inflation", "macro_factor", ["MF"], aliases=["inflation", "CPI"]),
            value("inflation", "headline_cpi", "Headline CPI (% y/y)", "inflation_rate", "pct y/y", "gaussian", 2.8,
                  0.3, aliases=["CPI"]),
            entity("federal_reserve", "Federal Reserve", "agency", ["MF"], {"function": "monetary_policy", "region": "US"},
                   ["Fed"]),
            value("federal_reserve", "policy_rate", "Fed policy rate", "policy_rate", "pct", "gaussian", 4.25, 0.25,
                  aliases=["policy rate", "target rate"], features={"decision_variable": "true"}),
            link(OIL, "new:inflation.headline_cpi", "raises", 1, dyn(0.4, 14, 60, 270)),
            link("new:inflation.headline_cpi", f"new:{FED_RATE}", "prompts tightening", 1, dyn(0.5, 45, 30)),
            link(f"new:{FED_RATE}", "delta.share_price", "weighs on", -1, dyn(-0.3, 1, 14))]


def _cpi(ctl: Any, at: Any) -> list[dict]:
    return [observe(CPI, 3.4, at)]


def _skybridge(ctl: Any, at: Any) -> list[dict]:
    return _airline("skybridge", "SkyBridge Air (illustrative)", "US", "SkyBridge", (2.6, 8.0, 30.0), ["SkyBridge"])


def _fed_hike(ctl: Any, at: Any) -> list[dict]:
    return [move(FED_RATE, 0.25, at, mode="absolute")]


def _second_shock(ctl: Any, at: Any) -> list[dict]:
    return [move(OIL, 0.12, at)]


def _vague(ctl: Any, at: Any) -> list[dict]:
    fuzzy = {"kind": "abstract", "candidate_entity_ids": ["delta", "skybridge"], "attribute_kind": "margin",
             "mention": "a US carrier"}
    return [link(OIL, fuzzy, "squeezes", -1, dyn(-0.4, 7, 30))]


def _hedges_end(ctl: Any, at: Any) -> list[dict]:
    return [observe("skybridge.fuel_cost", 2.9, at)]


def _resolve(ctl: Any, at: Any) -> list[dict]:
    return [observe("skybridge.operating_margin", 3.0, at)]


def _weaken(ctl: Any, at: Any) -> list[dict]:
    iid = find_link(ctl, FED_RATE, "delta.share_price")
    return [reweight(iid, False, 0.6)] if iid else []


def _climb(ctl: Any, at: Any) -> list[dict]:
    return [move(OIL, 0.06, at)]


def _fuel_index(ctl: Any, at: Any) -> list[dict]:
    return [observe("delta.fuel_cost", 3.0, at)]


def _fares_begin(ctl: Any, at: Any) -> list[dict]:
    return [value("delta", "avg_fare", "Delta average fare", "fare", "$", "lognormal", 250.0, 0.05, aliases=["fare"],
                  new_entity=False),
            observe("new:delta.avg_fare", 250.0, at)]


def _oil_up(ctl: Any, at: Any) -> list[dict]:
    return [move(OIL, 0.08, at)]


def _oil_down(ctl: Any, at: Any) -> list[dict]:
    return [move(OIL, -0.08, at)]


def _oil_step(delta: float):
    return lambda ctl, at: [move(OIL, delta, at)]


def _fare(v: float):
    return lambda ctl, at: [observe("delta.avg_fare", v, at)]


def _northwind(ctl: Any, at: Any) -> list[dict]:
    return _airline("northwind", "Northwind Airways (illustrative)", "US", "Northwind", (2.6, 7.0, 20.0), ["Northwind"])


def _alpenflug(ctl: Any, at: Any) -> list[dict]:
    return _airline("alpenflug", "Alpenflug (illustrative)", "EU", "Alpenflug", (2.7, 6.0, 15.0), ["Alpenflug"])


def _fuel_spike(ctl: Any, at: Any) -> list[dict]:
    return [move("delta.fuel_cost", 0.25, at)]


def _oil_fall(ctl: Any, at: Any) -> list[dict]:
    return [move(OIL, -0.15, at)]


def _cpi_cool(ctl: Any, at: Any) -> list[dict]:
    return [observe(CPI, 3.0, at)]


def _fed_hold(ctl: Any, at: Any) -> list[dict]:
    sub = ctl.engine.wm.graph.subentities.get(FED_RATE)
    return [observe(FED_RATE, round(float(sub.posterior.summary().q50), 2) if sub else 4.5, at)]


def _strengthen(ctl: Any, at: Any) -> list[dict]:
    iid = find_link(ctl, OIL, CPI)
    return [reweight(iid, True, 0.6)] if iid else []


def _rumor(ctl: Any, at: Any) -> list[dict]:
    return [link(OIL, "delta.share_price", "lifts", 1, dyn(0.5, 1, 7))]


def _jet_fuel_market(ctl: Any, at: Any) -> list[dict]:
    return [entity("jet_fuel", "Jet fuel (Gulf Coast)", "market", ["SC"], aliases=["jet fuel", "kerosene"]),
            value("jet_fuel", "price", "Jet fuel price (Gulf Coast)", "commodity_price", "$/gal", "lognormal", 2.5, 0.09),
            link(OIL, "new:jet_fuel.price", "sets most of", 1, dyn(0.95, 2, 10))]


def _cools(ctl: Any, at: Any) -> list[dict]:
    fuzzy = {"kind": "abstract", "attribute_kind": "inflation_rate", "mention": "inflation"}
    return [link(FED_RATE, fuzzy, "cools", -1, dyn(-0.3, 60, 90))]


def _cargo(ctl: Any, at: Any) -> list[dict]:
    return [entity("skyfreight", "SkyFreight Cargo (illustrative)", "company", ["SD"],
                   {"sector": "airlines", "region": "US", "business": "cargo"}, ["SkyFreight"]),
            value("skyfreight", "fuel_cost", "SkyFreight jet fuel cost", "cost_index", "$/gal", "lognormal", 2.6, 0.08),
            link(OIL, "new:skyfreight.fuel_cost", "raises", 1)]


def _third_shock(ctl: Any, at: Any) -> list[dict]:
    return [move(OIL, 0.10, at)]


OPS = {"oil": _oil, "delta": _delta, "connect": _connect, "shock": _shock, "macro": _macro, "cpi": _cpi,
       "skybridge": _skybridge, "fed_hike": _fed_hike, "second_shock": _second_shock, "vague": _vague,
       "resolve": _resolve, "hedges_end": _hedges_end, "weaken": _weaken, "climb": _climb, "fuel_index": _fuel_index,
       "fares_begin": _fares_begin, "oil_up": _oil_up, "oil_down": _oil_down, "fare_up": _fare(268.0),
       "fare_down": _fare(236.0), "fare_up2": _fare(276.0), "oil_up6": _oil_step(0.06), "oil_up12": _oil_step(0.12), "northwind": _northwind, "alpenflug": _alpenflug,
       "fuel_spike": _fuel_spike, "oil_fall": _oil_fall, "cpi_cool": _cpi_cool, "fed_hold": _fed_hold,
       "strengthen": _strengthen, "rumor": _rumor, "jet_fuel_market": _jet_fuel_market, "cools": _cools,
       "cargo": _cargo, "third_shock": _third_shock}


def _edit_group(ctl: Any, by: str) -> Any:
    return ctl.propose_group("Policy loop", ["inflation", "federal_reserve"], pattern_id="SE-POLICY", by=by,
                             description="Inflation prompts the Fed to tighten; the two move as one loop.")


def _learned_admitted(ctl: Any) -> Any:
    pats = ctl.engine.ltm.object_generalizations.patterns
    learned = [p for p in pats.values() if str(p.status) == "admitted" and p.id not in ("SE-POLICY", "SE-FUEL", "SE-NEST")
               and not p.sub_pattern_ids]
    return max(learned, key=lambda p: (len(p.roles), p.id)) if learned else None


def _edit_nest(ctl: Any, by: str) -> Any:
    from axelrod_wm.control.controller import ControllerError

    chunk = _learned_admitted(ctl)
    if chunk is None:
        raise ControllerError("no superentity the model admitted is left to nest (was the Chunking example rejected?)")
    return ctl.propose_group("Oil and rates", [], parts=["SE-POLICY", chunk.id], pattern_id="SE-NEST", by=by,
                             description="Oil feeds inflation and airline costs; inflation moves the Fed. The two "
                                         "superentities share inflation, so they act as one larger whole.")


def _edit_dissolve(ctl: Any, by: str) -> Any:
    return ctl.propose_dissolve("SE-NEST", "show its two parts as themselves again", by=by)


def _edit_retire(ctl: Any, by: str) -> Any:
    from axelrod_wm.control.controller import ControllerError

    iid = find_link(ctl, FED_RATE, "delta.share_price")
    if iid is None:
        raise ControllerError("there is no Fed policy rate → Delta share price link to retire (was it deselected?)")
    return ctl.propose_retire(interaction_id=iid, reason="the link is too indirect to keep", by=by)


def _edit_group_airlines(ctl: Any, by: str) -> Any:
    return ctl.propose_group("Airline fuel squeeze", ["resources_energy", "delta", "skybridge"], pattern_id="SE-FUEL",
                             by=by, description="Oil sets both airlines' fuel bills.")


def _edit_retire_northwind(ctl: Any, by: str) -> Any:
    return ctl.propose_retire(entity_id="northwind", reason="the airline stopped flying (illustrative)", by=by)


def _edit_dissolve_learned(ctl: Any, by: str) -> Any:
    from axelrod_wm.control.controller import ControllerError

    p = _learned_admitted(ctl)
    if p is None:
        raise ControllerError("no superentity the model admitted is left to delete (was the Chunking example rejected?)")
    return ctl.propose_dissolve(p.id, "it no longer earns its place: delete it, keep its members", by=by)


EDITS = {"group": _edit_group, "nest": _edit_nest, "dissolve_learned": _edit_dissolve_learned, "dissolve": _edit_dissolve, "retire": _edit_retire,
         "group_airlines": _edit_group_airlines, "retire_northwind": _edit_retire_northwind}


def A(headline: str, body: str = "", quotes: list | None = None, rationale: str = "", **kw: Any) -> Article:
    return Article(headline=headline, body=body, quotes=quotes or [], rationale=rationale, **kw)


EXAMPLES: list[Example] = [
    Example(id="create", n=1, title="Grounding: one article, one entity", memory="working", stage="working", feature="creation",
            isolates="Creation, and classification into a concept",
            summary="The article introduces oil. Its translation adds one entity and one value, the Brent price. Parsing "
                    "creates them; the classifier sorts Oil into the Commodity market concept; long-term memory makes it the "
                    "concept's first member.",
            watch=["Items: a new entity and a new value", "Lessons: “Commodity market” gains Oil"],
            steps=[Step(ops="oil", days=0, article=A(
                "Brent crude settles near $75 a barrel",
                "The global benchmark for crude oil, Brent, ended the week near $75 a barrel, in line with its average "
                "for the year.",
                [("Brent crude", [0]), ("near $75 a barrel", [1])],
                "A market the model has never seen: an entity (Oil) and the value the article reports (the Brent price, "
                "near $75).", mentions=["Brent", "oil"], event_type="market_entry"))]),
    Example(id="links", n=2, title="Composition: an actor is made of its values", memory="working", stage="working",
            feature="creation",
            isolates="Creation with internal interactions, each sorted into an interaction concept",
            summary="The article introduces Delta Air Lines with three values and the two links inside it: fuel costs "
                    "squeeze the margin, and the margin drives the share price. Delta becomes the Airline concept's first "
                    "member; its links become the first members of their interaction concepts.",
            watch=["Items: one entity, three values, two interactions", "Lessons: concepts gain their first members"],
            steps=[Step(ops="delta", article=A(
                "Delta Air Lines: jet fuel is among its largest costs",
                "Fuel is one of the biggest costs for a large airline such as Delta. When fuel costs rise, its operating "
                "margin narrows, and investors price its shares off that margin.",
                [("Delta Air Lines", [0]), ("jet fuel", [1]), ("operating margin narrows", [2, 4]),
                 ("price its shares off that margin", [3, 5])],
                "One entity, its three values, and the two mechanisms the article states inside it.",
                mentions=["Delta", "jet fuel", "airline"], event_type="market_entry"))]),
    Example(id="refine", n=3, title="Refinement: a fuzzy mention narrows to one value", memory="intake", stage="intake",
            feature="refinement",
            isolates="Intake: refining a fuzzy end from a generalization toward a subentity, and hedging what is left",
            summary="The article says jet fuel tracks crude, but it names “airlines' jet fuel costs”, a generalization, "
                    "not a subentity. The refiner narrows the end level by level to the Airline concept, whose only member "
                    "so far is Delta. The article does not name Delta, so the end stays fuzzy: a hedge with Delta's jet "
                    "fuel cost at two thirds and the rest kept for an airline not in the graph yet. A soft interaction "
                    "to Delta carries that weight until later evidence settles it.",
            watch=["Intake: the refinement steps, then the hedge", "Items: a fuzzy candidate, Oil price → Delta jet fuel cost · 67%"],
            steps=[Step(ops="connect", article=A(
                "Jet fuel prices track crude oil",
                "Refiners price jet fuel off crude, so airlines' jet fuel costs follow the oil price within weeks.",
                [("airlines' jet fuel costs follow the oil price", [0])],
                "One link, from the oil price to “airlines' jet fuel costs”: an end that names a concept, refined to a value.",
                mentions=["jet fuel", "crude oil", "airlines"], event_type="supply_shock"))]),
    Example(id="ripple", n=4, title="Transmission: a shock ripples order by order", memory="working", stage="working", feature="ripple",
            isolates="The ripple: first-, second-, and third-order effects",
            summary="Brent jumps 20%. The event moves one value; the simulation carries the move through the interactions: "
                    "Delta's fuel cost at first order, its margin at second order, its share price at third. Check that "
                    "the signs and sizes make sense all the way down.",
            watch=["Moves: the oil price", "Ripple: fuel cost (1st), margin (2nd), share price (3rd)"],
            steps=[Step(ops="shock", article=A(
                "Brent jumps 20% as producers tighten supply",
                "Oil producers announced deeper output cuts, and Brent rose 20% over the week.",
                [("Brent rose 20%", [0])],
                "A change to a value the model holds: a step of +20% in the oil price.",
                mentions=["Brent", "oil"], event_type="supply_shock"))]),
    Example(id="expert_add", n=5, title="Practitioner knowledge: add what the news never said", memory="working",
            stage="working", feature="manual", kind="manual",
            isolates="A backend user adds an entity, its value, and an interaction from their own experience, with no "
                     "article behind it",
            summary="You have run airline revenue for years, and you know something no article has said yet: how full "
                    "the planes are drives margins. Open the form, add Air travel demand with a monthly passenger count "
                    "(prefilled: about 80 million, give or take 6%), and an interaction from it to Delta's operating "
                    "margin. You are fairly sure, not certain, so the confidence is 70%. It goes through the same staged "
                    "review as any article, and the model treats it as a belief with that weight.",
            watch=["The form: an entity, a value with its typical level and spread, one interaction, your confidence",
                   "Items: Air travel demand, US air passengers, passengers → Delta operating margin, at your 70%"],
            manual={"entity": {"id": "air_travel", "name": "Air travel demand", "kind": "macro_factor", "tags": ["SD"],
                               "aliases": ["air travel", "travel demand", "passenger demand"]},
                    "values": [{"slug": "passengers", "name": "US air passengers", "attribute_kind": "traffic_flow",
                                "unit": "m/month", "family": "lognormal", "typical": 80.0, "spread": 0.06}],
                    "interactions": [{"source": "new:passengers", "target": "delta.operating_margin",
                                      "label": "fills planes for", "polarity": 1, "effect": 0.5, "delay_days": 7,
                                      "lag_days": 30}],
                    "confidence": 0.7,
                    "note": "From years in airline revenue management: busier planes lift margins."}),
    Example(id="select", n=6, title="Human in the loop: keep only what makes sense", memory="review", stage="review",
            feature="selection",
            isolates="Human review: selecting and deselecting items",
            summary="An economists' note adds inflation, the Fed, and three links: oil raises inflation, inflation prompts "
                    "tightening, and tighter policy weighs on Delta's shares. Deselect the Fed: its value and links go "
                    "with it, and the event is staged again without them.",
            watch=["Items: seven, with their dependencies", "The canvas: new items in a dashed outline"],
            steps=[Step(ops="macro", article=A(
                "Economists: oil feeds inflation, and the Fed leans against it",
                "Higher oil prices raise headline inflation within a few months. When inflation runs hot, the Federal "
                "Reserve tends to raise its policy rate, and a higher rate weighs on airline shares such as Delta's.",
                [("headline inflation", [0, 1]), ("Federal Reserve", [2]), ("its policy rate", [3]),
                 ("Higher oil prices raise headline inflation", [4]), ("tends to raise its policy rate", [5]),
                 ("weighs on airline shares such as Delta's", [6])],
                "Two new entities with their values, and the three mechanisms the note describes.",
                kind="analyst", source="Synthetic research note", mentions=["inflation", "Fed", "oil"],
                event_type="analysis"))]),
    Example(id="fold", n=7, title="Learning from surprise: an observation corrects an effect", memory="working", stage="working",
            feature="observation",
            isolates="The fold: an observed value updates itself and the effects that feed it",
            summary="A month after the oil shock, a CPI release comes in above what the model expected. The fold updates "
                    "inflation and, because the oil link was active, how strongly oil feeds inflation: a lesson learned "
                    "from data.",
            watch=["Learned: CPI's value and the Oil → CPI effect"],
            steps=[Step(ops="cpi", days=29, article=A(
                "CPI rises to 3.4% y/y",
                "Consumer prices rose 3.4% from a year earlier, led by energy.",
                [("rose 3.4%", [0])], "A reported value: headline CPI at 3.4%.", kind="data",
                source="Synthetic statistics release", mentions=["CPI", "inflation"], event_type="data_release"))]),
    Example(id="inherit", n=8, title="Inheritance: a newcomer starts from its concept", memory="long_term",
            stage="long_term", feature="inheritance",
            isolates="Long-term memory: concepts pass their priors to new members",
            summary="SkyBridge Air (made up for the demo) arrives with the same values and links, but the article gives no "
                    "effect sizes. Each new link is sorted into its concept and starts from the effect the concept has pooled "
                    "from its members so far, such as Delta's.",
            watch=["Items: SkyBridge, its values, three links", "Lessons: “Airline” gains SkyBridge"],
            steps=[Step(ops="skybridge", article=A(
                "SkyBridge Air, a low-cost carrier, starts US routes (illustrative)",
                "SkyBridge Air buys jet fuel like any airline, and its margin and shares move with it. The airline is made "
                "up for the demo.",
                [("SkyBridge Air", [0]), ("buys jet fuel like any airline", [1, 4]), ("its margin", [2, 5]),
                 ("shares", [3, 6])],
                "A new airline; the article says how it works but not how strongly, so the concepts supply the sizes.",
                mentions=["SkyBridge", "airline"], event_type="market_entry"))]),
    Example(id="expert_link", n=9, title="Practitioner knowledge: connect your idea to the rest", memory="working",
            stage="working", feature="manual", kind="manual",
            isolates="A backend user adds one interaction between values the model already has, with its size and "
                     "timing, at half confidence",
            summary="Your demand idea is still on its own: nothing in the model moves it. From experience, tighter money "
                    "cools discretionary travel within a quarter or two, but you are only half sure. Add one interaction "
                    "from the Fed's policy rate to US air passengers (prefilled: it lowers them, about a quarter of a "
                    "standard unit per standard unit, after a month), at 50% confidence. From now on, a rate move "
                    "reaches airline margins through your idea too.",
            watch=["The form: one interaction between existing values, its size and timing, your 50%",
                   "Items: Fed policy rate → US air passengers, at your 50%"],
            manual={"values": [], "interactions": [{"source": FED_RATE, "target": "air_travel.passengers",
                                                    "label": "cools", "polarity": -1, "effect": -0.25,
                                                    "delay_days": 30, "lag_days": 60}],
                    "confidence": 0.5,
                    "note": "Tighter money cools discretionary travel within a quarter or two."}),
    Example(id="memory", n=10, title="Entity memory: an actor is remembered by its decisions", memory="long_term", stage="long_term",
            feature="decision",
            isolates="Long-term memory: an entity memory records a decision by its context",
            summary="The Fed raises its policy rate by a quarter point while inflation runs hot. The rate is a decision "
                    "variable, so the move is the Fed's decision: its entity memory records that it raised when inflation "
                    "was above normal. That record is what a later decision hypothesis reads. The ripple now also runs "
                    "through the idea you added: the rate cools air travel, which thins Delta's margin.",
            watch=["Lessons: the Fed's entity memory records “raised”",
                   "Ripple: the rate's effect on Delta's shares, and through your air travel demand to Delta's margin"],
            steps=[Step(ops="fed_hike", article=A(
                "The Fed raises its policy rate by a quarter point",
                "Citing inflation well above target, the Federal Reserve raised its policy rate by 25 basis points.",
                [("raised its policy rate by 25 basis points", [0])],
                "A decision by an actor: the Fed's policy rate, +0.25 points.", mentions=["Fed", "policy rate"],
                event_type="policy_decision"))]),
    Example(id="analog", n=11, title="Analogy: a new shock recalls an old one", memory="long_term", stage="working",
            feature="analogs",
            isolates="Long-term memory: past days are recalled, and what followed them adjusts the effects",
            summary="Brent jumps again. Recall finds the day of the first shock, and what followed it (the CPI surprise) "
                    "adjusts the oil-to-inflation effect before the ripple is simulated.",
            watch=["Recalled: the first shock's day", "Adjusted: the Oil → CPI effect"],
            steps=[Step(ops="second_shock", article=A(
                "Brent climbs 12% on a new supply scare",
                "A pipeline outage pushed Brent up 12% in two days.",
                [("pushed Brent up 12%", [0])], "Another step in the oil price.", mentions=["Brent", "oil"],
                event_type="supply_shock"))]),
    Example(id="pending", n=12, title="Deferred commitment: an ambiguous mention waits", memory="intake", stage="intake", feature="pending",
            isolates="Intake: an end that cannot be told apart stays fuzzy, hedged across its candidates",
            summary="The article says fuel costs squeeze “a US carrier's” margin without naming it. Delta and SkyBridge "
                    "fit equally well, so the end is hedged: a soft interaction to each margin, weighted by its "
                    "probability, and a share kept for a carrier not in the graph yet. Forecasts hedge across both "
                    "until later evidence settles it.",
            watch=["Items: two fuzzy candidates, Delta and SkyBridge, with a third of the weight kept for a carrier not in the graph",
                   "The canvas: one fuzzy interaction fanning to both margins"],
            steps=[Step(ops="vague", article=A(
                "Fuel hedges are running out at a US carrier",
                "Analysts say a US carrier's fuel hedges are expiring, so oil will now squeeze its margin directly. The "
                "note does not name the airline.",
                [("oil will now squeeze its margin", [0])],
                "A link from oil to “a US carrier's” margin: two airlines fit, so the end waits.", kind="analyst",
                source="Synthetic research note", mentions=["a US carrier", "hedges"], event_type="analysis"))]),
    Example(id="resolve", n=13, title="Resolution: later evidence settles what waited", memory="long_term", stage="long_term",
            feature="pending",
            isolates="Working memory: evidence accumulates on a hedge until one candidate passes the bound",
            summary="Two later articles weigh in. The first names SkyBridge (its fuel hedges have run out), so SkyBridge "
                    "gains weight, but one mention is not enough: the end keeps hedging. The second reports SkyBridge's "
                    "margin falling while oil is high, the way the interaction predicts. That carries SkyBridge past "
                    "the bound, and the model proposes the resolution for review: keep the interaction to SkyBridge, "
                    "retire the one to Delta.",
            watch=["The trail: two articles name SkyBridge, then its margin moves as predicted; only the last carries it past the bound",
                   "The proposal: a refinement, keep SkyBridge and retire Delta's soft interaction"],
            focus="raised", raises="refinement",
            steps=[Step(ops="hedges_end", days=2, article=A(
                "SkyBridge Air says its fuel hedges have run out (illustrative)",
                "SkyBridge Air said it no longer hedges fuel; its jet fuel cost rose to $2.90 a gallon.",
                [("its jet fuel cost rose to $2.90 a gallon", [0])],
                "A reported value for SkyBridge; the article names the airline.",
                kind="filing", source="Synthetic filing", mentions=["SkyBridge"], event_type="earnings")),
                   Step(ops="climb", days=10, article=A(
                "Brent edges up 6%", "Oil rose again on tighter supply.", [("up 6%", [0])],
                "A step in the oil price.", mentions=["Brent"], event_type="supply_shock")),
                   Step(ops="resolve", days=4, article=A(
                "SkyBridge Air's operating margin falls to 3% (illustrative)",
                "With fuel unhedged and oil high, SkyBridge Air reported an operating margin of 3%.",
                [("operating margin of 3%", [0])], "A reported value for SkyBridge's margin.",
                kind="filing", source="Synthetic filing", mentions=["SkyBridge"], event_type="earnings"))]),
    Example(id="weaken", n=14, title="Falsifiability: evidence weakens a link", memory="working", stage="working", feature="existence",
            isolates="Working memory: evidence against a link lowers the belief that it exists",
            summary="A study finds little sign that the policy rate moves airline shares directly. The link stays, but the "
                    "belief that it exists falls, so it carries less of any future ripple.",
            watch=["Learned: the link's existence, before and after"],
            steps=[Step(ops="weaken", article=A(
                "Study: rate moves explain little of airline share prices",
                "New research finds that the policy rate has little direct effect on airline shares once fuel is taken "
                "into account.",
                [("little direct effect on airline shares", [0])], "Evidence against the Fed rate → Delta share link.",
                kind="analyst", source="Synthetic research note", mentions=["policy rate", "airline shares"],
                event_type="analysis"))]),
    Example(id="superentity", n=15, title="Chunking: a group that fires together becomes one", memory="long_term", stage="long_term",
            feature="superentity",
            isolates="Long-term memory: a recurring group of interactions is proposed as a superentity",
            summary="Weeks pass while oil keeps working through Delta's fuel cost and through inflation, and Delta reports "
                    "its fuel cost index. The same interactions are active together day after day, so the group gains "
                    "support, and once it crosses the threshold the model proposes it as a superentity.",
            watch=["The proposal: a collapse, raised by the model", "The members: Oil, Delta, and Inflation"],
            focus="raised", raises="superentity_admission",
            steps=[Step(ops="climb", days=14, article=A(
                "Brent edges up another 6%", "Oil kept rising through the month.", [("up another 6%", [0])],
                "A smaller step in the oil price.", mentions=["Brent"], event_type="supply_shock")),
                   Step(ops="fuel_index", days=7, article=A(
                "Delta's jet fuel cost index rises to $3.00 a gallon", "The airline's fuel cost index rose with crude.",
                [("rises to $3.00 a gallon", [0])], "A reported value for Delta's fuel cost.", kind="data",
                source="Synthetic statistics release", mentions=["Delta", "jet fuel"], event_type="data_release"))]),
    Example(id="correlate", n=16, title="Accumulating evidence: a correlation gains strength", memory="long_term", stage="long_term",
            feature="frontier",
            isolates="Long-term memory: moves the graph did not explain are paired, and each check a pair passes "
                     "strengthens it",
            summary="Delta starts reporting its average fare. Oil rises and the fare surprises upward; oil falls and the "
                    "fare surprises downward. Nothing in the graph links them, so the correlation frontier logs the pair "
                    "and checks it again. Each check it passes adds support and tightens its correlation, but a "
                    "correlation is not yet a cause: nothing is proposed.",
            watch=["Lessons: the co-movement oil → fare gains strength (support, correlation)",
                   "Items: only the fare report; the frontier is long-term memory's own bookkeeping"],
            steps=[Step(ops="fares_begin", article=A(
                "Delta starts publishing its average fare", "Delta's average fare was $250 last month.",
                [("average fare", [0]), ("$250", [1])], "A new value for Delta, and its first report.", kind="filing",
                source="Synthetic filing", mentions=["Delta", "fare"], event_type="earnings")),
                   Step(ops="oil_up6", days=15, article=A("Brent rises 6%", "Oil rose on tighter supply.",
                        [("rose", [0])], "A step in the oil price.", mentions=["Brent"], event_type="supply_shock")),
                   Step(ops="fare_up", days=6, article=A("Delta's average fare rises to $268",
                        "Fares rose faster than expected.", [("rises to $268", [0])], "A fare report.", kind="data",
                        source="Synthetic statistics release", mentions=["Delta", "fare"], event_type="data_release")),
                   Step(ops="oil_down", days=12, article=A("Brent falls 8%", "Oil fell as supply returned.",
                        [("fell", [0])], "A step down in the oil price.", mentions=["Brent"], event_type="supply_shock")),
                   Step(ops="fare_down", days=6, article=A("Delta's average fare falls to $236",
                        "Fares fell faster than expected.", [("falls to $236", [0])], "A fare report.", kind="data",
                        source="Synthetic statistics release", mentions=["Delta", "fare"], event_type="data_release"))]),
    Example(id="frontier", n=17, title="Correlation to causation: a pair that holds is proposed", memory="long_term",
            stage="long_term", feature="frontier",
            isolates="Long-term memory: a co-movement that keeps holding at spaced checks is proposed as a causal "
                     "interaction",
            summary="Oil jumps 12% and the fare surprises upward again, by more than before. The pair has now held at "
                    "enough spaced checks, and its points line up: the bigger the oil move, the bigger the fare "
                    "surprise. The frontier proposes oil → fare as a learned interaction. It is only a proposal: a "
                    "person decides whether the correlation is a cause.",
            watch=["The proposal: a learned link, raised by the model",
                   "Its evidence: three paired moves on one line (small rise, fall, big rise)"],
            focus="raised", raises="frontier_promotion",
            steps=[Step(ops="oil_up12", days=12, article=A("Brent jumps 12%", "Oil jumped on a new supply scare.",
                        [("jumped", [0])], "A step in the oil price.", mentions=["Brent"], event_type="supply_shock")),
                   Step(ops="fare_up2", days=6, article=A("Delta's average fare rises to $276",
                        "Fares rose again, by more than before.", [("rises to $276", [0])], "A fare report.", kind="data",
                        source="Synthetic statistics release", mentions=["Delta", "fare"], event_type="data_release"))]),
    Example(id="split", n=18, title="Category growth: a crowded concept splits", memory="long_term", stage="long_term", feature="taxonomy",
            isolates="Long-term memory: members that share a feature their concept lacks become a concept of their own",
            summary="Two more airlines arrive: Northwind, from the US, then Alpenflug, from Europe (both made up). With "
                    "three US airlines and one European one, the Airline concept is crowded: the US carriers share a region "
                    "the concept does not require, so they split off into a concept of their own.",
            watch=["Lessons: a new concept, “Airline (region=US)”", "Its members: Delta, SkyBridge, Northwind"],
            steps=[Step(ops="northwind", article=A(
                "Northwind Airways adds routes in the Midwest (illustrative)",
                "Northwind Airways, a US regional carrier made up for the demo, buys jet fuel like its rivals.",
                [("Northwind Airways", [0])], "Another US airline.", mentions=["Northwind"], event_type="market_entry")),
                   Step(ops="alpenflug", article=A(
                "Alpenflug opens a transatlantic route (illustrative)",
                "Alpenflug, a European airline made up for the demo, starts flying to New York.",
                [("Alpenflug", [0]), ("European airline", [0])], "An airline from another region.",
                mentions=["Alpenflug"], event_type="market_entry"))]),
    Example(id="collapse", n=19, title="Collapse: a person groups two entities", memory="long_term",
            stage="long_term", feature="structure", kind="edit", edit="group",
            isolates="Structure: entities collapse into one superentity, by a person's edit",
            summary="A backend user groups inflation and the Fed into one superentity, the Policy loop. Approved, it is "
                    "admitted and drawn as one card.",
            watch=["Items: one collapse", "Lessons: the superentity is admitted"]),
    Example(id="nest", n=20, title="Nesting: superentities within a superentity", memory="long_term",
            stage="long_term", feature="structure", kind="edit", edit="nest",
            isolates="Structure: two superentities become the parts of a larger one",
            summary="The Policy loop and the group the model learned in the Chunking example share inflation: oil feeds "
                    "inflation and the airlines' costs, and inflation moves the Fed. A backend user nests both in one "
                    "superentity, Oil and rates. Closed, it is one card; opened, it shows its two parts, and each part "
                    "opens into its entities.",
            watch=["Items: one collapse whose parts are superentities",
                   "The canvas: the outer outline holds both inner ones; the path above the canvas names each level"]),
    Example(id="expand", n=21, title="Expansion: the whole breaks back into its parts", memory="long_term", stage="long_term",
            feature="structure", kind="edit", edit="dissolve",
            isolates="Structure: a superentity breaks back into its constituents",
            summary="The backend user dissolves Oil and rates. Its two parts show as themselves again, the Policy loop and "
                    "the learned group; the pattern stays in long-term memory, dissolved, with its history.",
            watch=["Items: one expansion", "The canvas: the two inner superentities remain"]),
    Example(id="retire_superentity", n=22, title="Revision: delete a superentity the model provided",
            memory="long_term", stage="long_term", feature="structure", kind="edit", edit="dissolve_learned",
            isolates="Structure: a person deletes a superentity that long-term memory admitted on its own",
            summary="The superentity the model admitted in the Chunking example groups Oil with Delta and Inflation. A backend user "
                    "decides it no longer earns its place and deletes it. Its members stay in the graph as themselves; "
                    "the pattern is dissolved, and long-term memory keeps its history, so a later group that fires "
                    "the same way starts from that record.",
            watch=["Items: one expansion of a superentity the model made", "Lessons: the superentity is dissolved"]),
    Example(id="delete", n=23, title="Deletion: retiring a link always waits for review", memory="working", stage="review", feature="deletion",
            kind="edit", edit="retire",
            isolates="Deletion: retired structure leaves the graph; deleting always waits for a person",
            summary="After the study weakened it, the backend user retires the link from the Fed's rate to Delta's shares. "
                    "The log keeps its whole history.",
            watch=["Items: one retirement", "The canvas: the retired link in red"]),
    Example(id="inference", n=24, title="Inference without learning: ask a what-if", memory="inference", stage="inference", feature="inference",
            kind="thesis", question="What if oil rose by 30% next quarter?",
            isolates="Inference: a thesis on a branch of a committed version; nothing is learned",
            summary="Switch to Predict and ask what happens if Brent rises 30% next quarter. The forecast runs on a branch of "
                    "the committed version, by order and transmission path, and the model does not change.",
            watch=["The forecast: effects by order", "The version number does not move"]),
]

LIBRARY: list[LibraryEvent] = [
    LibraryEvent(id="jet-fuel-market", feature="creation", title="Jet fuel starts trading as its own market",
                 after="refine", step=Step(ops="jet_fuel_market", article=A(
                     "Gulf Coast jet fuel becomes a benchmark of its own",
                     "Traders now quote Gulf Coast jet fuel separately; it is priced almost entirely off crude.",
                     [("Gulf Coast jet fuel", [0, 1]), ("priced almost entirely off crude", [2])],
                     "A new market, its price, and its link to oil.", mentions=["jet fuel"], event_type="market_entry"))),
    LibraryEvent(id="policy-cools", feature="refinement", title="Tighter policy cools “inflation” (a fuzzy end)",
                 after="select", step=Step(ops="cools", article=A(
                     "Economists: higher rates cool inflation, with a long lag",
                     "A higher policy rate cools inflation, but only after a year or so.",
                     [("A higher policy rate cools inflation", [0])],
                     "A link to “inflation”, which names a value concept; the refiner finds the one value under that concept.",
                     kind="analyst", source="Synthetic research note", mentions=["policy rate", "inflation"],
                     event_type="analysis"))),
    LibraryEvent(id="cargo", feature="inheritance", title="A cargo airline arrives", after="inherit", step=Step(
        ops="cargo", article=A("SkyFreight Cargo starts flying freight (illustrative)",
                               "SkyFreight Cargo, a US freight airline made up for the demo, buys jet fuel like any carrier.",
                               [("SkyFreight Cargo", [0]), ("buys jet fuel", [1, 2])],
                               "A cargo airline: it is sorted below Airline, into Cargo airline, and inherits from both.",
                               mentions=["SkyFreight"], event_type="market_entry"))),
    LibraryEvent(id="third-shock", feature="analogs", title="A third oil shock", after="analog", step=Step(
        ops="third_shock", article=A("Brent rises 10% as inventories fall", "Crude inventories fell, and Brent rose 10%.",
                                     [("Brent rose 10%", [0])], "Another step in the oil price; recall now has two "
                                     "similar days to draw on.", mentions=["Brent"], event_type="supply_shock"))),
    LibraryEvent(id="oil-falls", feature="ripple", title="Brent falls 15%", after="ripple", step=Step(
        ops="oil_fall", article=A("Brent falls 15% as output returns", "Producers restored output, and Brent fell 15%.",
                                  [("Brent fell 15%", [0])], "A step down in the oil price.", mentions=["Brent"],
                                  event_type="supply_shock"))),
    LibraryEvent(id="fuel-spike", feature="ripple", title="Jet fuel spikes on a refinery outage", after="ripple",
                 step=Step(ops="fuel_spike", article=A(
                     "Jet fuel costs spike 25% after a refinery outage",
                     "A refinery outage on the Gulf Coast pushed Delta's jet fuel costs up 25%.",
                     [("pushed Delta's jet fuel costs up 25%", [0])],
                     "A move that starts one order down the chain: the ripple begins at the fuel cost.",
                     mentions=["jet fuel", "Delta"], event_type="supply_shock"))),
    LibraryEvent(id="cpi-cools", feature="observation", title="CPI eases to 3.0%", after="fold", step=Step(
        ops="cpi_cool", article=A("CPI eases to 3.0% y/y", "Consumer prices rose 3.0% from a year earlier.",
                                  [("rose 3.0%", [0])], "A reported value.", kind="data",
                                  source="Synthetic statistics release", mentions=["CPI"], event_type="data_release"))),
    LibraryEvent(id="fed-holds", feature="decision", title="The Fed holds its rate", after="memory", step=Step(
        ops="fed_hold", article=A("The Fed holds its policy rate", "The Federal Reserve left its policy rate unchanged.",
                                  [("left its policy rate unchanged", [0])],
                                  "A decision to hold: the rate is reported unchanged.", mentions=["Fed"],
                                  event_type="policy_decision"))),
    LibraryEvent(id="strengthen", feature="existence", title="Evidence supports the oil–inflation link",
                 after="weaken", step=Step(ops="strengthen", article=A(
                     "Study: oil passes through to inflation within months",
                     "New research finds that oil price moves reach headline inflation within a few months.",
                     [("oil price moves reach headline inflation", [0])], "Evidence for the Oil → CPI link.",
                     kind="analyst", source="Synthetic research note", mentions=["oil", "inflation"],
                     event_type="analysis"))),
    LibraryEvent(id="rumor", feature="selection", title="A rumor to reject", after="ripple", step=Step(
        ops="rumor", article=A("Rumor: higher oil will lift Delta's shares (illustrative)",
                               "An anonymous post claims that higher oil prices will lift airline shares.",
                               [("higher oil prices will lift airline shares", [0])],
                               "A claim with no mechanism behind it: a link the reviewer should reject.",
                               source="Synthetic forum post", mentions=["oil", "Delta"], event_type="rumor"))),
    LibraryEvent(id="group-airlines", feature="structure", title="Group oil and the two airlines", after="split",
                 edit="group_airlines"),
    LibraryEvent(id="retire-northwind", feature="deletion", title="Northwind stops flying", after="split",
                 edit="retire_northwind"),
    LibraryEvent(id="ask-fed", feature="inference", title="What if the Fed raised rates by 100bp?", after="select",
                 question="What if the Fed raised rates by 100bp?"),
    LibraryEvent(id="ask-double", feature="inference", title="What if oil prices doubled next quarter?",
                 after="refine", question="What if oil prices doubled next quarter?"),
]

SMALL = Catalog(name="small", examples=EXAMPLES, library=LIBRARY, ops=OPS, edits=EDITS)

__all__ = ["SMALL"]
