"""Decoding: a byte-order mark first, then an HTML page's own declaration (browser-style supersets), then UTF-8, and
only then Latin-1, reported as a fallback. Every sentence here is invented."""

from __future__ import annotations

import pytest

from axelrod_ingest.encoding import ALIASES, decode, declared

ZH = "新能源汽车销量同比增长，净利润保持稳定。"
KO = "영업이익은 전년 대비 증가했습니다."


def page(charset: str, body: str, *, tag: str = "charset") -> str:
    meta = (f'<meta charset="{charset}">' if tag == "charset" else
            f'<meta http-equiv="Content-Type" content="text/html; charset={charset}">')
    return f"<html><head><title>x</title>{meta}</head><body>{body}</body></html>"


@pytest.mark.parametrize("label,codec,body", [
    ("gb2312", "gbk", ZH), ("GBK", "gbk", ZH), ("gb18030", "gb18030", ZH + "\U00020000"),
    ("euc-kr", "euc-kr", KO), ("ks_c_5601-1987", "cp949", KO), ("cp949", "cp949", KO + "똠"),
    ("utf-8", "utf-8", ZH), ("big5", "big5hkscs", "新能源汽車銷量"), ("shift_jis", "cp932", "売上高は増加した"),
])
@pytest.mark.parametrize("tag", ["charset", "http-equiv"])
def test_a_declared_charset_is_honoured(label, codec, body, tag):
    d = decode(page(label, body, tag=tag).encode(codec), html=True)
    assert body in d.text and d.how == "declared"


def test_declared_names_are_read_as_their_supersets():
    assert declared(page("gb2312", "").encode()) == "gb18030" and declared(page("euc-kr", "").encode()) == "cp949"
    assert declared(page("iso-8859-1", "").encode()) == "cp1252" and declared(page("us-ascii", "").encode()) == "cp1252"
    assert set(ALIASES.values()) >= {"gb18030", "cp949", "cp932", "big5hkscs", "cp1252"}


def test_an_xml_declaration_counts():
    data = f'<?xml version="1.0" encoding="GBK"?><html><body>{ZH}</body></html>'.encode("gbk")
    assert declared(data) == "gb18030" and ZH in decode(data, html=True).text


def test_no_declaration_or_an_unknown_one_means_utf8():
    assert declared(b"<html><body>plain</body></html>") is None
    assert declared(page("x-no-such-charset", "").encode()) is None
    d = decode(page("x-no-such-charset", ZH).encode(), html=True)
    assert ZH in d.text and (d.encoding, d.how) == ("utf-8", "utf-8")


def test_a_declaration_the_bytes_do_not_fit_is_not_trusted():
    # declared gb2312, but the bytes are UTF-8 Korean: gb18030 cannot read them, so UTF-8 does
    d = decode(page("gb2312", KO).encode("utf-8"), html=True)
    assert KO in d.text and (d.encoding, d.how) == ("utf-8", "utf-8")
    # declared gb2312 and neither it nor UTF-8 fits: Latin-1, reported as a fallback
    d = decode(b"<meta charset=gb2312>\xff\xfe\xff", html=True)
    assert (d.encoding, d.how) == ("latin-1", "fallback")


def test_a_declaration_is_read_from_the_head_only():
    late = b"<html><body>" + b"x" * 5000 + b'<meta charset="gb2312"></body></html>'
    assert declared(late) is None


def test_non_html_ignores_declarations():
    d = decode(page("gb2312", ZH).encode("gbk"))              # not html=True: no sniffing, UTF-8 fails, Latin-1
    assert d.how == "fallback"


@pytest.mark.parametrize("data,name", [
    (b"\xef\xbb\xbf" + ZH.encode(), "utf-8"), (ZH.encode("utf-16"), "utf-16"),
    (ZH.encode("utf-32"), "utf-32"), (b"\xfe\xff" + ZH.encode("utf-16-be"), "utf-16"),
])
def test_a_byte_order_mark_decides_first(data, name):
    d = decode(data, html=True)
    assert d.text == ZH and d.encoding == name and d.how == "bom"


def test_a_bom_the_bytes_do_not_fit_is_ignored():
    d = decode(b"\xff\xfe\x00", html=False)                  # UTF-16 needs an even length
    assert d.how == "fallback"


def test_plain_utf8_and_empty():
    assert decode(KO.encode()).how == "utf-8" and decode(b"").text == ""
