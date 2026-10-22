"""A small multilingual world for the tests: a Chinese EV maker, a Korean maker, and a Japanese one, each with Chinese or
Korean names and aliases. Invented."""

from __future__ import annotations

from axelrod_ingest.contract.world_view import EntityView, ValueView, WorldView
from axelrod_ingest.extract import Rules
from axelrod_ingest.gazetteer import Gazetteer


def world() -> WorldView:
    ents = {
        "acme_ev": EntityView("acme_ev", "Acme EV", "company", ("AEV", "艾克米电动", "艾克米電動"), "CN", "autos",
                              ("acme_ev.revenue", "acme_ev.net_profit", "acme_ev.units")),
        "acme_kr": EntityView("acme_kr", "Acme Korea", "company", ("에이크미코리아",), "KR", "autos",
                              ("acme_kr.revenue", "acme_kr.operating_profit")),
        "acme_jp": EntityView("acme_jp", "Acme Japan", "company", ("アクメ",), "JP", "autos", ("acme_jp.revenue",)),
    }

    def v(eid: str, key: str, name: str, unit: str, mean: float, aliases: tuple[str, ...], kind: str = "revenue_flow"):
        return ValueView(f"{eid}.{key}", eid, name, kind, unit=unit, scale=0.3, family="lognormal", mean=mean,
                         sd=mean * 0.3, aliases=aliases)

    vals = [
        v("acme_ev", "revenue", "Acme EV revenue", "CNY bn/yr", 100, ("revenue", "营业收入", "營業收入")),
        v("acme_ev", "net_profit", "Acme EV net profit", "CNY bn/yr", 8, ("net profit", "净利润", "淨利潤")),
        v("acme_ev", "units", "Acme EV sales volume", "m units/yr", 4, ("sales volume", "销量"), "production_flow"),
        v("acme_kr", "revenue", "Acme Korea revenue", "KRW tn/yr", 250, ("revenue", "매출액")),
        v("acme_kr", "operating_profit", "Acme Korea operating profit", "KRW tn/yr", 10, ("operating profit", "영업이익")),
        v("acme_jp", "revenue", "Acme Japan revenue", "¥tn/yr", 40, ("revenue", "売上高")),
    ]
    return WorldView(entities=ents, values={x.id: x for x in vals}, links=())


def rules(yen: str = "¥") -> Rules:
    w = world()
    return Rules(w, Gazetteer(w), yen=yen)
