"""Sentences and chunks: exact spans, abbreviations and numbers kept whole, chunks inside one paragraph of one page."""

from __future__ import annotations

import pytest

from axelrod_wm.ingest.chunk import CHUNK_CHARS, _is_abbrev, chunk, sentences
from axelrod_wm.ingest.parse import Parsed, Segment


def split(text: str) -> list[str]:
    spans = sentences(text)
    for a, b in spans:
        assert text[a:b] == text[a:b].strip() and text[a:b]
    return [text[a:b] for a, b in spans]


@pytest.mark.parametrize("text,want", [
    ("The U.S. economy grew. Apple Inc. said so.", ["The U.S. economy grew.", "Apple Inc. said so."]),
    ("See e.g. Fig. 3 here. Next one.", ["See e.g. Fig. 3 here.", "Next one."]),
    ("Mr. Ueda spoke vs. Dr. Lagarde. Then No. 2 rose.", ["Mr. Ueda spoke vs. Dr. Lagarde.", "Then No. 2 rose."]),
    ("J. Smith said rates hit 1.25%. Next.", ["J. Smith said rates hit 1.25%.", "Next."]),
    ("Rates were 1.25% and 3.875% today. Yields 4.85.", ["Rates were 1.25% and 3.875% today.", "Yields 4.85."]),
    ('He said "rates rose." Then (it fell.) Next [one.] Last', ['He said "rates rose."', "Then (it fell.)",
                                                                 "Next [one.]", "Last"]),
    ("What? Yes! Really?! 2026 is next.", ["What?", "Yes!", "Really?!", "2026 is next."]),
    ("Grew in 2025. Then fell.", ["Grew in 2025.", "Then fell."]),
    ("rates rose. then fell.", ["rates rose. then fell."]),          # a lower-case word does not start a sentence
])
def test_sentence_boundaries(text, want):
    assert split(text) == want


def test_q3_with_a_digit_is_not_treated_as_an_abbreviation():
    # ABBREV lists q1..q4, but the abbreviation test reads letters only, so "Q3." ends a sentence (correctly so)
    assert split("Profit rose in Q3. Then it fell.") == ["Profit rose in Q3.", "Then it fell."]


def test_bullets_numbered_lists_and_capitalized_lines_break():
    text = "Intro:\n- first point\n• second point\n1. numbered\n2) also\nNew line\nlower continues"
    assert split(text) == ["Intro:", "- first point", "• second point", "1. numbered", "2) also",
                           "New line\nlower continues"]


def test_paragraph_breaks_and_whitespace_are_trimmed():
    assert split("Para one.\n\nPara two") == ["Para one.", "Para two"]
    assert split("A.\n\n\n B  ") == ["A.", "B"]
    assert split("   ") == [] and split("") == []


def test_spans_are_offset_by_base():
    text = "Rates rose. Yields fell."
    assert sentences(text, base=100) == [(100, 111), (112, 124)]


def test_is_abbrev():
    assert _is_abbrev("the U.S.", 7) and _is_abbrev("Apple Inc", 9) and _is_abbrev("J", 1)
    assert not _is_abbrev("in 2025", 7) and not _is_abbrev("rates rose", 10)


def test_sentences_are_deterministic():
    text = "The BoJ raised rates. JGB yields rose 10bp.\n\n- Brent fell 2%."
    assert sentences(text) == sentences(text) == [(0, 21), (22, 43), (45, 61)]


# -- chunks -----------------------------------------------------------------------------------------------------------
def _check(parsed: Parsed, chunks) -> None:
    text = parsed.text
    assert [c.ord for c in chunks] == list(range(len(chunks)))
    for c in chunks:
        assert text[c.start:c.end] == c.text == c.text.strip()
        assert "\n\n" not in c.text


def test_chunks_group_sentences_within_a_paragraph():
    p = Parsed("text", (Segment("One. Two. Three.\n\nFour. Five."),))
    cs = chunk(p, "t", "d")
    assert [c.text for c in cs] == ["One. Two. Three.", "Four. Five."]
    assert all(c.tenant == "t" and c.doc_id == "d" and c.page is None and c.section == "" for c in cs)
    _check(p, cs)


def test_chunks_never_cross_pages_and_carry_page_and_section():
    p = Parsed("xlsx", (Segment("Sheet: A\nBoJ | 1.25", 1, "A"), Segment("", 2, "Empty"),
                        Segment("Sheet: C\nECB | 2.25", 3, "C")))
    cs = chunk(p, "t", "d")
    assert [(c.text, c.page, c.section) for c in cs] == [("Sheet: A\nBoJ | 1.25", 1, "A"),
                                                          ("Sheet: C\nECB | 2.25", 3, "C")]
    _check(p, cs)


def test_chunks_respect_max_chars_and_a_long_sentence_is_cut_at_spaces():
    long = "The BoJ " + "very " * 40 + "slowly raised rates."
    p = Parsed("text", (Segment(f"Short one. Short two. {long} Short three."),))
    cs = chunk(p, "t", "d", max_chars=30)
    texts = [c.text for c in cs]
    assert texts[0] == "Short one. Short two." and texts[-1] == "Short three."
    assert all(len(t) <= 30 for t in texts)
    assert " ".join(texts[1:-1]) == long                     # the long sentence, in pieces cut at spaces, nothing lost
    _check(p, cs)


def test_a_long_line_is_cut_at_line_breaks_first_then_hard_when_there_is_no_space():
    from axelrod_wm.ingest.chunk import split_long

    text = "aaaa bbbb\ncccc dddd eeee"
    assert [text[a:b] for a, b in split_long(text, (0, len(text)), 12)] == ["aaaa bbbb", "cccc dddd", "eeee"]
    solid = "x" * 25
    assert [solid[a:b] for a, b in split_long(solid, (0, 25), 10)] == ["x" * 10, "x" * 10, "x" * 5]
    assert split_long("short", (0, 5), 10) == [(0, 5)]
    spaced = "ab" + " " * 12 + "cd"                          # the run of spaces between pieces is skipped
    assert [spaced[a:b] for a, b in split_long(spaced, (0, len(spaced)), 4)] == ["ab", "cd"]


def test_every_table_row_is_a_sentence():
    text = "Model inputs\nRate | 4.8 | %\nYen | 152 | per $\nThe end of the table."
    spans = [text[a:b] for a, b in sentences(text)]
    assert spans == ["Model inputs", "Rate | 4.8 | %", "Yen | 152 | per $", "The end of the table."]
    # a row's cells are never cut at a sentence's end inside a cell
    text = "BoJ rate | 1.0 | Raised in Sep. Held in Jul. | 2026-10-01\nNext."
    assert [text[a:b] for a, b in sentences(text)] == ["BoJ rate | 1.0 | Raised in Sep. Held in Jul. | 2026-10-01",
                                                       "Next."]


def test_default_chunk_size():
    sent = "Rates rose sharply today. "
    p = Parsed("text", (Segment((sent * 60).strip()),))
    cs = chunk(p, "t", "d")
    assert len(cs) == 3 and all(len(c.text) <= CHUNK_CHARS for c in cs)
    assert " ".join(c.text for c in cs) == p.text
    _check(p, cs)


def test_empty_document_has_no_chunks():
    assert chunk(Parsed("text", (Segment(""),)), "t", "d") == []
    assert chunk(Parsed("text", ()), "t", "d") == []
    # a segment of only whitespace (parse() never makes one: it normalizes) has no sentences and so no chunk
    p = Parsed("text", (Segment("  \n "), Segment("Rates rose.")))
    assert [(c.text, c.start) for c in chunk(p, "t", "d")] == [("Rates rose.", 6)]


def test_wrapped_prose_stays_one_sentence_while_headings_and_labels_break():
    prose = "Meanwhile, demand for construction equipment in North\nAmerica is recovering faster than expected."
    assert split(prose) == [prose]                                     # a full-width line wraps into the next
    long_line = "x" * 60
    assert split(f"{long_line}\nAmerica rose.") == [f"{long_line}\nAmerica rose."]
    assert split("Price (31 Jul 2026) ¥6,994\nRIC: 6301.T") == ["Price (31 Jul 2026) ¥6,994", "RIC: 6301.T"]
    heading = "Deposit Cost Reduction Helps Offset Yield Pressure For The Group"
    assert split(f"{heading}\nFollowing the results, margins rose.") == [heading, "Following the results, margins rose."]


def test_wire_headlines_and_symbol_bullets_break():
    assert split("Intro text here\n*JAPAN YIELD RISES\n a point") == ["Intro text here", "*JAPAN YIELD RISES",
                                                                             " a point"]


def test_table_lines_are_sentences():
    text = "As confirmed in the results, strength continued\n3/26 3/27E 3/28E\nRevenue (¥ bn) 4,132.8 4,472.9 4,738.1"
    assert split(text) == ["As confirmed in the results, strength continued", "3/26 3/27E 3/28E",
                           "Revenue (¥ bn) 4,132.8 4,472.9 4,738.1"]


def test_a_unit_after_a_figure_ends_no_abbreviation():
    assert split("NII of $96.5b. NII of $105.5bn. Next.") == ["NII of $96.5b.", "NII of $105.5bn.", "Next."]
    assert _is_abbrev("in 5bn", 6) is False and _is_abbrev("the bn", 6) is True


def test_symbol_bullets_and_whole_sheet_rows():
    assert split("Intro text here\n◆ The BoJ hiked.") == ["Intro text here", "◆ The BoJ hiked."]
    row = "Label | " + " | ".join(str(k) for k in range(400))
    chunks = chunk(Parsed("xlsx", (Segment(row),)), "t", "d")
    assert [c.text for c in chunks] == [row]                      # a spreadsheet row longer than a chunk stays whole
