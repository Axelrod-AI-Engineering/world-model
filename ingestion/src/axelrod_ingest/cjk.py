"""Chinese, Japanese, and Korean text (Oct 22): how it is normalized, measured, split into sentences, and cut.

Standard library only, and no dictionary: every rule here looks at characters and punctuation, so the same text always
gives the same result.

- **Width.** Full-width digits, letters, and punctuation (１２３，％，（）) become their ASCII forms, as NFKC does, but only
  within the full-width block and the currency signs (￥ ￡ ￦ ￠). NFKC applied to everything would also turn "m²" into
  "m2", "…" into "...", and a circled digit into a plain one. The full-width "！" and "？" stay, because they end
  sentences that have no space after them. A PDF that draws a Chinese name with a space between every character
  ("比 亞 迪 股 份") is rejoined.
- **Length.** A chunk's size is a weight, not a count of characters: an ideograph, a kana, or a Hangul syllable weighs two,
  because it carries about as much as two letters of English. Seven hundred units is then about 350 Chinese characters.
- **Sentences.** "。", "！", "？" (and their half-width forms before an ideograph) end a sentence with no space after
  them. A Korean sentence ends in a period, question mark, or exclamation mark before a space and a Hangul syllable, or in
  one of the endings 다, 요, 죠, 까 at the end of a line (a bullet or a heading line often has no period).
- **Cuts.** A piece never ends inside a word or a character: not between two letters or digits of one word or number,
  not before a combining mark, a variation selector, a joiner, or a Hangul jamo that completes a syllable. Korean words
  are cut at spaces. Chinese has none, so a piece is cut after the last clause mark (，、；：) that fits, else at the limit.
"""

from __future__ import annotations

import re
import unicodedata

HAN = "㐀-䶿一-鿿豈-﫿\U00020000-\U0002a6df"
KANA = "぀-ヿ"
HANGUL = "가-힯ᄀ-ᇿ㄰-㆏"
CJK_CHAR = re.compile(f"[{HAN}{KANA}{HANGUL}]")
CJK_WEIGHT = 2                                # what one ideograph, kana, or syllable weighs against a Latin letter
FULL_KEPT = {0xFF01, 0xFF1F}                  # ！ ？ stay full-width: they end a sentence without a space
FULL_WIDTH = {cp: chr(cp - 0xFEE0) for cp in range(0xFF01, 0xFF5F) if cp not in FULL_KEPT}
FULL_WIDTH.update({0x3000: " ", 0xFFE0: "¢", 0xFFE1: "£", 0xFFE5: "¥", 0xFFE6: "₩"})
SPACED_HAN = re.compile(f"(?<![{HAN}])(?:[{HAN}] ){{2,}}[{HAN}](?![{HAN}])")
SENTENCE_END = re.compile(r"[。！？‼⁇⁈⁉]+[」』”’）)\]]*|[!?]+(?=[" + HAN + KANA + HANGUL + r"])")
KOREAN_END = re.compile(r"(?<=[다요죠까])[.!?]*[\"'”’)\]]*(?=\n)")
CLAUSE_MARKS = "，、；：,;:)）」』”"
JOINERS = {"‍", "‌", "⁠"}      # zero-width joiners: a cut before one splits a character


def width(text: str) -> str:
    """Full-width forms to their ASCII forms (NFKC within the full-width block and the currency signs only), and a
    Chinese run drawn with a space between every character rejoined."""
    text = text.translate(FULL_WIDTH)
    return SPACED_HAN.sub(lambda m: m.group(0).replace(" ", ""), text)


def weight(text: str) -> int:
    """A text's length in units: a Latin character is one, an ideograph, kana, or Hangul syllable two."""
    return len(text) + (CJK_WEIGHT - 1) * sum(1 for _ in CJK_CHAR.finditer(text))


def limit(text: str, a: int, b: int, units: int) -> int:
    """The largest end e in [a, b] such that text[a:e] weighs at most `units` (at least a + 1: a piece is never empty)."""
    used = 0
    for k in range(a, b):
        used += CJK_WEIGHT if CJK_CHAR.match(text[k]) else 1
        if used > units:
            return max(k, a + 1)
    return b


def _ascii_word(ch: str) -> bool:
    return ch.isascii() and ch.isalnum()


def joined(text: str, cut: int) -> bool:
    """Whether cutting `text` just before index `cut` would split a word, a number, or a character."""
    left, right = text[cut - 1], text[cut]
    return (unicodedata.combining(right) > 0 or right in JOINERS or left in JOINERS or "︀" <= right <= "️"
            or "ᅠ" <= right <= "ᇿ"                              # a vowel or final jamo completes a syllable
            or (_ascii_word(left) and _ascii_word(right))                 # AEV, 123456
            or (left in ",." and right.isdigit() and cut >= 2 and text[cut - 2].isdigit())      # 1,|234
            or (left.isdigit() and right in ",." and text[cut + 1:cut + 2].isdigit())           # 1|,234
            or (left in "'’" and right.isalpha() and cut >= 2 and text[cut - 2].isalpha())      # don'|t
            or (re.match(f"[{HANGUL}]", left) is not None and re.match(f"[{HANGUL}]", right) is not None))  # one word


def cut_at(text: str, a: int, e: int) -> int:
    """Where to cut the piece of `text` that starts at `a` and may end at most at `e`: after the last line break, else
    the last space, else the last clause mark that fits, else at `e` backed off to a point that splits no word, number, or
    character (at `e` itself when the whole window is one unbroken word). The result is an offset from `a`."""
    window = text[a:e + 1]
    cut = window.rfind("\n")
    if cut <= 0:
        cut = window.rfind(" ")
    if cut <= 0:
        cut = max((window.rfind(c) + 1 for c in CLAUSE_MARKS if window.rfind(c) > 0), default=0)
    if cut <= 0:
        k = e - a
        while k > 1 and joined(text, a + k):
            k -= 1
        cut = e - a if joined(text, a + k) else k
    return cut


def sentence_cuts(text: str) -> set[int]:
    """Offsets where a CJK sentence ends: after 。！？ and their closing quotes, and after a Korean ending at a line's end."""
    return {m.end() for pat in (SENTENCE_END, KOREAN_END) for m in pat.finditer(text)}
