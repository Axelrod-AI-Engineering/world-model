"""Shared fixtures: an invented world (two auto companies, a bank, a market, an agency), its construction and a focused
scenario, a desk home on disk, and documents built byte for byte. No client data. The isolated lake, the hashing embedder
and no LLM step come from ingestion's pytest plugin."""

from __future__ import annotations

import io
import json
import subprocess
from pathlib import Path

import pytest

from axelrod_desk import settings
from axelrod_desk.desk import Desk

pytest_plugins = ["axelrod_ingest.testing"]

WORLD_VIEW = {"inverted": [], "world_view": {
    "entities": [
        {"id": "acme", "kind": "company", "name": "Acme Motors", "aliases": ["Acme", "7203 JP"], "sector": "autos",
         "region": "JP", "subentity_ids": ["acme.revenue", "acme.units"]},
        {"id": "rival", "kind": "company", "name": "Rival Batteries", "aliases": ["Rival", "300750 CH"], "sector": "autos",
         "subentity_ids": ["rival.revenue"]},
        {"id": "solo", "kind": "company", "name": "Solo Bank", "aliases": [], "sector": "banks", "subentity_ids": ["solo.loans"]},
        {"id": "plain", "kind": "company", "name": "Plain", "aliases": [], "subentity_ids": []},
        {"id": "usd_jpy", "kind": "market", "name": "Dollar yen", "aliases": [], "subentity_ids": ["usd_jpy.rate"]},
        {"id": "boj", "kind": "agency", "name": "Bank of Japan", "aliases": [], "subentity_ids": ["boj.rate"]}],
    "values": [
        {"id": "acme.revenue", "entity_id": "acme", "name": "Acme revenue", "attribute_kind": "revenue_flow",
         "unit": "JPY bn per quarter"},
        {"id": "acme.units", "entity_id": "acme", "name": "Acme units", "attribute_kind": "volume", "unit": "units"},
        {"id": "rival.revenue", "entity_id": "rival", "name": "Rival revenue", "attribute_kind": "revenue_flow",
         "unit": "RMB bn"},
        {"id": "solo.loans", "entity_id": "solo", "name": "Solo loans", "attribute_kind": "stock", "unit": "USD bn"},
        {"id": "usd_jpy.rate", "entity_id": "usd_jpy", "name": "USD/JPY", "attribute_kind": "price", "unit": "JPY"},
        {"id": "boj.rate", "entity_id": "boj", "name": "BOJ policy rate", "attribute_kind": "rate", "unit": "pct"}],
    "links": [
        {"id": "l1", "source_id": "boj.rate", "target_id": "acme.revenue"},
        {"id": "l2", "source_id": "acme.revenue", "target_id": "rival.revenue"},
        {"id": "l3", "source_id": "acme.units", "target_id": "acme.revenue"}]}}
for _v in WORLD_VIEW["world_view"]["values"]:
    _v["aliases"] = []

BASE_OBS = [
    {"observation_id": "OBS_ACME_REV_Q2", "metric_id": "acme.revenue", "label": "Revenue, Q2",
     "period": {"label": "Q2 2026", "type": "quarter", "start": "2026-04-01", "end": "2026-06-30"}, "value": 100.0,
     "unit": "JPY bn per quarter", "kind": "reported actual", "available_at": "2026-08-01", "selected_baseline": True,
     "source": {"source_id": "s.acme", "document": "data/sources/acme/h1.pdf", "location": "page 3"}}]


def pdf(pages: list[str]) -> bytes:
    """A real PDF: one Helvetica text line per page line, with a correct xref table (as ingestion's tests build them)."""
    n = len(pages)
    font = 3 + 2 * n
    objs: list[bytes] = [b"<< /Type /Catalog /Pages 2 0 R >>",
                         ("<< /Type /Pages /Kids [" + " ".join(f"{3 + 2 * k} 0 R" for k in range(n))
                          + f"] /Count {n} >>").encode()]
    for k, text in enumerate(pages):
        ops = "BT /F1 12 Tf 72 720 Td 14 TL " + " ".join(
            "(" + ln.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)") + ") Tj T*" for ln in text.split("\n")) + " ET"
        stream = ops.encode("latin-1")
        objs.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents {4 + 2 * k} 0 R "
                    f"/Resources << /Font << /F1 {font} 0 R >> >> >>".encode())
        objs.append(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
    objs.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = []
    for k, body in enumerate(objs):
        offsets.append(out.tell())
        out.write(b"%d 0 obj\n" % (k + 1) + body + b"\nendobj\n")
    xref = out.tell()
    out.write(b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1))
    out.write(b"".join(b"%010d 00000 n \n" % o for o in offsets))
    out.write(b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref))
    return out.getvalue()


REPORT = ["Acme Motors Q3 2026 results", "Revenue for the quarter was JPY 120.5 bn\nUnits sold 50,000",
          "Outlook: revenue of JPY 130 bn next quarter"]


def write_home(home: Path, *, client_core: bool = True) -> Path:
    data = home / "data"
    cons = data / "construction"
    for co, obs in (("acme", BASE_OBS), ("rival", [])):
        (cons / co).mkdir(parents=True)
        (cons / co / "sources.json").write_text(json.dumps({"sources": {"s.acme": {"file": "data/sources/acme/h1.pdf"}}}))
        (cons / co / "citations.json").write_text("{}")
        (cons / co / "repair.json").write_text(json.dumps({"observations": obs}))
    (cons / "solo").mkdir()
    (cons / "solo" / "sources.json").write_text(json.dumps({"s.solo": {"file": "x.pdf"}}))
    (cons / "solo" / "citations.json").write_text("{}")
    scen = data / "clients" / "scenarios"
    (scen / "focus_autos").mkdir(parents=True)
    (scen / "focus_autos" / "scenario.yaml").write_text(
        "id: focus_autos\ntitle: Autos\nfocus:\n  base: unified\n  companies: [acme, rival]\n"
        "context_pack:\n  name: 'Focus: autos'\n")
    (scen / "elsewhere").mkdir()
    (scen / "elsewhere" / "scenario.yaml").write_text("id: elsewhere\nfocus:\n  base: other\n  companies: [acme, rival]\n")
    (data / "world_view.json").write_text(json.dumps(WORLD_VIEW))
    (data / "core").mkdir()
    home.mkdir(parents=True, exist_ok=True)
    (home / "desk.toml").write_text(
        'repo = "repo"\ndata = "data"\nclients = "data/clients"\nconstruction = "data/construction"\n'
        'world_view = "data/world_view.json"\n' + ('client_core = "data/core"\n' if client_core else "")
        + 'remaps = ["old/=new/"]\n[groups]\nmine = ["acme", "solo"]\n')
    (home / "repo").mkdir()
    return home


def fake_export(cmd, cwd, env, capture_output, text):
    """The world model's export scripts, as far as a build needs them: the v4.1.4 folder and the evaluation export."""
    if "export_context.py" in cmd[-8:] or any(c.endswith("export_context.py") for c in cmd):
        out = Path(cmd[cmd.index(next(c for c in cmd if c.endswith("export_context.py"))) + 2])
        out.mkdir(parents=True)
        (out / "036_pack.json").write_text("{}")
        (out / "reading").mkdir()
        (out / "reading" / "00_START_HERE.md").write_text("start")
    else:
        Path(cmd[cmd.index("snapshot") + 2]).write_text(json.dumps({"remaps": [cmd[i + 1] for i, c in enumerate(cmd)
                                                                               if c == "--remap"]}))
    return subprocess.CompletedProcess(cmd, 0, "folded in 2 bundles\nHTTP Request: noise", "")


@pytest.fixture
def home(tmp_path) -> Path:
    return write_home(tmp_path / "home")


@pytest.fixture
def desk(home):
    d = Desk(settings.load(home), poppler=False, run=fake_export)
    yield d
    d.close()


@pytest.fixture
def person(desk):
    from axelrod_desk import accounts

    return accounts.create(desk.db, "ada@example.com", "Ada", "a long password", admin=True)
