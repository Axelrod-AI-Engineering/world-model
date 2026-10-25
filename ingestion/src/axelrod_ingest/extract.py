"""Extraction (Oct 17): recognized sentences into import signals, by rules, deterministically.

For each sentence, the values it names (gazetteer.py) and the numbers, directions, and causal words around them decide
what it claims:

    observe   a value with a level in its unit:        "held rates at 3.875%", "USD/JPY fell to 152",
              "Price (31 Jul 2026) ¥6,994" (a key-data line), "raised rates by 25bp to 3.75-4.0%" (a range's midpoint)
    move      a value with a direction and a size:     "the BoJ raised its policy rate by 25bp", "a 25bp cut",
              "net interest income rose 4%", "2Y yields ending ~7bp higher"
    move      a revision from one figure to another:   "we raise our OP forecast from ¥592bn to ¥654bn" (+10.4%),
              "trim our TSF growth forecast to 7.3% from 7.5%" (-0.2 points)
    move      a value with a direction and no size:    "estimates for Komatsu were cut" (a small standardized move);
              the direction word must sit next to the value, as its verb or its adjective ("NII rose", "lower NII")
    observe / move from a table row: a row whose label names the value ("Operating profit (¥bn) 3,766 3,843 4,261"),
              read in the column of the period the document is in (tables.py), or a Previous/Current pair as a move;
              a spreadsheet's row by its header's columns, by a period in the row itself ("EBIT | FY2027 | 3400000"),
              or a level beside its figure ("USD/JPY | 158.05"), scaled by the label's unit or, failing one, by the
              one scale that makes it plausible ("14,805" in € mn is 14.8 €bn)
    support / contradict
              two values joined by a causal word when the model has a link between them: "higher JGB yields lift
              Tokio Marine's income" (cause, verb, effect) or "NII rose 5%, thanks to higher rates" (effect, because,
              cause); the claim's sign is the verb's times the cause's direction, and a denied channel ("hikes are
              unlikely to strengthen the yen") contradicts. Also: a predicate ("is a tailwind for"), a connector with its
              own sign ("benefits from", "hurt by"), a verb whose sign is the effect's word ("lead to NII pressure"),
              a relative clause or a participle ("which lift", ", triggering"), and an event before or after ("Following
              the hike, the yen rose", "the yen rose after the hike"). An entity stands for the one value whose link has
              the stated sign ("a weaker yen lifts Toyota"); a sector with its region ("Japanese insurers") for the
              model's companies in it; bare "yields" for the bond market of the region in view
    link      the same, when the model has no link yet (proposed for review, with a modest effect)
    move      the ends of a channel reported as what happened ("a weaker yen lifted Toyota's profit", "NII rose thanks
              to higher rates"), never of a mechanism ("a weaker yen lifts ...") or a premise ("amid talk of hikes")

Numbers must fit the value's unit (a percent for a rate, a currency or plain number near a price's level), and a level
must be plausible for the value (within a wide band of its posterior), so years, page numbers, and footnotes never
become levels. A price target is not a price, a quarter's figure is not a year's, a forecast of a market level is not
its level, a sentence only about earlier years is history, a figure for "select banks" is no one bank's, a denied or
supposed claim ("is unlikely to fall", "if yields rise", "downside risks include") is no claim, and a disclaimer
claims nothing. A value's direction is read from its own words: not across a preposition ("weakening from the yen"),
not from a verb acting on something else ("the yen raises import costs"), not from someone's aim ("swaps to reduce
volatility"). Every signal quotes its sentence exactly. Sentences are grouped into items by chunk.

Precision (Oct 18): an observation is a reported current level, and a move a reported change or a revision. So a
level is read in the latest actual column (never an estimate, a stale year-end, or a market price at a period's end),
a workbook's computed columns are a projection, and a preview, a base case, the market's pricing, another's guidance,
a prediction ("will grow"), a scenario's bullet, an earlier episode, a quarter's sequential change of a year's flow, a
month's print of a year-on-year rate, a pause, a part of a list taken for the whole, and a value after an actor the
model does not know claim nothing.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Any

from axelrod_ingest.chunk import CELL, sentences, tabular
from axelrod_ingest.cjk import CJK_CHAR
from axelrod_ingest.contract.world_view import WorldView
from axelrod_ingest.dates import resolve as resolve_dates
from axelrod_ingest.gazetteer import METRICS, Gazetteer, Match
from axelrod_ingest.tables import (
    FIGURE,
    FIGURE_CELL,
    MONTHS,
    PERIOD,
    Header,
    Period,
    align,
    cells_of,
    end_of,
    header_of,
    period_of,
    pick,
    revise,
)
from axelrod_ingest.text import norm
from axelrod_ingest.units import (
    ARTICLE,
    CJK_SCALE_RUN,
    CJK_TAIL,
    CODE_AFTER,
    CODES,
    CURRENCY,
    CURRENCY_PREFIX,
    CURRENCY_SUFFIX,
    CURRENCY_WORD,
    SCALE,
    scale_hint,
    scale_value,
    tail_value,
)

# -- numbers ------------------------------------------------------------------------------------------------------
NUMBER = re.compile(
    rf"(?P<sign>[+\-−–])?\s?(?P<cur>{CURRENCY_PREFIX})?\s?"
    r"(?P<num>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)(?![\d年月日년월일위])"        # 2026年 is a date, not a figure
    rf"(?:\s?(?P<scale>trillion|tn|tr|billion|bn|b|million|mn|mm|m|k)\b|\s?(?P<cscale>{CJK_SCALE_RUN})(?P<tail>{CJK_TAIL}))?"
    rf"(?:\s?(?P<cursuf>{CURRENCY_WORD}))?"
    r"(?:[\s-]?(?P<unit>个百分点|個百分點|百分[点點]|퍼센트|%p(?![a-z])|%|percentage[\s-]points?|pct pts?|ppts?|pp|per ?cent|percent|"
    r"pct|basis[\s-]points?|bps?|x\b))?"
    rf"(?:\s?(?P<code>{CODE_AFTER})\b)?", re.I)
CURRENCY_ONLY_SCALES = ("m", "b", "tr")     # "$5m", "$6.4b": a scale only with a currency ("5 m" is not five million)
RANGE_JOIN = re.compile(r"^\s?(?:[-–]|to)\s?$")
DIRECTION_UP = (r"(?:rais|hik|lift|increas(?!ingly)|ris(?:e|es|en|ing)\b|rose|climb|jump|gain|surg|beat|upgrad|improv|widen|"
                r"strengthen|higher|up\b(?!\s+to\b)|grew\b|grow(?:s|ing|n)?\b|expand|accelerat|boost|recover|rebound|tighten|stronger|"
                r"spik|soar|appreciat)")
DIRECTION_DOWN = (r"(?:cut|lower|reduc|fell|fall|drop|declin|slip|slid|plung|miss(?:ed|es|ing)?\b|downgrad|weaken|narrow|"
                  r"contract(?:ed|ing|ion)\b|shrink|shrank|decreas|eas(?:e|es|ed|ing)\b|trim|compress|slow|down\b|"
                  r"soft(?:en|er|ening|ened)?\b|weaker|deteriorat|tumbl|sank|sink|depreciat)")
# at a word's start: "crisis", "again", and "release" name no direction ("risk" is not "rise" either)
UP = re.compile(r"\b" + DIRECTION_UP + r"\w*", re.I)
DOWN = re.compile(r"\b" + DIRECTION_DOWN + r"\w*", re.I)
BY = re.compile(r"\bby\s+(?:about\s+|around\s+|roughly\s+|c\.\s?|~)?$", re.I)
LEVEL = re.compile(r"\b(?:at|to|of|is|was|were|are|be|stands? at|stood at|reached|reach|hit|near|around|towards?|"
                   r"close to|(?:ended|ending|closed|closing|trading|traded) (?:at|near|around)|=)\s*(?:about\s+|around\s+|roughly\s+|c\.\s?|~|just\s+|(?:just\s+)?(?:above|below|over|"
                   r"under)\s+)?$|[=:]\s*$|(?:为|是|达到|达|至|约为|约|共计|合计|录得|实现|으로|로|[은는이가])\s*(?:约|약)?\s*$",
                   re.I)
KEY_VALUE = re.compile(r"^[\s,:]*(?:close|closing)?[\s,:]*$", re.I)   # "Price (31 Jul 2026) ¥6,994", parentheticals dropped
PARENS = re.compile(r"\([^()]*\)")
KEY_VALUE_CHARS = 90                        # a key-data line is short
TARGET = re.compile(r"^\s*(?:target|objective|obj\b|PT\b|range)", re.I)
# a market level's forecast, consensus, or assumption is not its level ("10-year yield forecast of 4.33%")
FORECAST = re.compile(r"^\s*(?:forecasts?|consensus|estimates?|expectations?|assumptions?|outlook|projections?)\b", re.I)
YEAR = re.compile(r"(?<![\d/.A-Za-z])(19[5-9]\d|20[0-4]\d)(?![\d/%])")    # not "FY2025": a fiscal label
STALE_DAYS = 180                       # a figure dated half a year before the document is history, not a level
SHORT_DATE = re.compile(r"\b(?P<d>\d{1,2})[ -](?P<mon>Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*[ -](?P<y>\d{2})\b")
TARGET_BEFORE = re.compile(r"\b(?:target|objective)\s+$", re.I)
# a level the sentence only expects or aims at: "the terminal policy rate", "we forecast USD/JPY at 162"
NOT_NOW = re.compile(r"\b(?:implied|(?:forecast|expect|see|project|predict)(?:s|ed|ing)?(?:\s+the)?)\s*$", re.I)
PROJECTED = re.compile(r"\b(?:projected|expected|forecast|seen|likely|should|will|to (?:rise|fall|climb|drop|reach))\b",
                       re.I)                   # "10-year yields projected to fall to 4.45%": a forecast, not a level
PROSPECT = re.compile(r"\b(?:year-end|forecast|projected|simulated|scenario|target|terminal|implied)\b", re.I)
YOY = re.compile(r"\s*\)?\s*(?:y-?o-?y|y/y|yoy|year[- ]on[- ]year|year[- ]over[- ]year)\b", re.I)
CJK_FORECAST = re.compile(r"预计|预期|预测|预估|估计|有望|将达|예상|전망|추정")     # a figure only expected (Chinese, Korean)
EXPECTS = re.compile(r"\b(?:expects?|expected|expecting|forecasts?|projects?|projected|anticipates?|sees?|will|likely|"
                     r"should)\b", re.I)
AS_EXPECTED = re.compile(r"\bas\s+(?:\w+\s+)?expected\b", re.I)          # "as markets widely expected" is no forecast
ESTIMATED = re.compile(r"\b(?:YE|FY|[1-4]Q|Q[1-4]|[12]H)?['’]?\d{2,4}[eE]\b")   # "13.6% YE26e": a forecast period
AVERAGED = re.compile(r"\baverage[ds]?\b", re.I)          # "an average policy rate of 3.5% in the quarter": a mean
HISTORY = re.compile(r"\b(?:last time|historically|the past|back in|previous (?:cycle|hiking cycle|episode)|"
                     r"(?:past|major|previous|prior|earlier) episodes)\b", re.I)
# what is only expected is no observation and no move: a preview ("hike incoming", "revenues are seen up 4%"), a base
# case, a projection, the market's pricing of moves to come, an assumption ("based on a rate of 4%"), and another's
# expectation or guidance ("management expects", "guided to fees down"); a revision of one (from A to B) is news
PREVIEW = re.compile(r"\b(?:(?:is|are|was|were|being)\s+seen|seen\s+(?:up|down|rising|falling|higher|lower)|incoming|"
                     r"projected|projections?|base[- ]case|baseline|there should|should be|pricing in|priced in|"
                     r"based on|guid(?:es|ed|ing)|expects|anticipates|sees)\b", re.I)
# ... read in the value's own part of the sentence: up to a semicolon or a sub-bullet ("o At 2Q26, mgmt guided")
PART_BREAK = re.compile(r";|\n\s*o\s+(?=[A-Z])")
FRAME_WORDS = 3
# a scenario's heading, its bullets, and a day and month with no year ("between 30 July and 5 August")
SCENARIO = re.compile(r"^\W*(?:(?:upside|downside|bull|bear|base)(?:[- ]case)?\s+scenario|(?:bull|bear|base)[- ]case)\b",
                      re.I)
BULLET = re.compile(r"^\s*(?:[-•*·▪●◦‣◆◇■□►▶➢➤✓✔]|\d+[.)])\s")
PROSE_WORDS = 4                         # a line of at least this many words that is no bullet ends a scenario's list
DAY_MONTH = re.compile(r"\b\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\b|"
                       r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2}\b(?!,?\s*\d)")
ESTIMATE_BEFORE = re.compile(r"\b(?:est\.|estimated?|expected|projected|forecast)\s+(?:[\w-]+\s+){0,2}$", re.I)
# a possessive of a name the model does not know ("NTT's share price"): the next sentence's "its" is that name's
POSSESSOR = re.compile(r"\b([A-Z][A-Za-z&]+)['’]s\b")
POSSESSED = re.compile(r"\b(?:its|their)\s+$", re.I)
# a view of the value, whose direction is the view's: "a downward bias to our GDP growth forecast"
VIEW_OF = re.compile(r"\s+(?:forecasts?|estimates?|outlook|projections?|guid(?:ance|e)|expectations?)\b", re.I)
# ... unless the view was revised, which is news: "we raised our NII forecasts"
REVISED = re.compile(r"\b(?:rais|cut|lower|trim|increas|reduc|revis|upgrad|downgrad|lift|boost)\w*", re.I)
# a value on another basis than the model's: "stripping out subsidies, core CPI was 2.3%"
OTHER_BASIS_LEAD = re.compile(r"\b(?:strip(?:ping|ped)? out|adjusted for)\b", re.I)
# a comparison with the previous quarter, and one with the year before
SEQUENTIAL = re.compile(r"\b(?:relative to|compared (?:with|to)|vs\.?|versus)\s+(?:the\s+)?(?:[1-4]Q|Q[1-4])\s?['’]?\d{2}|"
                        r"\bq/q\b|\bqoq\b|\bsequential(?:ly)?\b|\bquarter[- ]on[- ]quarter\b", re.I)
WILL_MOVE = re.compile(r"[^.;]{0,40}?\bwill\s+((?:\w+\s+)?\w+)", re.I)     # "... will grow", "will gradually rise"
MONTH_YEAR = re.compile(r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+20\d\d\b")   # a date, not a period
FULL_YEAR = re.compile(r"\b(?:FY|CY|full[- ]year|annual|for the year|(?:fiscal|calendar) year|20\d\d)", re.I)
MONTH_ON_MONTH = re.compile(r"\b(?:m/m|mom|month[- ]on[- ]month)\b", re.I)
PAUSED = re.compile(r"\b(?:paus(?:e|es|ed|ing)|halt(?:s|ed|ing)?|unchanged|on hold|hold(?:s|ing)? steady)\b", re.I)
# a value as the object of someone's aim: "buybacks to improve shareholder returns", "committed to reducing" (but
# "voted to raise the rate", "continues to raise", "the BoJ to hike" are the value's own moves: LICENSED, or a name)
AIM_OF = re.compile(r"(\S+)\s+to\s+[a-z]+\s+(?:the\s+|its\s+|their\s+|our\s+)?$")
ANNUAL = re.compile(r"\b(?:y/y|yoy|y-o-y|year[- ]on[- ]year|year[- ]over[- ]year)\b", re.I)
MONTHLY = re.compile(r"\s*(?:m/m|mom|month[- ]on[- ]month|in (?:January|February|March|April|May|June|July|August|"
                     r"September|October|November|December))\b", re.I)
# a figure labelled by its own name in a list ("OVX (-21%), VIX (-12%) ... MOVE (+6%)"): one component each
LABELLED = re.compile(r"[A-Za-z][\w&/.-]*\s*\(\s*[-+−]?\d[\d.,]*\s*%\s*\)|\([A-Z][\w&/.-]*\s+[-+−]\d[\d.,]*\s*%\s*\)")
# a short capitalized token the model does not know ("KEY FY26 NII up", "The BCB lowered its"): another actor
ACRONYM = re.compile(r"\b[A-Z]{2,5}\b")
COMMON_ACRONYMS = {"US", "UK", "EU", "EM", "DM", "FY", "CY", "YTD", "QTD", "MTD", "GDP", "CPI", "PCE", "PPI", "PMI",
                   "MOM", "USD", "JPY", "EUR", "GBP", "CNY", "RMB", "AI", "IT", "CEO", "CFO", "LSD", "MSD", "HSD",
                   "IPO", "ETF", "FX", "OK", "THE", "AND", "FOR", "NOT", "BUT", "WE", "OUR", "IN", "ON", "OF", "TO"}
GENERIC_NAME_WORDS = {"market", "capital", "bank", "group", "economy", "government", "bond", "us"}
# a value named without its entity, after another noun, is that noun's: "implied volatility", "sovereign issuance"
PRE_OK = {"the", "a", "an", "its", "their", "our", "this", "that", "of", "in", "on", "at", "for", "to", "and", "or",
          "with", "by", "from", "as", "is", "are", "was", "were", "higher", "lower", "rising", "falling", "elevated",
          "weaker", "stronger", "softer", "firmer", "record", "recent", "average", "overall", "global", "total", "about",
          "around", "see", "sees", "saw", "expect", "expects", "while", "than", "if", "when", "where", "but", "so",
          "still", "also", "both", "more", "less", "much", "rates", "rate", "fx", "strong", "weak", "solid", "robust",
          "slower", "faster", "continued", "sustained", "held", "hold", "holds", "kept", "keep", "keeps", "left",
          "maintained", "maintain", "said", "says", "closing", "close", "current", "last", "latest", "stock", "share",
          "one", "two", "three", "four", "another", "further", "additional", "policy"}
AIMED = re.compile(r"\b(?:targets?|targeting|targeted|objectives?|terminal|neutral|ambitions?|aspirations?|goals?)\b", re.I)
# a year's figure is named a year's: a quarterly document's headline is the quarter's unless it says otherwise
YEAR_WORDS = re.compile(r"\b(?:(?:FY|CY)\s?['’]?\d{0,4}|full[- ]year|annual(?:ly)?|(?:fiscal|calendar) year|for the year|year ended)\b|年度|全年|연간",
                        re.I)
CORE = re.compile(r"\b(?:core|underlying|adj\w*|ex)\b", re.I)
EXCLUDING = re.compile(r"\((?:ex|excl|excluding|adj|adjusted|underlying|core)\b", re.I)   # "NII (ex markets)": another metric
OTHER_BASIS = re.compile(r"^\s*(?:QoQ|q/q|m/m|MoM|annuali[sz]ed|saar|SAAR|qoq)\b")       # not a y/y rate
HEADING_SHARE = 0.6
PREPOSITIONS = {"from", "by", "on", "to", "with", "for", "at", "against", "versus", "vs", "via", "into", "over"}
# an infinitive is the value's own move only right after it ("NII to rise"), after a word that makes it so ("is expected
# to rise", "began to rebound", "voted to raise"), or after a name ("the BoJ to raise"); after a noun it is someone's
# aim ("its portfolio to reduce volatility", "the imperative ... to hike")
INFINITIVE = re.compile(r"(\S+)?(\s+)to\s+[a-z]+")
LICENSED = {"expected", "likely", "set", "due", "continue", "continues", "continued", "begun", "began", "begin", "begins",
            "started", "start", "starts", "seems", "seem", "poised", "going", "is", "are", "was", "were", "has", "have",
            "had", "voted", "decided", "agreed", "moved", "plans", "planned", "intends", "projected", "forecast"}
TRANSITIVE = re.compile(r"\b(?:rais|lift|boost|cut|lower|reduc|increas|push|driv|drove|strengthen|weaken|trim|slow|widen|"
                        r"narrow)\w*\s+"
                        r"(?:the\s+|its\s+|their\s+|a\s+|an\s+)?(?!(?:by|to|from|in|on|at|over|for|sharply|further|"
                        r"slightly|again|significantly|modestly|materially|substantially|and|or|but|as|than|while)\b)"
                        r"[a-z]{3,}", re.I)
FIGURE_RUN = re.compile(r"(?<![\w.])[-+−]?\d[\d,]*\.\d+%? [-+−]?\d[\d,]*\.\d+%?(?![\w.])")   # "0.9027 0.8522": a table's cells
EXPOSED = re.compile(r"\b(?:exposed|exposure|sensitive|sensitivity|beneficiar\w*|hedg\w*|benefit\w* from|suffer\w* from|"
                     r"tends? to)\b", re.I)                # who gains from a stronger yen claims nothing about the yen
COMPARATIVE_NOUN = re.compile(r"\b(?:higher|lower|weaker|stronger|softer|firmer|bigger|smaller|faster|slower|rising|"
                              r"falling|strong|weak|solid|robust|soft)\s+(?!(?:than|in|on|by|at|to|over|and|or|from|"
                              r"since|after|this|last|y/y|yoy|q/q)\b)[a-zA-Z]{3,}", re.I)                    # a line whose words are mostly capitalized is a heading or a chart label
# words that may follow a value's name without making it the modifier of another noun ("NII forecasts")
# nouns that make a value's name the modifier of another measure: "USD/JPY volatility", "yen borrowing", "NII growth"
MODIFIED_BY = {"growth", "volatility", "vol", "borrowing", "lending", "exposure", "position", "positioning", "flow",
               "spread", "swap", "option", "future", "forward", "basis", "curve", "sensitivity", "beta", "carry",
               "funding", "deposit", "loan", "asset", "liability", "implied", "index", "indice", "share", "weight",
               "weighting", "mix", "contribution", "consensus", "premium", "discount", "multiple", "cost", "momentum",
               "pricing", "appreciation", "depreciation", "intervention", "hedging", "denominated", "translation", "fair",
               "platform", "boost", "impact", "drag", "uplift", "accretion", "dilution", "headwind", "tailwind",
               "benefit", "regime"}
QUARTER = re.compile(r"(?<![A-Za-z0-9])(?:[1-4]Q|Q[1-4]|[12]H|H[12])\s?['’]?\d{0,4}(?![A-Za-z0-9])|\bquarter(?:ly)?\b|\bq/q\b|"
                     r"上半年|下半年|半年度?|前三季度|[一二三四1-4]季度|상반기|하반기|[1-4]분기|반기", re.I)    # a part of a year, in Chinese or Korean too
FROM_TO = re.compile(r"\bfrom\s+(?:about\s+|c\.\s?|~)?$", re.I)
# a verb (or a predicate) of causation, the cause before it: "higher yields lift NII", "the yen weighs on margins",
# "rate hikes are a tailwind for NII" (never a passive: "driven by" names its cause after it, see BECAUSE)
CAUSAL_UP = re.compile(r"\b(?:lift(?:s|ed|ing)?|boost(?:s|ed|ing)?|support(?:s|ed|ing)?|rais(?:e|es|ed|ing)|"
                       r"(?:drives?|drove|driving|driven(?!\s+by))|increas(?:e|es|ed|ing)|"
                       r"benefit(?:s|ed|ing|ting)?(?!\s+from)|help(?:s|ed|ing)?|"
                       r"push(?:es|ed)? up|add(?:s|ed)? to|fe(?:eds?|d|eding)|strengthen(?:s|ed|ing)?|"
                       r"fuel(?:s|led|ed|ling|ing)?|underpin(?:s|ned|ning)?|bolster(?:s|ed|ing)?|spur(?:s|red|ring)?|"
                       r"(?:(?:a|an|the)\s+)?tailwinds?\s+(?:for|to)|(?:(?:a|an)\s+)?(?:net\s+)?positive\s+for|"
                       r"supportive\s+(?:of|for)|(?:positively|favou?rably)\s+(?:affect|impact)(?:s|ed|ing)?)\b",
                       re.I)
CAUSAL_DOWN = re.compile(r"\b(?:weigh(?:s|ed|ing)? on|hurt(?:s|ing)?|pressur(?:e|es|ed|ing)|compress(?:es|ed|ing)?|"
                         r"reduc(?:e|es|ed|ing)|cut(?:s|ting)? into|lower(?:s|ed|ing)?|drag(?:s|ged|ging)? (?:on|down)|"
                         r"erod(?:e|es|ed|ing)|squeez(?:e|es|ed|ing)|dampen(?:s|ed|ing)?|weaken(?:s|ed|ing)?|"
                         r"dent(?:s|ed|ing)?|curb(?:s|ed|ing)?|restrain(?:s|ed|ing)?|hamper(?:s|ed|ing)?|"
                         r"eat(?:s|ing)? into|ate into|moderat(?:e|es|ed|ing)|temper(?:s|ed|ing)?|"
                         r"(?:(?:a|an|the)\s+)?headwinds?\s+(?:for|to)|(?:(?:a|an)\s+)?(?:net\s+)?negative\s+for|"
                         r"(?:negatively|adversely)\s+(?:affect|impact)(?:s|ed|ing)?)\b", re.I)
# a verb of causation with no sign of its own: the effect's words give it ("lower rates lead to NII pressure")
CAUSES = re.compile(r"\b(?:leads? to|led to|results? in|resulted in|translates? into|trigger(?:s|ed|ing)?|"
                    r"caus(?:e|es|ed|ing))\b", re.I)
# a direction a noun gives a value beside it, in a causal claim: "yen weakness", "NII pressure", "an unwind of carry"
SIDE_UP = re.compile(r"\b(?:growth|strength|appreciation|rally|upside|tailwinds?|gains?|improvement|expansion|"
                     r"acceleration|recovery|rebound|uplift)\b", re.I)
SIDE_DOWN = re.compile(r"\b(?:pressures?|weakness|depreciation|downside|headwinds?|slowdown|unwind(?:ing)?|"
                       r"deterioration|declines?|contraction|compression|squeeze|erosion|drag|slide|slump|plunge|"
                       r"sell-?off)\b", re.I)
# a channel the sentence attributes to others in order to doubt it: "we push back on the notion that ..."
DOUBTED = re.compile(r"\b(?:push(?:es|ed|ing)? back (?:on|against)|(?:the )?(?:notion|myth|misconception) that|"
                     r"disagree|skeptic(?:al|ism)|doubtful)\b", re.I)
# an event that opens the sentence, and what moved after it: "Following the BoJ's hike, the yen rose"
FOLLOWING = re.compile(r"^\W*(following|after|in the wake of|in response to|as(?! (?:of|such|a result|expected|well|"
                       r"noted|discussed|mentioned|shown|seen|per|part|long|far|soon|much|many|we|I|you)\b))\b", re.I)
# ... or comes after it: "the yen rose 3% after the BoJ's hike" (an event with no direction causes nothing)
TEMPORAL = re.compile(r"following|after|in the wake of|in response to", re.I)
# "the Fed kept hiking, triggering a slide in the yen": a participle after a comma is the clause's consequence
PARTICIPLE = re.compile(r"^\s*,\s*$")
# "help" takes the sign of the verb it helps: "lower oil prices would help moderate rate hikes"
HELPS = re.compile(r"^help(?:s|ed|ing)?\s+(?:to\s+)?(?=\w)", re.I)
# "Higher yields, which lift NII": a relative clause whose verb is the cause's (no other break before it)
RELATIVE_VERB = re.compile(r"^[^,;:]*?,?\s*\b(?:which|that)\s+(?:(?:should|could|would|will|may|might|can|also|in turn|"
                           r"further|typically|tends? to)\s+)*$", re.I)
# "the effect ... because of the cause": a connector that names its cause after it (the sign is the two directions',
# or the connector's own: "NII benefits from higher rates", "margins were hurt by the stronger yen")
BECAUSE = re.compile(r"\b(?:driven by|thanks to|due to|owing to|on the back of|as a result of|because of|on expectations "
                     r"of|helped by|boosted by|supported by|reflecting|given|benefit(?:s|ed|ing|ting)? from|"
                     r"amid(?:st)?(?: (?:concerns|expectations|fears|hopes|speculation|talk)(?: of| over| about| that)?)?|"
                     r"following|after|in the wake of|in response to|"
                     r"(?:lifted|aided|underpinned|bolstered|fuell?ed) by|"
                     r"(?:hurt|hit|pressured|squeezed|dampened|held back|constrained|eroded|weighed (?:on|down)|"
                     r"dragged(?: down)?) by)\b", re.I)
EXPECTATION = re.compile(r"on expectations|given|amid(?:st)? \w", re.I)   # a premise or a mood, not what happened
PAST = re.compile(r"(?:ed|drove|fed)\b", re.I)             # "higher yields lifted NII" reports; "lift" states a mechanism
MODAL = re.compile(r"\b(?:should|could|would|will|may|might|can|if|unless)\b", re.I)
BY_UP = re.compile(r"^(?:helped|boosted|supported|lifted|aided|underpinned|bolstered|fuell?ed|benefit)", re.I)
BY_DOWN = re.compile(r"^(?:hurt|hit|pressured|squeezed|dampened|held|constrained|eroded|weighed|dragged)", re.I)
LEADS_TO = re.compile(r"\b(?:leads? to|led to|results? in|translates? into|pricing in|priced in)\b", re.I)
SOURCE_REACH = 28                      # how far before a mention a direction word still qualifies it ("lower Bund yields")
CAUSAL_REACH = 80                      # at most this many characters between a cause and its effect
CLAUSE_BREAK = re.compile(r"\b(?:and|but|while|which|whereas)\b|[,;:]")
BECAUSE_BREAK = re.compile(r"\b(?:and|but|while|which|whereas)\b|;")   # "NII rose 5%, thanks to ...", not "... but helped by"
# yields named without their market: "higher yields", "long-term bond yields"
BARE_YIELDS = re.compile(r"\b(?:(?:long-term|long-dated|longer-dated|longer-term|bond|government bond|sovereign)\s+)?"
                         r"yields\b", re.I)
# ... unqualified: after a direction or a function word, not a tenor or another noun ("30-year yields", "real yields")
BARE_BEFORE = re.compile(r"(?:^|\b(?:the|higher|lower|rising|falling|elevated|firmer|softer|and|of|in|as|with|from|on)\s+|"
                         r"[,(]\s*)$", re.I)
# a causal word used as a noun ("a 25bp increase", "the boost", "further pressure") is no verb
NOUN_FORM = re.compile(r"(?:\b(?:a|an|the|its|their|this|that|further|more|any|some|no)|\d[\d.,]*\s*(?:bps?|%|pp)?|['’]s)"
                       r"\s+$", re.I)
# "yields are 5bp lower": "lower" as a predicate, not a verb
PREDICATE = re.compile(r"\b(?:is|are|was|were|be|been|being|ends?|ended|closed|much|slightly|significantly|roughly|"
                       r"modestly|far|even|bps?|points?)\s+$|\d\s*(?:bps?|%|pp)?\s+$", re.I)
# a sector with its region, the model's companies of both: "Japanese insurers", "US banks", "European lenders"
GROUP_REGIONS = {"JP": re.compile(r"Japan(?:ese|['’]s)?", re.I), "US": re.compile(r"(?-i:US|U\.S\.)|American", re.I),
                 "EU": re.compile(r"European|Euro(?:pe|zone|-area| area)(?:['’]s)?", re.I),
                 "CN": re.compile(r"Chin(?:a|ese)(?:['’]s)?", re.I)}
GROUP_SECTORS = {"insurance": re.compile(r"(?:(?:non-life|life|P&C|property and casualty)\s+)?(?:insurers|insurance "
                                         r"companies)", re.I),
                 "banking": re.compile(r"(?:(?:large|regional|commercial)\s+)?(?:banks|lenders)", re.I),
                 "autos": re.compile(r"(?:automakers|carmakers|auto ?makers|car ?makers|automobile manufacturers)", re.I),
                 "machinery": re.compile(r"(?:machinery|equipment) makers", re.I),
                 "telecom": re.compile(r"(?:telcos|telecoms? operators|telecoms? carriers)", re.I)}
GROUP = re.compile(r"\b(?P<region>" + "|".join(p.pattern for p in GROUP_REGIONS.values()) + r")\s+(?P<sector>"
                   + "|".join(p.pattern for p in GROUP_SECTORS.values()) + r")\b", re.I)
# a value named outright, or a market's by the region in view ("10-year yields" in a note on the US), may end a new link;
# a company's value read from the document's subject or the last sentence may not
OUTRIGHT = ("name", "sentence", "region", "document")
LINK_REACH = 40                        # ... and for proposing a new link, at most this many
MODIFIER = re.compile(r"\s+(?!(?:and|or|but|to|in|on|of|at|by|for|as|is|are|was|were|has|have|had|will|would|could|"
                      r"may|might|should|can|be|been|that|which|while|with|from|than|its|their|the|a|an)\b)(?:[a-z]{3,}|[A-Z]{2,}\b)")
NOT = re.compile(r"\b(?:not|never|no longer|unlikely|nor|neither)\b|n['’]t\b", re.I)
# a claim that is denied or only supposed is no claim: "is unlikely to fall", "did not raise", "could rise"
NEGATED = re.compile(r"\b(?:not|never|no|unlikely|nor|neither|could|might|would|suggests?|difficult to|hard to)\b|(?-i:\bmay\b)|n['’]t\b", re.I)
# ... nor is one the sentence frames as a condition, a risk, a scenario, or a question
SUPPOSED = re.compile(r"\b(?:if|unless|whether|absent|barring|scenario|hypothetical|sensitivity|based on an?|catalysts?|"
                      r"for (?:a|an|every|each) [+]?\d[\d.]*\s?(?:bp|bps|%|pp)|(?:upside|downside|key) risks?|risks? "
                      r"(?:to|include|includ\w*|are|is|of|that)|conditional)\b|^\s*(?:Exhibit|Figure|Chart|Table|Source)\b", re.I)
RISK_LIST = re.compile(r"\b(?:upside|downside|key) risks?\b|\brisks? (?:include|includ\w*|are|to)\b", re.I)
# a figure against consensus is no move of the value: "we are 2% higher than consensus"
CONSENSUS = re.compile(r"\b(?:than|vs\.?|versus|above|below|ahead of|behind)\s+(?:the\s+)?(?:consensus|cons\.?|street)\b",
                       re.I)
# an adjective before a value that the sentence goes on to use as a cause ("higher oil prices should aid SGD")
AS_CAUSE = re.compile(r"\b(?:should|would|could|will|may|might|can|tends?|means?|implies|aids?|helps?|hurts?|tilts?|"
                      r"leads?|pushes|supports?|weighs?|drives?|boosts?|benefits?|lifts?)\b", re.I)
# a figure for a group of companies is no one company's: "we raised our NIM forecasts for select banks"
SECTOR_WIDE = re.compile(r"\b(?:for|across|at) (?:the )?(?:select(?:ed)?|most|all|some|several|many|other)? ?(?:banks|names|"
                         r"companies|peers|insurers|lenders|sector|group|money centers?|trust banks|regionals)\b|\bon a median basis\b|"
                         r"\bin aggregate\b", re.I)
# "interest rates" names the rate environment, not a decision: a cause in a channel, never a level or a move
GENERIC_RATES = {"interest rate", "short-term rate"}
# research boilerplate: disclaimers, disclosures, and legal notices make no claims about the model
BOILERPLATE = re.compile(
    r"\b(?:investors? (?:may|should|must|could)|past performance|may go down as well as up|not (?:an? )?(?:offer|solicitation)"
    r"|analyst certification|important disclosures?|disclosure appendix|required disclosures?|conflicts? of interest"
    r"|(?:no|any) (?:representation|warranty)|regulated by|authori[sz]ed and regulated|registered (?:office|in england)"
    r"|all rights reserved|copyright|for (?:professional|institutional|qualified) (?:investors|clients)"
    r"|without (?:the )?(?:prior )?(?:written )?(?:consent|permission)|price target (?:methodology|risks?)"
    r"|ratings? (?:system|definitions?|distribution)|this (?:report|document|publication|material|research) "
    r"(?:is|has been|was|may|does|should|must|contains)|independent (?:investment )?decisions?|investment advice)\b", re.I)
MIN_LOG_BAND = 0.15                    # at least ±16% around a lognormal value's mean is plausible
MAX_POINTS = 2.0                       # a rate rarely moves more than two points in one claim
UNDIRECTED_SD = 0.5                    # a direction without a size: half a standard unit, as a weak move
LINK_EFFECT = 0.3                      # a proposed new link's size before review
LLM_CONFIDENCE = 0.5                   # an item the LLM step alone read
CONTEXT_SENTENCES = 3                  # an entity named this many sentences ago no longer resolves a value phrase

# -- dates --------------------------------------------------------------------------------------------------------
DATE_PATTERNS = [
    re.compile(r"\b(?P<y>20\d{2})-(?P<m>\d{2})-(?P<d>\d{2})\b"),
    re.compile(r"\b(?P<mon>Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?\s+(?P<d>\d{1,2}),?\s+(?P<y>20\d{2})\b"),
    re.compile(r"\b(?P<d>\d{1,2})[\s-]+(?P<mon>Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?,?[\s-]+(?P<y>20\d{2})\b"),
]


def _date(y: str, m: str | None, d: str, mon: str | None = None) -> datetime | None:
    try:
        month = MONTHS[mon.lower()[:3]] if mon else int(m)
        return datetime(int(y), month, int(d), tzinfo=UTC)
    except (ValueError, KeyError, TypeError):
        return None


def find_date(text: str, filename: str = "") -> datetime | None:
    """The document's date: the first full date in its opening text, else one in its file name (dates.py)."""
    return resolve_dates(text, filename).published


# -- numbers ------------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Num:
    value: float                       # in the number's own unit (a percent stays 4.0 for "4%")
    unit: str                          # "%", "bp", "pp", "x", or ""
    currency: str                      # "$", "¥", ... or ""
    scale: float
    start: int
    end: int
    negative: bool
    signed: bool = False               # written with a sign ("+10%", "-2%"): the sign is a direction
    range: bool = False                # the midpoint of a range ("3.75-4.0%", "5-10bp")
    blank: bool = False                # an empty table cell ("-", "n.a."): a column with no figure
    year: bool = False                 # a bare four-digit year ("2025" in a header): a date, not a level


def _unit(u: str) -> str:
    u = u.replace("-", "")
    if u in ("pp", "%p") or u.startswith(("percentagepoint", "pctpt", "ppt")) or "百分" in u:
        return "pp"
    if u in ("%", "pct", "퍼센트") or u.startswith("perc"):
        return "%"
    if u.startswith(("basispoint", "bp")):
        return "bp"
    return "x" if u == "x" else ""


def numbers(text: str, yen: str = "¥") -> list[Num]:
    """The figures in `text`. A bare ¥ is the currency `yen` names ("¥" for the Japanese yen, "CNY" for the yuan:
    units.resolve_yen decides from the document); a sign that names its currency ("JP¥", "CN¥", 円, 元) keeps it."""
    out: list[Num] = []
    for m in NUMBER.finditer(text):
        prev_char = text[m.start("num") - 1] if m.start("num") else ""
        if not (m.group("sign") or m.group("cur")) and prev_char and (
                (prev_char.isalnum() and not CJK_CHAR.match(prev_char)) or prev_char in "*^"):
            continue                                     # figures inside a word ("FY26", "3Q26") or footnotes ("*1")
        v = float(m.group("num").replace(",", ""))
        unit = _unit((m.group("unit") or "").lower().replace(" ", ""))
        sign_cur = m.group("cur") or ""
        cur = CODES.get(sign_cur.lower(), sign_cur) if sign_cur else ""
        cur = cur or CODES.get((m.group("code") or "").lower(), "") or CURRENCY_SUFFIX.get(m.group("cursuf") or "", "")
        if sign_cur == "¥":
            cur = yen                                    # the one sign that names no currency by itself
        scale_word = (m.group("scale") or "").lower()
        scale = SCALE.get(scale_word, 1.0) if scale_word not in CURRENCY_ONLY_SCALES or cur else 1.0
        cscale = m.group("cscale")
        if cscale and not ("조" in cscale and ARTICLE.search(text[:m.start("num")])):
            scale = scale_value(cscale)
            v += tail_value(m.group("tail") or "") / scale    # "3억 5천만": 3 and 5천만 (5e7) of 1e8 is 3.5
        sign = m.group("sign") or ""
        at = m.start("sign")
        if sign and text[at + 1].isspace() and (at == 0 or text[at - 1].isspace()):
            sign = ""                                    # " - 812.0": a dash standing alone is an empty cell
        first = min(x for x in (at if sign else None, m.start("cur") if m.group("cur") else None,
                                m.start("num")) if x is not None)
        bare = re.fullmatch(r"(?:19|20)\d{2}", m.group("num")) is not None and not (unit or cur or sign or cscale or scale_word)
        n = Num(v, unit, cur, scale, first, m.end(), negative=bool(sign) and sign in "-−–", signed=bool(sign), year=bare)
        prev = out[-1] if out else None
        # "3.75-4.0%", "5-10bp", "$4.06-4.16b": two numbers joined by a dash, the second larger, read as the midpoint
        if prev is not None and n.negative and not prev.signed and RANGE_JOIN.match(text[prev.end:m.start("num")]) \
                and prev.unit in ("", unit) and v > prev.value and (not prev.currency or prev.currency == cur or not cur):
            scale = SCALE.get(scale_word, 1.0) if prev.currency else scale       # "$4.06-4.16b": the b is the range's
            n = Num((prev.value + v) / 2, unit, prev.currency or cur, max(scale, prev.scale), prev.start, m.end(),
                    negative=False, range=True)
            out[-1] = n
            continue
        out.append(n)
    return out


def _unit_kind(unit: str) -> str:
    u = unit.lower()
    if u.startswith("pct") or u == "%" or "pct" in u:
        return "rate"
    return "level"


def _unit_scale(unit: str) -> float:
    """How many units of a value's unit one of its units is: ¥bn/yr is 1e9, ¥tn/yr 1e12, m units/yr 1e6."""
    u = unit.lower()
    for word, k in (("tn", 1e12), ("bn", 1e9), ("mn", 1e6), ("m ", 1e6)):
        if word in u:
            return k
    return 1.0


# -- the rules ------------------------------------------------------------------------------------------------------
@dataclass
class Found:
    """A signal the rules found, before it becomes an import signal."""

    type: str                          # observe | move | support | contradict | link
    value_of: str | None = None
    value: float | None = None
    delta: float | None = None
    mode: str = "absolute"
    source: str | None = None
    target: str | None = None
    label: str = ""
    effect: float = 0.0
    quote: str = ""
    rule: str = ""
    confidence: float = 0.7
    direction: int = 0                 # +1 up, -1 down, 0 neither (for the item's stance)

    def signal(self) -> dict[str, Any]:
        note = f"rule: {self.rule}"
        if self.type == "observe":
            return {"type": "observe", "value_of": self.value_of, "value": round(self.value, 6), "quote": self.quote, "note": note}
        if self.type == "move":
            return {"type": "move", "value_of": self.value_of, "delta": round(self.delta, 6), "mode": self.mode,
                    "quote": self.quote, "note": note}
        if self.type == "link":
            return {"type": "link", "source": self.source, "target": self.target, "label": self.label,
                    "effect": self.effect, "quote": self.quote, "note": note}
        return {"type": self.type, "source": self.source, "target": self.target, "strength": 0.5, "quote": self.quote,
                "note": note}


@dataclass
class Reading:
    """What reading a document carries from sentence to sentence: the entities named in the last few sentences (the
    context, with how many sentences ago, the most recent last), the document's subject, region, and date, and the last
    table header seen on the current page."""

    recent: list[tuple[str, int]] = field(default_factory=list)
    subject: str | None = None
    region: str | None = None
    date: datetime | None = None
    ref: datetime | None = None         # the end of the period the document reports on (a report of FY2025 published in 2026)
    header: Header | None = None
    page: int | None = None
    columns: list[list[str]] = field(default_factory=list)   # a sheet's header rows over its entity rows, top first
    after_data: bool = True             # whether the last spreadsheet row had figures (a new header row starts afresh)
    scenario: bool = False              # under a scenario's heading ("Upside Scenario"), its bullets are supposed
    past: bool = False                  # the last sentence was about earlier years only (an episode being told)
    stranger: bool = False              # the last sentence named, in the possessive, someone the model does not know
    forward: bool = False               # a guidance or an outlook: its figures are plans, not results
    partial: bool = False               # the document reports a month, a quarter, or a half: a year's flow needs its own words

    @property
    def when(self) -> datetime | None:
        """The date a year's flow and the history of a sentence are judged against: the period the document reports on, else
        when it was published."""
        return self.ref or self.date


# a column of an entity-row table ("Company | ... | CET1 Ratio, % | ..."): a past or forward period relative to the
# latest ("FY-1", "FY", "MRQ-3", "NTM", "Price a Week Ago"), or a copy converted to another currency ("(USD)")
RELATIVE = re.compile(r"^(?:FY|FQ|FH|CY|MRQ|MRHY|MRP)(?:\s?[-+]\s?\d+)?\b|^(?:LTM|NTM)\b|\bago\b", re.I)
CONVERTED = re.compile(r"\((?:USD|EUR|JPY|GBP|CHF|CAD)\)")
LATEST = re.compile(r"^(?:MRP|MRQ|Current|Latest)$", re.I)
PRICED = re.compile(r"(?P<sign>[-+−])?(?P<n>\d+(?:\.\d+)?)\s?bps?\s+(?:of\s+(?:rate\s+)?(?P<dir>hikes?|cuts?|tightening|"
                    r"easing)\s+)?(?:is\s+|are\s+|now\s+|currently\s+)?priced\b", re.I)
MEAN = re.compile(r"(?:Mean|Average|Avg\.?|Consensus(?: mean)?)", re.I)
GROUP_ROWS = 4                          # how many header rows above an entity-row table are read
HEADER_LINES = 12                       # ... from at most this many lines (a cell's line break splits its row)

LABEL_GAP = re.compile(r"^[\sA-Za-z.*/:'’-]*$")          # a row label's tail, parentheticals dropped: "(¥ bn) New"
LABEL_WORDS = re.compile(r"\b(?:at|to|of|is|was|were|are|by|from|in|for|on|and|the|we|our|with|than|vs)\b", re.I)
LABEL_CHARS = 40
BLANK = re.compile(r"--?|—|–|n\.?a\.?|n/a|NM|nm")       # an empty cell
FOOTNOTE = re.compile(r"\*\d*")
PERCENT_HINT = re.compile(r"\(%\)|,\s?%|%\s*$|\bratio\b", re.I)
# a row of old figures, of consensus, or of changes and sensitivities is not the value's level
OLD_LABEL = re.compile(r"\b(?:Old|Prior|Previous|consensus|cons\.?|per|sensitivity|impact|changes?|chg|growth|y/y|high|"
                       r"low|average|avg|range|assumptions?|assumed|"
                       r"yoy|q/q|Δ|∆)(?![\w])", re.I)
GROWTH_LABEL = re.compile(r"^(?:growth|y/y|yoy)$", re.I)     # ... though a growth rate's own row is its level
# a market's price is read on a date ("9/25/2026", "Current"), never at a period's end or as its average ("Q2-2026")
MARKET_KINDS = {"asset_price", "fx_rate", "bond_yield", "commodity_price", "volatility"}
MODEL_AFTER = 3                         # whole figures before a computed one that mark a model's projection
HALF_YEAR_QUARTERS = 2                  # a year with this many quarters reported is read, though the model completes it
PARTLY_MODELLED = 0.7                   # ... with less confidence than a figure stated for the year
CHECK_ROW = re.compile(r"\s=\s|\b(?:check|diff(?:erence)?|variance)\b", re.I)    # a model's own consistency rows
CUMULATIVE = re.compile(r"\b(?:cumulative|YTD|year[- ]to[- ]date)\b", re.I)


class Rules:
    def __init__(self, graph: WorldView, gazetteer: Gazetteer, inverted: frozenset[str] | set[str] = frozenset(),
                 yen: str = "¥") -> None:
        self.graph = graph
        self.yen = yen                  # what a bare ¥ is in this document (units.resolve_yen): "¥" or "CNY"
        self.gz = gazetteer
        # patterns for surfaces that name a value's reciprocal ("the yen" for USD/JPY), from the world's templates
        self.inverted = [re.compile(p, re.I) for p in sorted(inverted)]
        self.links = {(i.source_id, i.target_id): i for i in graph.links}
        # what each value adds into through accounting, identity and stock-flow links (its totals)
        self._into: dict[str, set[str]] = {}
        for i in graph.links:
            if i.fixed:
                self._into.setdefault(i.source_id, set()).add(i.target_id)
        self._members: dict[str, list[Match]] = {}      # the companies a sector named in the sentence stands for
        # the markets whose values are bond yields, one per region ("yields" in a note on Japan are the JGBs')
        self.bond_markets = sorted({s.entity_id for s in graph.values.values()
                                    if s.attribute_kind == "bond_yield"
                                    and s.entity_id in gazetteer.markets})
        # the head words of each entity's values ("yield" for the JGBs, "profit" for a company)
        self.heads = {e: {norm(n.split()[-1]) for sid in ent.subentity_ids for n in (
            graph.values[sid].name, *graph.values[sid].aliases) if n.split()}
            for e, ent in graph.entities.items()}

    # -- one value, one number --------------------------------------------------------------------------------
    def _posterior(self, sid: str) -> tuple[float, float]:
        s = self.graph.values[sid]
        return s.mean, max(s.sd, 1e-9)

    def _family(self, sid: str) -> str:
        return self.graph.values[sid].family

    def plausible_level(self, sid: str, v: float) -> bool:
        mean, sd = self._posterior(sid)
        scale = float(self.graph.values[sid].scale or 1.0)
        if self.graph.values[sid].unit == "index" and self.graph.values[sid].attribute_kind == "asset_price":
            return v > 0                 # a market index rebased in the model: a quoted level is in its own points
        if self._family(sid) in ("lognormal", "gamma"):
            # within six of the value's own standard units (a log scale), so ¥197 is no USD/JPY but ¥6,994 a share
            return v > 0 and mean > 0 and abs(math.log(v / mean)) <= max(6 * scale, MIN_LOG_BAND)
        return abs(v - mean) <= 6 * sd + 4 * scale

    def _raw_level(self, sid: str, n: Num) -> float | None:
        """The number in the value's unit, or None when the units don't fit (no plausibility check)."""
        unit = self.graph.values[sid].unit
        if _unit_kind(unit) == "rate":
            if n.unit == "%":
                v = n.value
            elif n.unit == "bp":
                v = n.value / 100.0
            else:
                return None
        else:
            if n.unit in ("%", "bp", "pp", "x") or n.year:
                return None
            # the unit's own currency is the first one it names ("¥ per $" is in yen, "€ per ¥100" in euros)
            low = unit.lower()
            named = sorted((low.find(x), c) for c, names in CURRENCY.items() for x in names if x in low)
            want = named[0][1] if named else ""
            if n.currency and (want and n.currency != want or unit == "index"):    # an index is in no currency
                return None
            v = n.value * n.scale / _unit_scale(unit) if n.scale != 1.0 else n.value
        return -v if n.negative else v

    def _level(self, sid: str, n: Num) -> float | None:
        """The number as a level of the value, in its unit, or None when the units don't fit or it is implausible."""
        v = self._raw_level(sid, n)
        return v if v is not None and self.plausible_level(sid, v) else None

    def _delta(self, sid: str, n: Num, direction: int) -> tuple[float, str] | None:
        """The number as a change of the value: (delta, mode), signed by the direction."""
        unit = self.graph.values[sid].unit
        rate = _unit_kind(unit) == "rate"
        if n.unit == "bp":
            d, mode = n.value / 100.0, "absolute"
            if not rate:
                return None
        elif n.unit == "pp":
            if not rate:
                return None
            d, mode = n.value, "absolute"
        elif n.unit == "%":
            if rate:
                d, mode = n.value, "absolute"          # "rose by 0.25%" of a rate is a quarter point
            else:
                d, mode = n.value / 100.0, "relative"
        else:
            return None
        if d == 0 or d > (MAX_POINTS if mode == "absolute" else 0.9):
            return None
        return (direction * abs(d), mode)

    def _change(self, sid: str, old: Num, new: Num) -> tuple[float, str] | None:
        """A revision from `old` to `new`: points for a rate, else the relative change (both in the same units)."""
        if _unit_kind(self.graph.values[sid].unit) == "rate":
            a, b = self._raw_level(sid, old), self._raw_level(sid, new)
            if a is None or b is None or a == b or abs(b - a) > MAX_POINTS:
                return None
            return (b - a, "absolute")
        if old.unit != new.unit or old.unit in ("%", "bp", "pp") or (old.currency and new.currency
                                                                       and old.currency != new.currency):
            return None
        a, b = old.value * (old.scale if old.scale != 1.0 else new.scale), new.value * new.scale
        if a <= 0 or b <= 0 or a == b or not 0.1 < b / a < 1.9:
            return None
        return (b / a - 1.0, "relative")

    @staticmethod
    def _direction(text: str) -> int:
        up = UP.search(text)
        down = DOWN.search(text)
        if up and not down:
            return 1
        if down and not up:
            return -1
        if up and down:
            return 1 if up.start() < down.start() else -1
        return 0

    def local_direction(self, sent: str, start: int, end: int, lo: int = 0, hi: int | None = None) -> int:
        """The direction the words next to a mention give it: its verb (up to six words after it, within its clause)
        or its adjective (up to four words before it): "NII rose", "estimates for NII were cut", "lower NII"."""
        hi = len(sent) if hi is None else hi
        after = re.split(r"[;:]|,\s|\s[–—-]\s|\b(?:but|while|whereas|and|which|as|than)\b", sent[end:hi], maxsplit=1)[0]
        after = BECAUSE.split(after, maxsplit=1)[0]      # "NII was flat due to weaker demand": the demand's word
        after = COMPARATIVE_NOUN.sub(" ", after)        # "point to weaker manufacturing PMI": weaker is the PMI's
        after = _licensed(after)                        # "the yen has increased the urgency to hike": not the yen's
        after = TRANSITIVE.sub(" ", after)              # "the yen raises import costs": the costs rise, not the yen
        d = self._direction(" ".join(after.split()[:6]))
        if d:
            return d
        before = re.split(r"[;:,()]|\b(?:and|but|while|whereas|which|as|than)\b", sent[lo:start])[-1]
        if re.search(r"\bof\s+(?:the\s+|its\s+|their\s+)?$", before):
            return 0                                     # "the imports of crude oil": the value is another noun's
        words = _licensed(before).split()[-4:]
        # an adjective or a verb right before it ("a weaker yen", "cut its rate"), not across a preposition ("OCG
        # weakening from the yen": the yen is the cause)
        k = max((i + 1 for i, w in enumerate(words) if w.lower() in PREPOSITIONS), default=0)
        if AS_CAUSE.search(" ".join(sent[end:hi].split()[:4])):
            return 0                                     # "higher oil prices should aid SGD": oil is the cause here
        return self._direction(" ".join(words[k:]))

    def _modified(self, sent: str, m: Match) -> bool:
        """Whether the mention modifies another measure ("USD/JPY volatility", "yen borrowing", "NII growth",
        "NII ex-markets") rather than standing for the value, unless that word belongs to the value's own name
        ("TSF growth" is total social financing growth)."""
        nxt = re.match(r"\s+([a-z][a-z-]+)", sent[m.end:])
        if not nxt or not (norm(nxt.group(1)) in MODIFIED_BY or nxt.group(1).startswith("ex-")):
            return False
        s = self.graph.values[m.subentity_id]
        return norm(nxt.group(1)) not in {norm(w) for name in (s.name, *s.aliases) for w in name.split()}

    def _premodified(self, sent: str, m: Match) -> bool:
        """Whether a value named by a phrase that leaves out its entity ("volatility", "share price", "issuance")
        follows another noun that makes it something else's: "implied volatility", "sector share prices"."""
        if m.via == "name" and (self._own_words(m) - GENERIC_NAME_WORDS) & {
                norm(w) for w in re.findall(r"[A-Za-z0-9&/-]+", m.surface)}:
            return False
        prev = re.search(r"(?:^|\s)([A-Za-z][A-Za-z-]*)\s+$", sent[max(0, m.start - 30):m.start])
        return bool(prev) and prev.group(1).islower() and prev.group(1) not in PRE_OK \
            and not UP.fullmatch(prev.group(1)) and not DOWN.fullmatch(prev.group(1))   # "raised rates": a verb

    def _component(self, sent: str, m: Match) -> bool:
        """Whether a value named by an alias (not its own name) sits in a list of labelled parts that moved both ways
        ("converts (-23%) and IPOs (-66%) declined, while follow-on issuance rose", "rates (MOVE -5%) were lower, while
        volatility in commodities (OVX +56%) jumped"): one part, or another's, is not the whole the value stands for."""
        named = norm(m.surface) == norm(self.graph.values[m.subentity_id].name)
        return not named and len(LABELLED.findall(sent)) >= 2 and bool(UP.search(sent)) and bool(DOWN.search(sent))

    def _foreign(self, sent: str, m: Match) -> bool:
        """Whether a value phrase that names no entity ("NII", "GDP growth"), resolved from the context or the
        document, follows on its own line an acronym the model does not know, another actor's ("KEY FY26 NII up
        9-11%", "The BCB lowered its GDP forecast")."""
        if m.via in ("name", "sentence"):
            return False
        lead = sent[sent.rfind("\n", 0, m.start) + 1:m.start]
        return any(t not in COMMON_ACRONYMS and t not in METRICS and t.lower() not in self.gz.surface_words
                   and t not in self.gz.surface_words for t in ACRONYM.findall(lead))

    def _own_words(self, m: Match) -> set[str]:
        e = self.graph.entities.get(m.entity_id)
        return {norm(w) for name in ((e.name, "", *e.aliases) if e else ())
                for w in re.findall(r"[A-Za-z0-9&/-]+", name)}

    def _flip(self, m: Match) -> int:
        return -1 if any(r.fullmatch(m.surface) for r in self.inverted) else 1   # "the yen strengthened": USD/JPY fell

    def value_claims(self, sent: str, m: Match, nums: list[Num], prev_end: int, next_start: int,
                     date: datetime | None = None, linked: bool = False, others: bool = False,
                     ref: datetime | None = None, partial: bool = False) -> list[Found]:
        """What the sentence says about one value: a revision from one figure to another, its level, a move with a
        size, else a bare direction (unless the sentence states a channel through the value, `linked`, or a causal
        word joins it to another entity, `others`). Each is read from the value's clause: from the previous mention
        to the next.
        With the document's `date`, a sentence only about earlier years is history (no claim), and a level for a
        year two or more years out is a long-range forecast (no level)."""
        sid = m.subentity_id
        assert sid is not None
        ref = ref or date
        flip = self._flip(m)
        clause = sent[prev_end:next_start]
        # the years the clause is about ("for the first time since 2007" dates nothing)
        years = {int(y) for y in YEAR.findall(re.sub(r"\bsince\s+\S+", " ", clause))}
        rate = _unit_kind(self.graph.values[sid].unit) == "rate"
        # a target is not the value, though a market forecaster's revised target for a rate is a move in its view
        aimed = TARGET.match(sent[m.end:]) or TARGET_BEFORE.search(sent[max(0, m.start - 12):m.start])
        if (aimed and not rate) or NEGATED.search(clause) or SUPPOSED.search(sent) or HISTORY.search(sent) or sent.rstrip().endswith("?") \
                or (ref is not None and years and max(years) < ref.year) or self._modified(sent, m) \
                or self._premodified(sent, m) or (m.via == "document" and m.entity_id in self.gz.policy) \
                or self._generic(m) \
                or (m.via != "name" and SECTOR_WIDE.search(clause)) \
                or re.search(r"\b(?:bn|mn|tn|billions?|millions?|trillions?)\s*$", sent[max(0, m.start - 12):m.start], re.I) \
                or OTHER_BASIS_LEAD.search(sent[prev_end:m.start]) or self._component(sent, m) or self._foreign(sent, m) \
                or _aim(sent[prev_end:m.start]):
            return []
        after = [n for n in nums if m.end <= n.start < next_start]
        before = [n for n in nums if prev_end <= n.start and n.end <= m.start and m.start - n.end <= 14
                  and not re.search(r"[;:,.]", sent[n.end:m.start]) and not BECAUSE.search(sent[n.end:m.start])]
        out: list[Found] = []
        # 1. a revision: "from ¥592bn to ¥654bn", "to 7.3% from 7.5%"
        for a, b in zip(after, after[1:]):
            lead = sent[m.end:a.start]
            if len(lead) > 60 or re.search(r"[,;:]", lead):
                break                                    # the revision is the value's own, in its clause
            between = sent[a.end:b.start]
            pair = ((a, b) if FROM_TO.search(lead) and re.fullmatch(r"\s*to\s*", between) else
                    (b, a) if re.search(r"\bto\s*$", lead) and re.fullmatch(r"\s*\(?from\s*", between) else None)
            got = self._change(sid, *pair) if pair and flip == 1 else None
            if got:
                return [Found("move", value_of=sid, delta=got[0], mode=got[1], quote=sent,
                              rule="from one figure to another", confidence=0.8, direction=1 if got[0] > 0 else -1)]
        if aimed or PREVIEW.search(_part(sent, m.start, m.end)):
            return []                    # a revision is news; a preview, a base case, or someone's guidance is not
        # the words around the value, else its own ("two more rate hikes")
        direction = flip * (self.local_direction(sent, m.start, m.end, prev_end, next_start) or self._direction(m.surface))
        # 2. a growth rate's own level: "core CPI rose 1.7% y-o-y", "TSF growth (+7.2% YoY)"
        if "y/y" in self.graph.values[sid].unit and flip == 1:
            for n in after:
                if n.unit == "%" and n.start - m.end <= 40 and YOY.match(sent[n.end:]) and not FROM_TO.search(
                        sent[m.end:n.start]) and (lvl := self._level(sid, n)) is not None:
                    return [Found("observe", value_of=sid, value=lvl, quote=sent, rule="growth rate", confidence=0.75,
                                  direction=direction)]
        # 3. a level: "at 3.875%", "to 1.25%", "fell to 152", "Price (31 Jul 2026) ¥6,994"
        flow = self.graph.values[sid].unit.endswith("/yr")
        far = date is not None and any(y >= date.year + 2 for y in years)
        stale = date is not None and any((date - d).days > STALE_DAYS for d in _dates_in(sent))
        lead = sent[prev_end:m.start]
        # a market level the sentence only expects ("we expect a further hike to lift the policy rate to 1.50%")
        expected = EXPECTS.search(AS_EXPECTED.sub(" ", sent[sent.rfind(";", 0, m.start) + 1:m.start]))
        forecast = (not flow and (FORECAST.match(sent[m.end:]) or NOT_NOW.search(lead) or ESTIMATED.search(clause)
                                  or expected)) or AIMED.search(lead) or AVERAGED.search(" ".join(lead.split()[-3:])) \
            or CJK_FORECAST.search(lead)
        for k, n in enumerate(after):
            gap = sent[m.end:n.start]
            between = [x for x in after[:k] if not _inside_parens(sent, m.end, x.start)]
            moved = all(x.unit in ("%", "bp", "pp") for x in between) and re.search(r"\bto\s*$", gap)
            # a flow's figure after its change ("income rose 16% to ¥22bn") is a period's result, a quarter's as
            # likely as the year's, unless the year is named
            if len(gap) > 60 or (between and not moved) or flip != 1 or (flow and QUARTER.search(clause)) \
                    or (flow and between and not FULL_YEAR.search(MONTH_YEAR.sub(" ", clause))) \
                    or far or stale or forecast or EXCLUDING.search(gap) or re.search(r"\bfrom\b", gap) \
                    or CJK_FORECAST.search(re.split(r"[,;，；。]", sent[n.end:], maxsplit=1)[0]) \
                    or (flow and partial and not YEAR_WORDS.search(clause)) \
                    or (_unit_kind(self.graph.values[sid].unit) == "rate" and OTHER_BASIS.match(sent[n.end:])):
                break
            # (a row of a table is not a key-data line: "Research expenses 7 (15,510) (18,356)" is a note number and columns)
            keyed = len(sent) <= KEY_VALUE_CHARS and KEY_VALUE.match(PARENS.sub("", gap)) \
                and sum(not x.unit for x in after[k + 1:]) < 2 and (not flow or YEAR_WORDS.search(sent))
            if flow and n.currency and n.scale == 1.0:
                continue                 # "RMB 10" in a sentence is ten yuan, not ten of the flow's billions: it needs its scale
            if keyed or (LEVEL.search(gap) and not re.search(r"[,;]\s", PARENS.sub("", gap))
                         and not (not flow and PROJECTED.search(gap))):
                lvl = self._level(sid, n)
                if lvl is not None:
                    out.append(Found("observe", value_of=sid, value=lvl, quote=sent, rule="level", confidence=0.75,
                                     direction=direction))
                    break
        # a key-data figure with its label after it: "$95.10 (Stock Price as of 10/01/2026)"
        if not out and flip == 1 and not forecast and len(sent) <= KEY_VALUE_CHARS:
            for n in before:
                if re.fullmatch(r"\s*\((?:[A-Za-z]+\s+){0,2}", sent[n.end:m.start]) and not direction \
                        and (lvl := self._level(sid, n)) is not None:
                    out.append(Found("observe", value_of=sid, value=lvl, quote=sent, rule="key data", confidence=0.75))
        if CONSENSUS.search(clause):
            return out
        if ESTIMATED.search(clause):
            return out                   # a change over estimated years ("inflation CAGR FY26-28E 0.5% higher")
        # a year's flow does not move by a quarter's sequential change ("relative to 2Q26, NII down 2%"), nor a
        # year-on-year rate by a month's print or a sequential change ("core CPI rose 0.2% in August", "TSF up
        # sequentially"); and a pause is no move ("a pause on rate cuts, unchanged since May")
        sized = [n for n in after if n.unit == "%" and n.start - m.end <= 40]
        part = _part(sent, m.start, m.end)
        growth = "y/y" in self.graph.values[sid].unit
        will = WILL_MOVE.match(sent[m.end:next_start])   # "EPS will grow by 13%": a prediction, no move
        if (flow and SEQUENTIAL.search(sent) and not ANNUAL.search(sent) and sized) or PAUSED.search(part) \
                or (will and self._direction(will.group(1))) or (
                growth and (any(MONTHLY.match(sent[n.end:]) for n in sized) or SEQUENTIAL.search(part)
                            or MONTH_ON_MONTH.search(part))):
            return out
        # 4. a move with a size: "raised ... by 25bp", "rose 4%", "~7bp higher", "a 25bp cut in ...", "by +10%"
        for n in after:
            gap = sent[m.end:n.start]
            if (LEVEL.search(gap) and not BY.search(gap)) or FROM_TO.search(gap) or _labelled_parens(sent, m.end, n.start):
                continue                                 # "lower to 1.71%" is a level, "(OVX +56%)" another value
            d = direction or (flip * (-1 if n.negative else 1) if n.signed and BY.search(gap) else 0)
            if d and (BY.search(gap) or (n.unit in ("%", "bp", "pp") and len(gap) <= 40)):
                got = self._delta(sid, n, d)
                if got:
                    return [*out, Found("move", value_of=sid, delta=got[0], mode=got[1], quote=sent,
                                        rule="direction + size", confidence=0.8, direction=d)]
        if direction:
            for n in reversed(before):
                got = self._delta(sid, n, direction)
                if got:
                    return [*out, Found("move", value_of=sid, delta=got[0], mode=got[1], quote=sent,
                                        rule="size + direction before", confidence=0.75, direction=direction)]
            # 5. a bare direction, unless the value has a level here or the sentence is about a channel through it
            # (a connector after the value leaves its own verb a report: "USD/JPY fell amid talk of hikes")
            linked = linked or (others and (any(p.search(clause) for p in (CAUSAL_UP, CAUSAL_DOWN))
                                            or bool(BECAUSE.search(sent[prev_end:m.start]))))
            figures_before = sum(n.end <= m.start for n in nums if n.start >= prev_end) >= 2     # a remark beside a row's figures
            if not out and not linked and not LEADS_TO.search(clause) and " = " not in sent and not figures_before \
                    and not (VIEW_OF.match(sent[m.end:]) and not REVISED.search(sent[prev_end:m.start])) \
                    and not _heading(sent) and not EXPOSED.search(" ".join(sent[prev_end:m.start].split()[-4:])):
                return [Found("move", value_of=sid, delta=direction * UNDIRECTED_SD, mode="standardized", quote=sent,
                              rule="direction without size", confidence=0.45, direction=direction)]
        return out

    # -- table rows ---------------------------------------------------------------------------------------------
    def row_claims(self, sent: str, m: Match, nums: list[Num], reading: Reading) -> list[Found] | None:
        """A table row whose label names the value: None when the sentence is not such a row, else what it claims
        (a level in the column `pick` chooses, or a move from a Previous/Current pair)."""
        sid = m.subentity_id
        assert sid is not None
        if CELL in sent:
            return self._sheet_row(sent, m, reading)
        run: list[Num] = []
        for n in nums:
            if n.start < m.end or (not run and _inside_parens(sent, m.end, n.start)):
                continue                                 # a figure in the label's parenthetical: "(000s)", "(03/27E)"
            if not run:
                gap = sent[m.end:n.start]
                words = gap.split()
                k = next((i for i, w in enumerate(reversed(words)) if not BLANK.fullmatch(w)), len(words))
                label_gap = gap[:gap.rfind(words[-k])] if k else gap
                if len(gap) > LABEL_CHARS or not LABEL_GAP.match(FOOTNOTE.sub("", PARENS.sub("", label_gap))) \
                        or LABEL_WORDS.search(label_gap):
                    return None
                run += [_blank(n.start)] * k            # empty cells before the first figure: "Adjusted net income - 812.0"
            else:
                between = sent[run[-1].end:n.start].split()
                if between and not all(BLANK.fullmatch(w) for w in between):
                    break
                run += [_blank(n.start)] * len(between)
            run.append(n)
        rest = sent[run[-1].end:].split() if run else []
        if rest and all(BLANK.fullmatch(w) for w in rest):
            run += [_blank(len(sent))] * len(rest)      # empty cells after the last figure: "881.5 - -"
        if sum(not n.blank for n in run) < 2:
            return None
        label = sent[:run[0].start]
        if TARGET.match(sent[m.end:]) or TARGET_BEFORE.search(sent[max(0, m.start - 12):m.start]) \
                or self._old_label(sid, label.replace(m.surface, " ")) or self._generic(m):
            return []
        header = reading.header
        if header is None or self._flip(m) != 1:
            return []
        cells = align(list(header.periods), run, rate=_unit_kind(self.graph.values[sid].unit) == "rate")
        if cells is None or (len({p.text for p in header.periods}) < len(header.periods) < len(run)
                             and len(cells[0]) < len(run)):
            return []                    # side-by-side blocks of the same periods (before and after a revision, or
            # two tables), the row running across them: which block is current is not said
        periods, row = cells
        return self._read_cells(sid, sent, label, periods, row, reading)

    @staticmethod
    def _generic(m: Match) -> bool:
        """Whether the mention is a generic rate ("interest rate"), which names no agency's rate by itself."""
        return " ".join(norm(w) for w in m.surface.split()) in GENERIC_RATES

    def _old_label(self, sid: str, label: str) -> bool:
        """Whether a row's label (without the value's own name: "Fed funds target range") marks old figures,
        consensus, or changes rather than the value's level."""
        growth = "y/y" in self.graph.values[sid].unit
        return any(not (growth and GROWTH_LABEL.match(x.group(0))) for x in OLD_LABEL.finditer(label))

    def _sheet_row(self, sent: str, m: Match, reading: Reading) -> list[Found] | None:
        """A spreadsheet row ("Net Interest Income, mm | | 51152 | ..."): cells aligned with the header row by
        position, or a period written in the row itself ("Forward EBIT | FY2027 | 3400000"). The text cells between
        the label and the first figure are the row's unit ("BoJ policy rate | % | 0.75 | 1.25")."""
        spans = cells_of(sent)
        cells = [sent[x:y].strip() for x, y in spans]
        k = next(j for j, (x, y) in enumerate(spans) if m.start < y or j == len(spans) - 1)   # the value's own cell
        label = cells[k]
        if TARGET.search(label) or self._old_label(m.subentity_id, label.replace(m.surface, " ")) or self._flip(m) != 1 \
                or self._generic(m) \
                or (EXCLUDING.search(sent[m.end:spans[k][1]]) and not CORE.search(m.surface)) \
                or _inside_parens(sent, spans[k][0], m.start):
            return []                    # "US CPI (core)" is not headline CPI; "core CPI (ex fresh food)" is core CPI;
            # "Net income (incl. equity gains)" is not the equity book

        def figure(j: int) -> Num | None:
            ns = numbers(cells[j], self.yen)
            return ns[0] if len(ns) == 1 and ns[0].end - ns[0].start == len(cells[j]) else None

        rest = [(j, c) for j, c in enumerate(cells) if j > k and c]
        first_fig = next((j for j, _c in rest if figure(j)), len(cells))
        units = [c for j, c in rest if j < first_fig and not PERIOD.fullmatch(c)]
        hint = ", ".join([label, *units])
        nxt = cells[k + 1] if k + 1 < len(cells) else ""
        years = [int(y) for y in YEAR.findall(sent)]
        if nxt and figure(k + 1) and not self.graph.values[m.subentity_id].unit.endswith("/yr"):
            if PROSPECT.search(label) or (reading.when and years and max(years) < reading.when.year):
                return []                # a projection ("Year-end USD/JPY") or a past episode's row
            # a level and its figure side by side: "USD/JPY | 158.054", "Last Price | 349.31"
            v = self._cell_level(m.subentity_id, hint, figure(k + 1))
            return [Found("observe", value_of=m.subentity_id, value=v, quote=sent, rule="table cell",
                          confidence=0.75)] if v is not None else []
        # a period written before the row's figures: "Forward EBIT | FY2027 | 3400000"
        inrow = [(j, p) for j, c in rest if j < first_fig and (pm := PERIOD.fullmatch(c)) and (p := period_of(pm))
                 and p.kind != "cur"]
        if inrow:
            if inrow[1:] or first_fig == len(cells):
                return []
            # a table of sources with a mean of theirs ("Line item | Period | Broker A | Broker B | n | Mean"): the mean
            heads = reading.columns[-1] if reading.columns else []
            mean = next((j for j, c in enumerate(heads) if j > inrow[0][0] and MEAN.fullmatch(c.strip())), None)
            col = mean if mean is not None and mean < len(cells) and figure(mean) else first_fig
            return self._read_cells(m.subentity_id, sent, hint, [inrow[0][1]], [figure(col)], reading)
        header = reading.header
        if header is None or not header.cells:
            return []
        figures = [n for j in range(k + 1, len(cells)) if (n := figure(j))]
        if CHECK_ROW.search(label) or not any(n.value for n in figures):
            return []                    # a model's check ("NI on IS = NI on CF"), or a row of zeros: no figure
        flow = self.graph.values[m.subentity_id].unit.endswith("/yr")
        modelled = _modelled(cells, k)
        periods, row, partly = [], [], set()
        quarters = 0                     # the year's quarters reported so far (before the model's columns)
        for p, j in zip(header.periods, header.cells):
            quarters += p.kind == "quarter" and j < modelled
            # a model's columns are not read, from its first computed figure on ("13525400 | 12830192.55"), but for
            # a year at least half reported (two quarters in, two modelled); and for a flow, a year that repeats its
            # last quarter is a balance, not a year's flow (unless the row runs cumulative)
            half = p.kind == "year" and quarters >= HALF_YEAR_QUARTERS
            if k < j < len(cells) and (j < modelled or half) and (n := figure(j)) and not (
                    flow and p.kind == "year" and cells[j - 1] == cells[j] and not CUMULATIVE.search(label)):
                periods.append(p)
                row.append(n)
                if j >= modelled:
                    partly.add(f"table row ({p.text})")
            quarters = 0 if p.kind == "year" else quarters
        if not row or (not flow and any(figure(j) for j in range(max(header.cells) + 1, len(cells)))):
            return []                    # a level's figures run on past the dated columns: its latest is not dated
        out = self._read_cells(m.subentity_id, sent, hint, periods, row, reading)
        for f in out:
            if f.rule in partly:         # a year the model completed yields to a figure stated for it (a forward row)
                f.confidence = PARTLY_MODELLED
        return out

    def priced_claims(self, sent: str, ms: list[Match]) -> list[Found]:
        """A move of a policy rate the market prices ("+15bp priced for the next meeting", "25bp of cuts
        priced in"): the agency's rate named in the sentence, by the size priced."""
        got = PRICED.search(sent)
        sid = next((x.subentity_id if x.subentity_id else self.gz.policy.get(x.entity_id) for x in ms
                    if (x.subentity_id and x.via in ("name", "sentence") and self.graph.values[
                        x.subentity_id].attribute_kind == "policy_rate") or (not x.subentity_id
                                                                              and self.gz.policy.get(x.entity_id))), None)
        if not got or sid is None or NEGATED.search(sent[max(0, got.start() - 30):got.end()]):
            return []
        down = got.group("sign") in ("-", "−") or (got.group("dir") or "").lower().startswith(("cut", "eas"))
        size = float(got.group("n")) / 100.0
        return [Found("move", value_of=sid, delta=-size if down else size, mode="absolute", quote=sent,
                      rule="priced by the market", confidence=0.75, direction=-1 if down else 1)]

    def entity_row(self, sent: str, ms: list[Match], reading: Reading) -> list[Found]:
        """A spreadsheet row seen: a row of labels only joins the header rows over the table (a new table's after a
        row of figures); a row whose first cell names one of the model's companies is read as that company's row."""
        if CELL not in sent:
            if not reading.after_data and not FIGURE.search(sent):
                reading.columns = [*reading.columns, [sent]][-HEADER_LINES:]   # the rest of a header cell's text
            return []
        cells = [sent[x:y].strip() for x, y in cells_of(sent)]
        figures = sum(1 for c in cells if FIGURE_CELL.fullmatch(c))
        if not figures and (sum(1 for c in cells if c) >= 3 or not reading.after_data):
            reading.columns = [*([] if reading.after_data else reading.columns), cells][-HEADER_LINES:]
            reading.after_data = False
            return []
        if figures < 3:
            return []
        if not reading.after_data:
            reading.columns = _header_rows(reading.columns, len(cells))
        reading.after_data = True
        first = next((x for x, y in cells_of(sent) if sent[x:y].strip()), 0)
        end = sent.find(" | ", first)
        company = next((m.entity_id for m in ms if m.kind == "entity" and m.entity_id in self.gz.companies
                        and first <= m.start and (end < 0 or m.end <= end)), None)
        if company is None or not reading.columns or FIGURE.search(sent[first:end if end >= 0 else len(sent)]):
            return []
        return self.entity_row_claims(sent, company, reading)

    def entity_row_claims(self, sent: str, company: str, reading: Reading) -> list[Found]:
        """A row of an entity-row table: a company's row under header rows that name each column's measure
        ("Name | Ticker | ... | Static Price (1 Oct) | ... | CET1 Ratio, %"). A column is read as the
        company's value when its header names one of the company's levels (a price, a ratio), in its latest column:
        one headed by the measure itself or "Current"/"MRP" under a group header that names it, never a past or
        forward period ("FY-1", "FY", "MRQ-2", "Price a Week Ago", "Price on 2/1/2025"), consensus, or a copy
        converted to another currency."""
        cells = [sent[x:y].strip() for x, y in cells_of(sent)]
        head_row, groups = reading.columns[-1], reading.columns[:-1]
        out: list[Found] = []
        for j, c in enumerate(cells):
            ns = numbers(c, self.yen)
            head = head_row[j].strip() if j < len(head_row) else ""
            if not head or len(ns) != 1 or ns[0].end - ns[0].start != len(c) or CONVERTED.search(head):
                continue
            if LATEST.match(head):
                # "Current" under a group header ("Stock Price, $"): the group's measure, nearest to the left
                group = next((g[i].strip() for g in reversed(groups) for i in range(min(j, len(g) - 1), -1, -1)
                              if g[i].strip()), "")
                label = f"{group}, {head}"
            elif RELATIVE.search(head) or PERIOD.fullmatch(head):
                continue
            else:
                label = head
            periods = [p for pm in PERIOD.finditer(label) if (p := period_of(pm))]
            dated = _dates_in(label) + [datetime(p.end[0], p.end[1], max(p.day, 1), tzinfo=UTC) for p in periods
                                        if p.kind == "date" and p.end and p.end[0]]
            if OLD_LABEL.search(label) or TARGET.search(label) or (reading.date and any(
                    (reading.date - d).days > STALE_DAYS for d in dated)):
                continue
            ms = self.gz.find(label, [company], subject=company)
            m = next((x for x in ms if x.subentity_id and x.entity_id == company), None)
            if m is None or any(f.value_of == m.subentity_id for f in out) \
                    or self.graph.values[m.subentity_id].unit.endswith("/yr"):
                continue                 # a flow's latest column is a quarter, its FY columns the past
            v = self._cell_level(m.subentity_id, label, ns[0])
            if v is not None:
                out.append(Found("observe", value_of=m.subentity_id, value=v, quote=sent,
                                 rule=f"entity row ({label})", confidence=0.75))
        return out

    def _read_cells(self, sid: str, sent: str, label: str, periods: list[Period], row: list[Num],
                    reading: Reading) -> list[Found]:
        kinds = {p.kind for p in periods}
        if {"prev", "cur"} <= kinds:
            old = next(n for p, n in zip(periods, row) if p.kind == "prev")
            new = next(n for p, n in zip(periods, row) if p.kind == "cur")
            got = self._change(sid, old, new)
            if not got:
                return []
            out = [Found("move", value_of=sid, delta=got[0], mode=got[1], quote=sent, rule="table revision",
                         confidence=0.8, direction=1 if got[0] > 0 else -1)]
            # a flow's row that names the document's fiscal year ("unit sales FY3/27 | 9,500 | 9,650"): its new level
            year = [p for pm in PERIOD.finditer(label) if (p := period_of(pm)) and p.kind == "year"]
            if year and self.graph.values[sid].unit.endswith("/yr") and pick(
                    year[:1], flow=True, date=reading.when, fy_month=self._fy_month(sid)) == 0 \
                    and (v := self._cell_level(sid, label, new)) is not None:
                out.insert(0, Found("observe", value_of=sid, value=v, quote=sent, rule=f"table row ({year[0].text})",
                                    confidence=0.75))
            return out
        if any(p.revision for p in periods):
            return self._revised(sid, sent, label, periods, row, reading)
        unit = self.graph.values[sid].unit
        fy_month = self._fy_month(sid)
        flow = unit.endswith("/yr")
        if flow and reading.partial:
            return []                    # a quarter's document: its table's year column is not told from the quarter's
        if flow and any(p.kind == "year" and not p.fiscal and p.end and p.end[1] != fy_month for p in periods):
            return []                    # years ending in another month: another company's table ("12/26E" for a March FY)
        if flow and any(p.kind == "date" and p.end and p.end[1] != fy_month for p in periods):
            return []                    # a column dated inside the year ("30 June ... 2026"): an interim statement, not a year
        k = pick(periods, flow=flow, date=reading.when if flow else reading.date, fy_month=fy_month)
        p = periods[k] if k is not None else None
        if p is None or (not flow and reading.date and p.end and p.end[0] and (reading.date - datetime(
                *end_of(p, fy_month, reading.date.year), tzinfo=UTC)).days > STALE_DAYS) \
                or (not flow and p.kind not in ("date", "cur")
                    and self.graph.values[sid].attribute_kind in MARKET_KINDS):
            return []                    # no column for now, a level half a year old (a year-end before a later
            # quarter), or a market price at a period's end or on its average ("FY2025", "Q2-2026"): not today's
        v = self._cell_level(sid, label, row[k])
        if v is None:
            return []
        return [Found("observe", value_of=sid, value=v, quote=sent, rule=f"table row ({periods[k].text})",
                      confidence=0.75)]

    def _fy_month(self, sid: str) -> int:
        """The month a value's fiscal year ends in: March for a Japanese company, else December."""
        ent = self.graph.values[sid].entity_id
        return 3 if self.gz.region.get(ent) == "JP" and ent in self.gz.companies else 12

    def _revised(self, sid: str, sent: str, label: str, periods: list[Period], row: list[Num],
                 reading: Reading) -> list[Found]:
        """A row under new and old estimates: the new estimate in the document's period, and its revision from the
        old one for the same period."""
        new = [(p, n) for p, n in zip(periods, row) if p.revision == "cur"]
        out = self._read_cells(sid, sent, label, [replace(p, revision="") for p, _n in new], [n for _p, n in new],
                               reading)
        if out:
            period = out[0].rule[len("table row ("):-1]
            old = next((n for p, n in zip(periods, row) if p.revision == "prev" and p.text == period), None)
            got = self._change(sid, old, next(n for p, n in new if p.text == period)) if old else None
            if got:
                out.append(Found("move", value_of=sid, delta=got[0], mode=got[1], quote=sent, rule="table revision",
                                 confidence=0.8, direction=1 if got[0] > 0 else -1))
        return out

    def _cell_level(self, sid: str, label: str, n: Num) -> float | None:
        """A cell's number as a level: scaled by the row label's unit ("(¥ bn)", "mm", "000s", "(%)", a ratio as a
        fraction), else by the one scale that makes it plausible ("14,805" in € mn is 14.8 €bn)."""
        rate = _unit_kind(self.graph.values[sid].unit) == "rate"
        if n.blank or (n.year and not rate):
            return None
        if rate:
            if n.unit == "" and PERCENT_HINT.search(label):
                # a percent, or a ratio stored as a fraction (0.1419 for 14.19%): the one that is plausible
                fits = [v for x in ((n.value, n.value * 100) if abs(n.value) < 1.5 else (n.value,))
                        if (v := self._level(sid, Num(x, "%", "", 1.0, n.start, n.end, n.negative))) is not None]
                return fits[0] if len(fits) == 1 else None
            return self._level(sid, n)
        if PERCENT_HINT.search(label):
            return None                  # a share or a ratio of the value ("Operating income mix, %") is not it
        hint = scale_hint(label)
        if hint is not None and n.scale == 1.0:
            return self._level(sid, Num(n.value, n.unit, n.currency, hint, n.start, n.end, n.negative))
        if n.scale != 1.0 or n.currency or not self.graph.values[sid].unit.endswith("/yr"):
            return self._level(sid, n)                   # a price or a rate is never rescaled to fit
        fits = {v for k in (1.0, 1e3, 1e6, 1e9, 1e12) if (v := self._level(sid, Num(
            n.value, n.unit, n.currency, k, n.start, n.end, n.negative))) is not None}
        return fits.pop() if len(fits) == 1 else None

    # -- two values and a causal word -------------------------------------------------------------------------
    def _side(self, sent: str, m: Match, lo: int, hi: int, default: int = 1) -> int:
        """A mention's own direction in a causal claim ("higher yields", "rate cuts", "the yen weakened"), `default`
        when none is given; an inverted surface flips it."""
        before = " ".join(sent[max(lo, m.start - SOURCE_REACH):m.start].split()[-2:])
        after = " ".join(sent[m.end:hi].split()[:2])
        d = self._direction(before) or self._direction(after) or self._direction(m.surface) \
            or _noun_direction(after) or _noun_direction(sent[max(lo, m.start - SOURCE_REACH):m.start])
        return self._flip(m) * (d or default)

    @staticmethod
    def _object(sent: str, m: Match) -> bool:
        """Whether a mention is the object of a causal verb before it ("to support the yen", "efforts that lifted
        oil"), so the verb's phrase, not the value, is what the sentence goes on to name as a cause. An adjective is
        no verb: "lower rates", "rising yields"."""
        lead = sent[max(0, m.start - SOURCE_REACH):m.start]
        return any(re.fullmatch(r"\s+(?:(?:the|its|their|a|an)\s+)?", lead[x.end():]) and lead[:x.start()].strip()
                   and not re.fullmatch(r"lower|\w+ing", x.group(0), re.I)
                   for p in (CAUSAL_UP, CAUSAL_DOWN) for x in p.finditer(lead))

    def _reported(self, sent: str, m: Match) -> bool:
        """Whether a direction the sentence gives a value is a claim: not denied, supposed, past, asked, previewed,
        estimated ("est. slightly higher NII"), or a heading's, and the mention stands for the value itself (see
        value_claims)."""
        return not (NEGATED.search(sent) or SUPPOSED.search(sent) or HISTORY.search(sent) or sent.rstrip().endswith("?")
                    or _heading(sent) or self._generic(m) or self._modified(sent, m) or self._premodified(sent, m)
                    or (m.via == "document" and m.entity_id in self.gz.policy) or PREVIEW.search(_part(sent, m.start, m.end))
                    or ESTIMATE_BEFORE.search(sent[max(0, m.start - SOURCE_REACH):m.start]))

    def _modifies(self, m: Match, rest: str) -> bool:
        """Whether a name is followed by the noun it modifies: a lower-case word that is neither a function word
        nor a causal or direction word ("Euro area unemployment", not "Oil lifts" or "BoJ hikes"), nor the head
        word of the entity's own values ("JGB yields" are the JGBs' yields)."""
        nxt = MODIFIER.match(rest)
        return bool(nxt) and not any(p.match(rest.lstrip()) for p in (CAUSAL_UP, CAUSAL_DOWN, UP, DOWN, BECAUSE)) \
            and norm(nxt.group(0).strip()) not in self.heads.get(m.entity_id, ())

    def causal_claims(self, sent: str, matches: list[Match], region: str | None = None) -> list[Found]:
        """Channels the sentence states between the things it names (with `region`, the document's, for bare
        "yields")."""
        out: list[Found] = []
        self._members = {}
        groups = self._groups(sent)
        matches = sorted([m for m in matches if not any(g.start <= m.start < g.end for g in groups)] + groups,
                         key=lambda m: m.start)
        matches = sorted(matches + self._bare_yields(sent, matches, region), key=lambda m: m.start)
        # an entity's name that modifies another noun ("euro area unemployment", "Tokio Marine shares") is not the
        # entity standing for its values
        matches = [m for m in matches if m.subentity_id or not self._modifies(m, sent[m.end:])]
        if RISK_LIST.search(sent) or DOUBTED.search(sent):
            return out                                   # a list of risks pairs things that the sentence does not join;
                                                         # a view the author pushes back on is not the author's
        for k, a in enumerate(matches):
            for b in matches[k + 1:]:
                if b.start - a.end > CAUSAL_REACH:      # mentions come in reading order: the rest are further away
                    break
                if CELL not in sent[a.end:b.start]:     # a channel is stated within one cell of a table
                    read = self._channel(sent, a, b)
                    if read is not None:
                        self._claim(sent, out, *read, adjacent=b is matches[k + 1] and b.start - a.end <= LINK_REACH)
        read = self._following(sent, matches)
        if read is not None:
            self._claim(sent, out, *read, adjacent=False)
        return out

    def _channel(self, sent: str, a: Match, b: Match) -> tuple | None:
        """How two mentions are joined, if by a causal word: (cause, effect, sign, whether the cause's direction is
        stated, the word, and the directions the sentence reports for its ends), else None."""
        between = sent[a.end:b.start]
        why = BECAUSE.search(between)
        # causal verbs, each with its sign, but not a word of the connector ("helped" in "helped by")
        verbs = sorted(((x.start(), x, sign) for p, sign in ((CAUSAL_UP, 1), (CAUSAL_DOWN, -1), (CAUSES, 0))
                        for x in p.finditer(between) if not (why and x.start() < why.end() and why.start() < x.end())
                        and not NOUN_FORM.search(between[:x.start()])
                        and not (x.group(0).lower() == "lower" and PREDICATE.search(between[:x.start()]))),
                       key=lambda t: t[0])
        if why and all(at < why.start() for at, _x, _s in verbs) and not BECAUSE_BREAK.search(between[:why.start()]):
            # "NII rose 5%, thanks to higher rates": b causes a, with the sign of the two directions, or the
            # connector's own ("NII benefits from higher rates")
            own = 1 if BY_UP.match(why.group(0)) else -1 if BY_DOWN.match(why.group(0)) else 0
            hi = a.end + why.start()
            da = self._flip(a) * (self.local_direction(sent, a.start, a.end, 0, hi)
                                  or _noun_direction(" ".join(sent[a.end:hi].split()[:2])))
            db = self._side(sent, b, a.end + why.end(), len(sent), default=0)
            if not (own or da) or (TEMPORAL.match(why.group(0)) and not db):
                return None
            # a report ("NII rose, thanks to higher rates") claims the directions on both sides; a premise or a mood
            # ("NII rose amid talk of higher rates") only the effect's
            ends = [(a, da)] if EXPECTATION.match(why.group(0)) else [(a, da), (b, db)]
            return b, a, (own or da) * (db or 1), bool(db), why.group(0), ends
        if not verbs or why:                             # (a verb after the connector is the cause's own)
            return None
        at, first, sign = verbs[0]
        lead = between[:at]
        if CLAUSE_BREAK.search(lead) and not (RELATIVE_VERB.match(lead) or (
                PARTICIPLE.match(lead) and first.group(0).lower().endswith("ing"))):
            return None                                  # "the BoJ and help stabilise JGBs": the verb is not the BoJ's
        if re.search(r"[,;:]", between[first.end():]):
            return None                                  # "the yen strengthened, equities fell": no object
        if not sign:                                     # "lead to NII pressure": the effect's own word
            sign = self._side(sent, b, a.end + first.end(), len(sent), default=0) * self._flip(b)
            if not sign:
                return None
        helped = HELPS.match(between[at:])
        if helped:                                       # "help moderate rate hikes": the helped verb's sign
            rest = between[at + helped.end():]
            sign = -1 if CAUSAL_DOWN.match(rest) or DOWN.match(rest) else 1
        da = self._side(sent, a, 0, a.end + at, default=0)
        # a report ("a weaker yen lifted Toyota's profit") claims the cause's direction and the verb's for the effect;
        # a mechanism ("a weaker yen lifts ...") claims neither
        ends = [(a, da), (b, sign * self._flip(b))] if (
            PAST.search(first.group(0)) and not MODAL.search(sent[:a.end + at])) else []
        # "BoJ hikes strengthen the yen": USD/JPY falls
        return a, b, sign * (da or 1) * self._flip(b), bool(da), first.group(0), ends

    def _following(self, sent: str, matches: list[Match]) -> tuple | None:
        """A sentence that opens with an event and goes on to what moved after it: "Following the BoJ's rate hike,
        the yen rose 3%". Both directions must be stated; the claim is the sign of the two."""
        lead = FOLLOWING.match(sent)
        if lead is None:
            return None
        comma = sent.find(",", lead.end())
        causes = [m for m in matches if lead.end() <= m.start and m.end <= comma]
        effects = [m for m in matches if 0 <= comma < m.start <= comma + CAUSAL_REACH]
        if not (causes and effects):
            return None
        cause, effect = causes[-1], effects[0]
        dc = self._side(sent, cause, lead.end(), comma, default=0)
        de = self._flip(effect) * self.local_direction(sent, effect.start, effect.end, comma + 1)
        if not (dc and de) or MODAL.search(sent):
            return None
        return cause, effect, dc * de, True, lead.group(1), [(cause, dc), (effect, de)]

    def _claim(self, sent: str, out: list[Found], cause: Match, effect: Match, sign: int, stated: bool, verb: str,
               ends: list[tuple[Match, int]], *, adjacent: bool) -> None:
        """The claims of one causal reading: the moves it reports, and a support, contradiction, or new link."""
        if self._object(sent, cause) or cause.kind == "group":
            return                                       # "the imperative to support the yen raised ...": the aim
        between = sent[min(cause.end, effect.end):max(cause.start, effect.start)]
        denied = bool(NOT.search(between))
        for m, d in ends:
            if d and not denied and m.subentity_id and self._reported(sent, m) \
                    and not any(f.value_of == m.subentity_id for f in out):
                out.append(Found("move", value_of=m.subentity_id, delta=d * UNDIRECTED_SD, mode="standardized",
                                 quote=sent, rule=f"direction in a reported channel ('{verb}')", confidence=0.45,
                                 direction=d))
        if not (cause.subentity_id or effect.subentity_id) and cause.entity_id == effect.entity_id:
            return                                       # one entity named twice ("US EV demand ... US EV subsidies")
        for src, dst in self._resolve(cause, effect, sign if stated and not denied else 0):
            link = self.links.get((src, dst))
            if link is not None:
                polarity = link.polarity        # an uncalibrated link: the sign its mechanism states
                agrees = (polarity == sign) != denied
                out.append(Found("support" if agrees else "contradict", source=src, target=dst,
                                 quote=sent, rule=f"causal '{verb}' on a known link", confidence=0.6))
            elif not denied and cause.via in OUTRIGHT and effect.via in OUTRIGHT and adjacent:
                # a new link only from two values named outright, next to each other, joined by the verb
                out.append(Found("link", source=src, target=dst, label=verb.lower(), effect=sign * LINK_EFFECT,
                                 quote=sent, rule=f"causal '{verb}', no link yet", confidence=0.4))

    def _resolve(self, cause: Match, effect: Match, sign: int) -> list[tuple[str, str]]:
        """The value pairs a causal claim is about: one pair, or one per member of a sector it names as the effect
        ("Japanese insurers"). An entity named for its values stands for the one value a link joins to the other
        side, or, with a stated `sign`, for the one value whose link has that sign ("a weaker yen lifts Toyota"); a
        link of unknown size has no sign. Where a value and a part of it both qualify, the entity stands for the total;
        where a causal link and an identity or accounting term both qualify, for the causal link."""
        effects = self._members[effect.entity_id] if effect.kind == "group" else [effect]
        out = []
        for e in effects:
            pairs = self._pairs(cause, e)
            if len(pairs) > 1 and sign:
                pairs = [p for p in pairs if (m := self.links[p].effect_mean) and (m > 0) == (sign > 0)]
            if len(pairs) > 1 and e.kind != "value":
                # a claim about the company as a whole is on its total, not on a part that adds into it (R11)
                pairs = [p for p in pairs if not any(q[1] in self._totals_of(p[1]) for q in pairs if q != p)]
            if len(pairs) > 1 and any(not self.links[p].fixed for p in pairs):
                # a causal sentence is about a causal link, not an identity or accounting term beside it
                pairs = [p for p in pairs if not self.links[p].fixed]
            if len(pairs) == 1 and pairs[0][0] != pairs[0][1]:       # not ambiguous, nor one value named twice
                out.append(pairs[0])
        return out

    def _totals_of(self, value: str) -> set[str]:
        """Every value `value` adds into, through accounting, identity and stock-flow links, at any depth."""
        seen: set[str] = set()
        todo = [value]
        while todo:
            for t in self._into.get(todo.pop(), ()):
                if t not in seen:
                    seen.add(t)
                    todo.append(t)
        return seen

    def _bare_yields(self, sent: str, matches: list[Match], region: str | None) -> list[Match]:
        """"Yields" named without their market ("higher yields lift Japanese insurers"): the bond market of the region
        in view (a sector's the sentence names, else the regions of the names in it, else the document's), standing,
        like any market named in a channel, for the one yield a link joins to the other side."""
        regions = [self.gz.region.get(self._members[m.entity_id][0].entity_id) if m.kind == "group"
                   else self.gz.region.get(m.entity_id) for m in matches]
        view = {r for r in regions if r} or {region} - {None}
        market = [e for e in self.bond_markets if self.gz.region.get(e) in view]
        if len(market) != 1:
            return []
        return [Match("entity", market[0], None, y.start(), y.end(), y.group(0), "region")
                for y in BARE_YIELDS.finditer(sent) if not any(m.start < y.end() and y.start() < m.end for m in matches)
                and BARE_BEFORE.search(sent[:y.start()])]

    def _groups(self, sent: str) -> list[Match]:
        """Sectors the sentence names with their region ("Japanese insurers", "US banks' NII"): the model's companies
        of that sector and region, each standing for the value the words after a possessive name, if any."""
        out = []
        for g in GROUP.finditer(sent):
            region = next(r for r, p in GROUP_REGIONS.items() if p.fullmatch(g.group("region")))
            sector = next(x for x, p in GROUP_SECTORS.items() if p.fullmatch(g.group("sector")))
            members = sorted(e for e in self.gz.companies if self.gz.region.get(e) == region
                             and self.graph.entities[e].sector == sector)
            if not members:
                continue
            gid = f"group:{sector}:{region}:{g.start()}"
            owned = []
            for e in members:
                named = self.gz.find(sent[g.end():g.end() + CAUSAL_REACH], [e], subject=e) \
                    if re.match(r"['’]s?\s", sent[g.end():]) else []
                v = next((m for m in named if m.subentity_id and m.entity_id == e and m.start <= 3), None)
                owned.append(Match("value" if v else "entity", e, v.subentity_id if v else None, g.start(),
                                   g.end() + (v.end if v else 0), g.group(0), "name"))
            self._members[gid] = owned
            out.append(Match("group", gid, None, g.start(), max(x.end for x in owned), g.group(0), "name"))
        return out

    def _pairs(self, a: Match, b: Match) -> list[tuple[str, str]]:
        """The value pairs two mentions can stand for: their own values, or (for an entity) the values of it that
        a link joins to the other side."""
        srcs = [a.subentity_id] if a.subentity_id else self.graph.entities[a.entity_id].subentity_ids
        dsts = [b.subentity_id] if b.subentity_id else self.graph.entities[b.entity_id].subentity_ids
        if a.subentity_id and b.subentity_id:
            return [(a.subentity_id, b.subentity_id)]
        return sorted({(s, d) for s in srcs for d in dsts if (s, d) in self.links})


def _header_rows(lines: list[list[str]], width: int) -> list[list[str]]:
    """A table's header rows from the lines over it: a header cell written on two lines splits its row in two
    ("... | Avg." and "Loan Balances, mm | ..."), so lines are joined, from the bottom up, while the row stays
    within the table's width (its rows' count of cells); the last rows (at most GROUP_ROWS)."""
    rows: list[list[str]] = []
    for line in reversed(lines):
        if rows and len(rows[0]) < width and len(rows[0]) + len(line) - 1 <= width:
            rows[0] = [*line[:-1], f"{line[-1]} {rows[0][0]}".strip(), *rows[0][1:]]
        else:
            rows.insert(0, line)
    return rows[-GROUP_ROWS:]


def _told(sent: str, reading: Reading) -> bool:
    """Whether a sentence tells of no present news, updating what the reading carries: a bullet under a scenario's
    heading ("Upside Scenario" ... "• GDP growth stronger than expected"), until prose resumes; or an episode dated by
    day and month only ("as the yen rose 10% between 30 July and 5 August") right after a sentence about an earlier
    year ("The July-August 2024 shock ...")."""
    years = {int(y) for y in YEAR.findall(re.sub(r"\bsince\s+\S+", " ", sent))}
    episode = not years and reading.past and bool(DAY_MONTH.search(sent))
    reading.past = bool(reading.date and years and max(years) < reading.date.year) or episode
    if SCENARIO.match(sent):
        reading.scenario = True
    elif not BULLET.match(sent) and len(re.findall(r"[A-Za-z]{2,}", sent)) >= PROSE_WORDS:
        reading.scenario = False
    return episode or reading.scenario


def _aim(lead: str) -> bool:
    """Whether the words before a mention make it the object of an aim ("buybacks to improve shareholder returns"),
    not of the value's own move ("voted to raise the rate", "the BoJ to hike")."""
    a = AIM_OF.search(lead)
    return bool(a) and a.group(1).lower() not in LICENSED and not a.group(1)[0].isupper()


def _part(sent: str, start: int, end: int) -> str:
    """What frames a mention at start:end: its part of the sentence (between semicolons and sub-bullets) up to the
    mention, and the few words right after it ("Core CPI is projected to", "25bp hike incoming")."""
    lo = max((x.end() for x in PART_BREAK.finditer(sent, 0, start)), default=0)
    hi = next((x.start() for x in PART_BREAK.finditer(sent, end)), len(sent))
    return sent[lo:end] + " " + " ".join(sent[end:hi].split()[:FRAME_WORDS])


def _modelled(cells: list[str], k: int) -> int:
    """The first of a spreadsheet row's cells (after its label, cell `k`) that a model computed: a figure with
    decimals after at least MODEL_AFTER whole ones ("25511 | 24164.86732"), where reported figures end and a
    projection begins; the row's length when there is none (a ratio's row has decimals throughout)."""
    whole = 0
    for j in range(k + 1, len(cells)):
        if FIGURE_CELL.fullmatch(cells[j]):
            if "." not in cells[j]:
                whole += 1
            elif whole >= MODEL_AFTER:
                return j
    return len(cells)


def _dates_in(sent: str) -> list[datetime]:
    """The dates a sentence names ("31-Jul-2026", "Sep. 18, 2026", "9 Jan 24")."""
    out = [d for pat in DATE_PATTERNS for m in pat.finditer(sent)
           if (d := _date(m.group("y"), m.groupdict().get("m"), m.group("d"), m.groupdict().get("mon")))]
    out += [d for m in SHORT_DATE.finditer(sent) if (d := _date(f"20{m.group('y')}", None, m.group("d"), m.group("mon")))]
    return out


def _noun_direction(text: str) -> int:
    """The direction a noun gives a value in a causal claim ("yen weakness", "NII pressure"), or 0."""
    up, down = SIDE_UP.search(text), SIDE_DOWN.search(text)
    return 0 if bool(up) == bool(down) else 1 if up else -1


def _blank(at: int) -> Num:
    return Num(0.0, "", "", 1.0, at, at, False, blank=True)


def _licensed(text: str) -> str:
    """The text without the infinitives that are not the value's own (see LICENSED)."""
    def keep(m: re.Match) -> str:
        word = m.group(1)
        own = word is None or word in LICENSED or word[0].isupper() or word.endswith(")")
        return m.group(0) if own else word + m.group(2)
    return INFINITIVE.sub(keep, text)


def _labelled_parens(sent: str, lo: int, at: int) -> bool:
    """Whether the number at `at` sits in a parenthetical that names something of its own: "(OVX +56%)"."""
    seg = sent[lo:at]
    k = seg.rfind("(")
    return k > seg.rfind(")") and bool(re.search(r"\b[A-Z][A-Za-z]+", seg[k:]))


def _heading(sent: str) -> bool:
    words = re.findall(r"[A-Za-z][A-Za-z'’-]*", sent)
    return len(words) >= 3 and sum(w[0].isupper() for w in words) >= HEADING_SHARE * len(words)


def _inside_parens(sent: str, lo: int, at: int) -> bool:
    seg = sent[lo:at]
    return seg.count("(") > seg.count(")")


# -- a document into items --------------------------------------------------------------------------------------------
CATEGORY = {"policy_rate": "rates", "bond_yield": "rates", "interest_rate": "rates", "real_rate": "rates",
            "fx_rate": "fx", "inflation_rate": "macro", "growth_rate": "macro", "commodity_price": "commodities",
            "asset_price": "markets", "revenue_flow": "earnings", "volatility": "markets", "capital_flow": "flows",
            "margin": "earnings", "production_flow": "markets", "spending_flow": "macro", "loss_flow": "credit",
            "share": "earnings", "stress_index": "credit"}


@dataclass
class ChunkClaims:
    ord: int
    text: str
    found: list[Found] = field(default_factory=list)
    entities: list[str] = field(default_factory=list)
    mentions: list[Match] = field(default_factory=list)
    sentence_spans: list[tuple[int, int]] = field(default_factory=list)


def claims_of_chunk(rules: Rules, ord_: int, text: str, reading: Reading | None,
                    page: int | None = None) -> tuple[ChunkClaims, Reading]:
    out = ChunkClaims(ord_, text)
    reading = reading or Reading()
    if page != reading.page:
        reading.page, reading.header, reading.columns, reading.after_data = page, None, [], True
        reading.scenario = False
    for a, b in sentences(text):
        sent = text[a:b]
        ctx = [e for e, age in reading.recent if age < CONTEXT_SENTENCES]
        ms = rules.gz.find(sent, ctx, subject=reading.subject, region=reading.region)
        out.sentence_spans.append((a, b))
        for m in ms:
            out.mentions.append(Match(m.kind, m.entity_id, m.subentity_id, a + m.start, a + m.end, m.surface))
            if m.entity_id not in out.entities:
                out.entities.append(m.entity_id)
        named = [m.entity_id for m in ms]
        reading.recent = [(e, age + 1) for e, age in reading.recent if e not in named and age + 1 < CONTEXT_SENTENCES] \
            + [(e, 0) for e in dict.fromkeys(named)]
        if BOILERPLATE.search(sent):
            continue                                 # named for search, but a disclaimer claims nothing
        rowed = rules.entity_row(sent, ms, reading)
        header = header_of(sent)
        if header is not None:
            marks = all(p.kind in ("prev", "cur") for p in header.periods)
            reading.header = (revise(reading.header, header) if marks else None) or header
            continue
        told = _told(sent, reading)                  # a scenario's bullet or an earlier episode: no news of now
        nums = numbers(sent, rules.yen)
        # "NTT's share price lagged. However, its share price rebounded": "its" is the stranger's, not the subject's
        stranger, reading.stranger = reading.stranger, any(
            t.lower() not in rules.gz.surface_words for t in POSSESSOR.findall(sent))
        vals = [m for m in ms if m.subentity_id and not (
            stranger and m.via in ("context", "subject") and POSSESSED.search(sent[:m.start]))]
        causal = rules.causal_claims(sent, ms, region=reading.region)
        linked = {x for f in causal if f.type != "move" for x in (f.source, f.target)}
        claimed: set[str] = set()                    # one claim per value per sentence
        for f in rowed + rules.priced_claims(sent, ms):
            out.found.append(f)
            claimed.add(f.value_of)
        for k, m in enumerate(vals):
            if m.subentity_id in claimed or reading.forward:
                continue
            row = rules.row_claims(sent, m, nums, reading)
            if row is None and (tabular(sent) and sum(not _inside_parens(sent, m.end, n.start) for n in nums
                                                      if n.start >= m.end) >= 2 or FIGURE_RUN.search(sent)):
                row = []                                     # a table's row is read as a row, or not at all
            elif row is None:
                # the clause runs from the last mention of another value to the next ("crude oil prices": one value,
                # one clause)
                prev_end = max((v.end for v in vals[:k] if v.subentity_id != m.subentity_id), default=0)
                nxt = next((v.start for v in vals[k + 1:] if v.subentity_id != m.subentity_id), len(sent))
                row = [] if told else rules.value_claims(
                    sent, m, nums, prev_end, nxt, reading.date, ref=reading.when, partial=reading.partial, linked=m.subentity_id in linked,
                    others=any(x.entity_id != m.entity_id for x in ms))
            for f in row:
                out.found.append(f)
                claimed.add(m.subentity_id)
        for f in causal:
            if f.type == "move" and (f.value_of in claimed or told):
                continue                                 # the value's own words already say how it moved
            if not any(g.type == f.type and g.source == f.source and g.target == f.target and g.quote == f.quote
                       and g.value_of == f.value_of for g in out.found):
                out.found.append(f)
    return out, reading


def keep_best(chunk_claims: list[ChunkClaims]) -> None:
    """One level and one move per value, and one claim per pair of linked values, in a whole document (in place):
    the more confident, then the first. A report repeats its point in the summary, the body, and the charts;
    importing every repetition would count one piece of news several times."""
    best: dict[tuple, tuple[float, int, int]] = {}
    for ci, cl in enumerate(chunk_claims):
        for fi, f in enumerate(cl.found):
            key = ("value", f.value_of, f.type) if f.type in ("observe", "move") else ("link", f.source, f.target)
            if key not in best or f.confidence > best[key][0]:
                best[key] = (f.confidence, ci, fi)
    keep = {(ci, fi) for _rank, ci, fi in best.values()}
    for ci, cl in enumerate(chunk_claims):
        cl.found = [f for fi, f in enumerate(cl.found) if (ci, fi) in keep]


def category_of(graph: WorldView, found: list[Found]) -> str:
    for f in found:
        sid = f.value_of or f.target
        if sid in graph.values:
            return CATEGORY.get(graph.values[sid].attribute_kind, "other")
    return "other"


def stance_of(found: list[Found]) -> str:
    ups = sum(1 for f in found if f.direction > 0)
    downs = sum(1 for f in found if f.direction < 0)
    return "up" if ups > downs else "down" if downs > ups else ("mixed" if ups else "")


TICKER = re.compile(r"^(?:\d{3,6} [A-Z]{2}|[A-Z]{1,5})$")


def item_of(graph: WorldView, claims: ChunkClaims, *, doc_prefix: str, published_at: datetime, source: str,
            source_type: str, kind: str, title: str, extra: list[dict] | None = None) -> dict[str, Any] | None:
    """One import item for a chunk: its rule signals, then any the LLM step added (`extra`); None when it has none."""
    extra = list(extra or [])
    if not claims.found and not extra:
        return None
    first = claims.text[claims.sentence_spans[0][0]:claims.sentence_spans[0][1]] if claims.sentence_spans else claims.text
    headline = first if len(first) <= 200 else first[:197].rstrip() + "…"
    tickers = sorted({a for e in claims.entities if graph.entities[e].kind == "company"
                      for a in graph.entities[e].aliases if TICKER.match(a) and len(a) > 1})
    conf = sum(f.confidence for f in claims.found) / len(claims.found) if claims.found else LLM_CONFIDENCE
    first_id = next((x for x in (extra[0].get("value_of"), extra[0].get("target")) if x), None) if extra else None
    category = category_of(graph, claims.found) if claims.found else CATEGORY.get(
        graph.values[first_id].attribute_kind, "other") if first_id in graph.values else "other"
    return {
        "id": f"{doc_prefix}-{claims.ord:04d}", "published_at": published_at.isoformat(), "source": source or title,
        "source_type": source_type, "kind": kind, "headline": headline, "summary": claims.text,
        "entities": sorted(claims.entities), "tickers": tickers, "category": category,
        "stance": stance_of(claims.found), "relevance": round(min(0.9, 0.4 + 0.1 * (len(claims.found) + len(extra))), 2),
        "confidence": round(conf, 3), "tags": ["extracted", *(["llm"] if extra else [])],
        "signals": [f.signal() for f in claims.found] + extra,
    }


# -- provenance (Oct 25): what the world model's standards gate reads beside an item's signals ------------------------
THIRD_PARTY = ("broker_research", "expert_call", "news", "other")      # R21: not the company's own, not a regulator's


def signal_plausible(rules: Rules, sig: dict) -> bool | None:
    """Whether a signal's number is inside the band the extractor accepts: a level inside the value's band (6 sd + 4 scale,
    or six standard units on a log scale), a sized move inside the size it takes (a relative move up to 90%, an absolute one
    up to MAX_POINTS). None when there is no number to check (a link, a support, a bare direction)."""
    if sig["type"] == "observe":
        return rules.plausible_level(sig["value_of"], sig["value"])
    if sig["type"] == "move" and sig["mode"] != "standardized":
        return 0 < abs(sig["delta"]) <= (0.9 if sig["mode"] == "relative" else MAX_POINTS)
    return None


def plausible_of(rules: Rules, signals: list[dict]) -> bool | None:
    """True only when every signal was checked and is inside its band; False when one is outside; else None."""
    checks = [signal_plausible(rules, s) for s in signals]
    return None if any(c is None for c in checks) else all(checks)


def basis_of(rules: Rules, signals: list[dict], source_type: str, subject: str | None) -> str | None:
    """R21, conservatively. An issuer's own filing about itself (every value is the document's subject's) is `direct`.
    Third-party material is `proxy` when every signal is the quantity itself (a level, or a sized change of it) and
    `context_only` when none is (a link, a support, a bare direction); a mix, or anything else, is None (a person decides)."""
    if source_type == "filing":
        own = all(s["type"] in ("observe", "move") and rules.graph.values[s["value_of"]].entity_id == subject
                  for s in signals)
        return "direct" if own else None
    if source_type not in THIRD_PARTY:
        return None
    quantity = [s["type"] == "observe" or (s["type"] == "move" and s["mode"] != "standardized") for s in signals]
    return "proxy" if all(quantity) else "context_only" if not any(quantity) else None


def coverage_of(rules: Rules, signals: list[dict], partial: bool) -> str | None:
    """R18: `partial` when a value is a part of a total the model also holds (a segment, a region, through an accounting or
    identity link), or a year's flow read from a document that reports a month, a quarter or a half; else `full`. None when
    no signal is about a value (a link has no coverage)."""
    values = [s["value_of"] for s in signals if s["type"] in ("observe", "move")]
    if not values:
        return None
    part = any(rules._totals_of(v) or (partial and rules.graph.values[v].unit.endswith("/yr")) for v in values)
    return "partial" if part else "full"


def citation_of(doc_id: str, chunk: Any, signals: list[dict]) -> str:
    """Where a link was read: the document, the page, and the character span (in the document's text) of the sentence
    that makes the first link or support; the chunk's number when the sentence is not found in it. Empty when the item
    states no link."""
    sig = next((s for s in signals if s["type"] in ("link", "support", "contradict")), None)
    if sig is None:
        return ""
    at = chunk.text.find(sig["quote"]) if sig["quote"] else -1
    page = f" p.{chunk.page}" if chunk.page is not None else ""
    if at < 0:
        return f"{doc_id}{page} chunk {chunk.ord}"
    return f"{doc_id}{page} chars {chunk.start + at}-{chunk.start + at + len(sig['quote'])}"


def provenance_of(rules: Rules, item: dict, *, doc_id: str, chunk: Any, subject: str | None, partial: bool,
                  publisher: str, url: str | None) -> dict[str, Any]:
    """The attribution fields of one item (see contract.md): the document, who published it, how the calibration register
    would match it, the citation of a link, the coverage, and the plausibility of its numbers."""
    sigs = item["signals"]
    return {"document": doc_id, "publisher": publisher, "url": url or None,
            "basis": basis_of(rules, sigs, item["source_type"], subject), "citation": citation_of(doc_id, chunk, sigs),
            "coverage": coverage_of(rules, sigs, partial), "plausible": plausible_of(rules, sigs)}
