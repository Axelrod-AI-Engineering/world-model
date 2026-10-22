"""Currencies, scales, and the yen (Oct 22): what a figure's words and signs say about its unit, in English, Chinese, and Korean.

**Currencies.** A figure's currency is the code or sign before it ("RMB 344,815", "HK$43bn", "₩1.2tn", "US$5m") or the
word after its scale ("亿元", "百万元", "억원", "美元", "円"). One name per currency: "$" (USD), "¥" (JPY, the
legacy name), "€", "£", "CNY", "KRW", "HKD". `元`, `圆`, `人民币` are CNY, `원` is KRW, `円` and `日元` are JPY.

**Scales.** English words (k, m, bn, tn, million, billion, trillion) and the CJK ones: 十 (10), 百 (100), 千 (1e3), 万 (1e4),
亿 (1e8) in Chinese, with their traditional forms; 십, 백, 천, 만, 억, 조 (1e12) in Korean. A scale is one or more of them
multiplied: 百万 is a million, 十亿 a billion, 万亿 a trillion, 千万 ten million, 백만 a million. A Korean amount may
add smaller scales ("3억 5천만" is 350 million, "1조 2,345억" is 1.2345 trillion). 兆 is left out: it is a trillion in
Taiwan and a million in "兆瓦" (megawatt) and "兆字节" (megabyte). Korean 조 is a trillion unless it is an article of
a law ("제3조") or the start of a word that is not an amount (조치, 조정, 조사).

**The yen sign.** A bare ¥ is the Japanese yen, unless the document says otherwise: the same sign is the Chinese yuan in a
Chinese filing. `resolve_yen` reads the document, never the number: its own currency words first (RMB, 元, 人民币 against
JPY, 円, 日元: when only one side appears, or one side has three times the other's), then whether the issuer is a PRC
company, then the language of the text, and by default the yen. It returns the evidence with the answer, and the pipeline stores both in the document's metadata.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# -- currencies -------------------------------------------------------------------------------------------------
CODES = {"usd": "$", "us$": "$", "jpy": "¥", "jp¥": "¥", "yen": "¥", "eur": "€", "gbp": "£", "cny": "CNY", "rmb": "CNY",
         "cn¥": "CNY", "krw": "KRW", "₩": "KRW", "hkd": "HKD", "hk$": "HKD", "人民币": "CNY", "人民幣": "CNY"}
CURRENCY_SUFFIX = {"元": "CNY", "圆": "CNY", "圓": "CNY", "人民币": "CNY", "人民幣": "CNY", "美元": "$", "港元": "HKD",
                   "港币": "HKD", "港幣": "HKD", "日元": "¥", "円": "¥", "欧元": "€", "歐元": "€", "英镑": "£", "英鎊": "£",
                   "韩元": "KRW", "韓元": "KRW", "원": "KRW", "엔": "¥", "달러": "$", "유로": "€"}
CURRENCY = {"$": ("$", "usd", "dollar"), "¥": ("¥", "jpy", "yen"), "€": ("€", "eur", "euro"), "£": ("£", "gbp"),
            "CNY": ("cny", "rmb", "yuan", "人民币"), "KRW": ("krw", "₩", "won", "원"), "HKD": ("hkd", "hk$")}
CURRENCY_PREFIX = r"US\$|HK\$|CN¥|JP¥|[$¥€£₩]|人民[币幣]|(?<![/\w])(?:USD|JPY|EUR|GBP|CNY|RMB|KRW|HKD)(?=\s?\d)"
CURRENCY_WORD = "|".join(sorted(CURRENCY_SUFFIX, key=lambda w: (-len(w), w)))
CODE_AFTER = r"(?:USD|JPY|EUR|GBP|CNY|RMB|KRW|HKD)"

# -- scales -----------------------------------------------------------------------------------------------------
SCALE = {"k": 1e3, "m": 1e6, "mn": 1e6, "mm": 1e6, "million": 1e6, "b": 1e9, "bn": 1e9, "billion": 1e9, "tn": 1e12,
         "tr": 1e12, "trillion": 1e12}
CJK_SCALE = {"十": 1e1, "百": 1e2, "千": 1e3, "万": 1e4, "萬": 1e4, "亿": 1e8, "億": 1e8,
             "십": 1e1, "백": 1e2, "천": 1e3, "만": 1e4, "억": 1e8, "조": 1e12}
# one scale: a run of the characters above, a Korean 조 only where it is no article or word start (see the docstring)
CJK_SCALE_RUN = r"(?:[十百千万萬亿億십백천만억]|조(?![치정건항사직합달성]))+"
CJK_TAIL = rf"(?:\s?\d[\d,]*(?:\.\d+)?\s?{CJK_SCALE_RUN})*"
ARTICLE = re.compile(r"제\s?$")                 # 제3조: article 3 of a law, no trillion


def scale_value(run: str) -> float:
    """The product of the scale characters in a run: 百万 is 1e6, 万亿 1e12, 천만 1e7."""
    out = 1.0
    for ch in run:
        out *= CJK_SCALE[ch]
    return out


def tail_value(tail: str) -> float:
    """The amount a Korean or Chinese number adds after its first scale ("3억 5천만": the 5천만, 5e7)."""
    return sum(float(m.group(1).replace(",", "")) * scale_value(m.group(2)) for m in TAIL_PART.finditer(tail))


TAIL_PART = re.compile(rf"(\d[\d,]*(?:\.\d+)?)\s?({CJK_SCALE_RUN})")

# a table label's unit: "(RMB'000)", "(KRW million)", "(HK$ million)", "Unit: RMB million", "单位：人民币百万元", "(단위: 백만원)"
SCALE_HINT = re.compile(r"(?:\(|,\s|\b)(?:[$¥€£₩]|HK\$|USD|JPY|EUR|CNY|RMB|KRW|HKD)?\s?(?P<s>bn|billions?|mn|mm|m|millions?|MM|"
                        r"000s|'000|k|tn|tr)\b\)?", re.I)
CJK_LABEL_SCALE = re.compile(rf"({CJK_SCALE_RUN})\s?(?:{CURRENCY_WORD})")


def scale_hint(label: str) -> float | None:
    """The scale a row's label states ("(RMB'000)" is a thousand, "百万元" a million, "(단위: 억원)" a hundred million), or None."""
    m = SCALE_HINT.search(label)
    if m:
        word = m.group("s").lower().rstrip("s")
        return 1e3 if word in ("000", "'000", "k") else SCALE.get(word, SCALE.get(word[:2], 1e6))
    c = CJK_LABEL_SCALE.search(label)
    return scale_value(c.group(1)) if c else None


# -- language and the yen -----------------------------------------------------------------------------------------
HAN_CHAR = re.compile("[㐀-䶿一-鿿豈-﫿]")
KANA_CHAR = re.compile("[぀-ヿ]")
HANGUL_CHAR = re.compile("[가-힯]")
LANGUAGE_SAMPLE = 20000
CNY_WORDS = re.compile(r"(?<![A-Za-z])(?:RMB|CNY|renminbi|yuan)\b|人民[币幣]|[\d万萬亿億百千]\s?元", re.I)
JPY_WORDS = re.compile(r"(?<![A-Za-z])JPY\b|\bJapanese yen\b|円|日元|日圓", re.I)
PRC_ISSUER = re.compile(r"People[’']s Republic of China|\bPRC\b|中华人民共和国|中華人民共和國|深圳证券交易所|上海证券交易所|"
                        r"Shenzhen Stock Exchange|Shanghai Stock Exchange|A-share", re.I)
ISSUER_SAMPLE = 5000                            # a filing names its issuer and its country in the opening text
CJK_SHARE = {"ja": 0.05, "ko": 0.20, "zh": 0.20}
DOMINANT = 3                                    # one currency's words this many times the other's settle a mixed text


def language_of(text: str) -> str:
    """"ja", "ko", "zh", or "en" (anything else, mostly Latin text): by the share of kana, Hangul, and ideographs among the
    letters of the opening text. A bilingual report with an English body (a fifth of it Chinese at most) is "en"."""
    head = text[:LANGUAGE_SAMPLE]
    letters = sum(c.isalpha() for c in head) or 1
    kana, hangul, han = (len(p.findall(head)) for p in (KANA_CHAR, HANGUL_CHAR, HAN_CHAR))
    if kana / letters >= CJK_SHARE["ja"]:
        return "ja"
    if hangul / letters >= CJK_SHARE["ko"]:
        return "ko"
    return "zh" if han / letters >= CJK_SHARE["zh"] else "en"


def issuer_country(text: str) -> str | None:
    """"CN" when the opening text says the issuer is a PRC company (a PRC incorporation, a Shenzhen or Shanghai listing),
    else None."""
    return "CN" if PRC_ISSUER.search(text[:ISSUER_SAMPLE]) else None


@dataclass(frozen=True)
class Yen:
    """How a bare ¥ in a document is read, and why."""

    code: str                                    # "JPY" or "CNY"
    basis: str                                   # explicit | issuer | language | default
    evidence: dict = field(default_factory=dict)

    @property
    def currency(self) -> str:
        """The name a figure's currency takes: "¥" for the yen (as ever), "CNY" for the yuan."""
        return "CNY" if self.code == "CNY" else "¥"

    def meta(self) -> dict:
        return {"code": self.code, "basis": self.basis, **self.evidence}


def resolve_yen(text: str, *, language: str | None = None, issuer: str | None = None) -> Yen:
    """What a bare ¥ means here, deterministically (see the module docstring for the order). `language` and `issuer` (a
    country code) override what the text shows, as a caller who knows them would."""
    language = language or language_of(text)
    issuer = issuer or issuer_country(text)
    cny, jpy = len(CNY_WORDS.findall(text)), len(JPY_WORDS.findall(text))
    evidence = {"signs": text.count("¥"), "cny_words": cny, "jpy_words": jpy, "language": language,
                "issuer_country": issuer or ""}
    if cny and not jpy:
        return Yen("CNY", "explicit", evidence)
    if jpy and not cny:
        return Yen("JPY", "explicit", evidence)
    if cny and jpy and cny >= DOMINANT * jpy:
        return Yen("CNY", "dominant", evidence)
    if cny and jpy and jpy >= DOMINANT * cny:
        return Yen("JPY", "dominant", evidence)
    if issuer == "CN":
        return Yen("CNY", "issuer", evidence)
    if language == "zh":
        return Yen("CNY", "language", evidence)
    return Yen("JPY", "language" if language == "ja" else "default", evidence)
