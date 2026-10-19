"""The reading set (context/reading.py): a v4.1.4 export an answering agent can open. The domain pack stays whole as the
machine-import file; `reading/` holds the same objects in files of at most 100 KB, with a START_HERE guide. Tests use
the tracked sally_demo export and small synthetic packs; the client's data is never read."""

from __future__ import annotations

import hashlib
import json

import pytest
from fastapi.testclient import TestClient

from axelrod_wm.api.app import create_app
from axelrod_wm.context import reading
from axelrod_wm.repo.snapshots import MemoryBackend


@pytest.fixture(scope="module")
def ctx():
    app = create_app(scenario="sally_demo", storage=MemoryBackend(), trace_dir=None, play_delay=0.0)
    with TestClient(app) as c:
        return c.get("/api/context/v4").json()


def export(tmp_path, ctx, cap_kb=100, name="out"):
    """The files an export writes, then its reading set; returns (folder, manifest, coverage check)."""
    out = tmp_path / name
    out.mkdir()
    m = json.loads(json.dumps(ctx["manifest"]))
    m["load_order"].append({"file": "evidence_pack_x_forecast_FC-1.json", "source": "this export: forecast",
                            "thesis_id": "S-T1", "question": "Q?"})
    for f in m["load_order"]:
        if f["source"] == "this export: domain_pack":
            (out / f["file"]).write_text(json.dumps(ctx["domain_pack"], indent=1))
        elif f["source"] in ("this export: evidence", "this export: forecast"):
            (out / f["file"]).write_text(json.dumps(ctx["evidence"]))
        elif f["source"] == "yours, unchanged" and f["file"].startswith("000"):
            (out / f["file"]).write_text("{}")
    check = reading.build_reading_set(out, ctx, m, cap_kb=cap_kb)
    return out, m, check


def read_index(out):
    """The id index across its files, with the check that each file's header names its first and last key."""
    parts = [json.loads(p.read_text()) for p in sorted((out / "reading").glob("90_index_ids_*.json"))]
    for d in parts:
        keys = list(d["ids"])
        assert keys == sorted(keys) and d["index_shard"]["keys_from"] == keys[0] and d["index_shard"]["keys_to"] == keys[-1]
    return {"files": {k: v for d in parts for k, v in d["files"].items()}, "ids": {k: v for d in parts for k, v in d["ids"].items()}, "parts": len(parts)}


def test_every_reading_file_is_under_the_cap_and_the_pack_stays_whole(tmp_path, ctx):
    out, m, check = export(tmp_path, ctx)
    files = list((out / "reading").iterdir())
    assert files and all(f.stat().st_size <= 100 * 1024 for f in files)
    pack_entry = next(f for f in m["load_order"] if f["source"] == "this export: domain_pack")
    assert pack_entry["role"] == "machine_import" and (out / pack_entry["file"]).exists()
    assert m["read_first"] == "reading/00_START_HERE.md"
    assert json.loads((out / pack_entry["file"]).read_text()) == ctx["domain_pack"]
    assert check["ok"] and check["missing"] == 0 and check["unexpected_or_duplicated"] == 0


def test_the_shards_cover_the_pack_exactly_by_id(tmp_path, ctx):
    out, _m, _check = export(tmp_path, ctx, cap_kb=16)
    docs = [json.loads(p.read_text()) for p in sorted((out / "reading").glob("[1-6]*.json"))]
    assert len(docs) > 5                                    # a small cap forces many files
    pack = ctx["domain_pack"]
    got = {}
    for d in docs:
        for s, objs in d["sections"].items():
            got.setdefault(s, []).extend(objs)
    for key, idk in (("company_edge_relationships", "relationship_id"), ("transmission_paths", "path_id"),
                     ("financial_model_semantic_fields", "field_spec_id")):
        assert sorted(o[idk] for o in got[key]) == sorted(o[idk] for o in pack[key])
        assert sorted(json.dumps(o, sort_keys=True) for o in got[key]) == sorted(json.dumps(o, sort_keys=True) for o in pack[key])
    sup = pack["domain_specific_support_objects"]
    assert sorted(o["identity_id"] for o in got[reading.SUP + "financial_identities"]) == sorted(
        o["identity_id"] for o in sup["financial_identities"])
    assert reading.verify_coverage(pack, docs)["ok"]
    # a lost object, a duplicated one, and an altered one are all caught
    first = next(d for d in docs if "company_edge_relationships" in d["sections"])
    objs = first["sections"]["company_edge_relationships"]
    lost = json.loads(json.dumps(docs))
    lost[docs.index(first)]["sections"]["company_edge_relationships"] = objs[1:]
    assert reading.verify_coverage(pack, lost)["missing"] == 1
    twice = [*docs, {"reading_shard": {}, "sections": {"company_edge_relationships": [objs[0]]}}]
    chk = reading.verify_coverage(pack, twice)
    assert chk["unexpected_or_duplicated"] == 1 and not chk["ok"]
    assert chk["duplicate_ids"] == [f"company_edge_relationships:{objs[0]['relationship_id']}"]
    assert reading.verify_coverage({**pack, "file_index": "x"}, docs)["ok"] is False


def test_a_build_that_loses_an_object_is_refused(tmp_path, ctx, monkeypatch):
    real = reading.pack_groups
    monkeypatch.setattr(reading, "pack_groups", lambda items, budget: real(items[1:], budget))
    with pytest.raises(ValueError, match="do not cover"):
        export(tmp_path, ctx)


def test_the_output_is_deterministic(tmp_path, ctx):
    a, ma, _ = export(tmp_path, ctx, name="a")
    b, mb, _ = export(tmp_path, ctx, name="b")
    assert ma["reading_set"] == mb["reading_set"]
    names = sorted(p.name for p in (a / "reading").iterdir())
    assert names == sorted(p.name for p in (b / "reading").iterdir())
    assert all((a / "reading" / n).read_bytes() == (b / "reading" / n).read_bytes() for n in names)


def test_start_here_lists_every_file_and_the_manifest_has_their_hashes(tmp_path, ctx):
    out, m, _ = export(tmp_path, ctx)
    guide = (out / "reading" / "00_START_HERE.md").read_text()
    names = sorted(p.name for p in (out / "reading").iterdir())
    assert all(f"`{n}`" in guide for n in names)
    rs = m["reading_set"]
    assert sorted(f["file"] for f in rs["files"]) == [f"reading/{n}" for n in names]
    for f in rs["files"]:
        data = (out / f["file"]).read_bytes()
        assert f["bytes"] == len(data) and f["sha256"] == hashlib.sha256(data).hexdigest()
    assert rs["max_file_kb"] == 100 and rs["start_here"] == "reading/00_START_HERE.md"
    # the linked files (evidence, forecast, the machine-import pack, the client's own) are listed with their sizes
    assert "../evidence_pack_x_forecast_FC-1.json" in guide and "thesis S-T1" in guide and "Q?" in guide
    assert "Do not open" in guide and "../000_core_world_model_common_contract_v4.1.4.json" in guide
    assert "If any file fails to load" in guide and "Never answer as if" in guide
    for c in ctx["domain_pack"]["companies"]:
        assert c["company_name"] in guide and c["ticker"] in guide


def test_the_index_and_overviews_lead_to_the_shards(tmp_path, ctx):
    out, _m, _ = export(tmp_path, ctx)
    index = read_index(out)
    pack = ctx["domain_pack"]
    for r in pack["company_edge_relationships"]:
        code = index["ids"][f"company_edge_relationships:{r['relationship_id']}"]
        code = code if isinstance(code, str) else code[0]
        doc = json.loads((out / "reading" / index["files"][code]).read_text())
        assert r in doc["sections"]["company_edge_relationships"]
    for c in pack["companies"]:
        text = (out / "reading" / f"01_overview_{c['axelrod_entity_id']}.md").read_text()
        for p in pack["transmission_paths"]:
            if c["company_id"] in (p["primary_company_id"], *p["company_ids"]):
                assert f"`{p['path_id']}`" in text
        assert "Business composition" in text and "Calculation coverage" in text


def test_a_small_cap_splits_the_index_and_a_large_one_keeps_it_whole(tmp_path, ctx):
    small, _m, _ = export(tmp_path, ctx, cap_kb=30, name="small")
    assert read_index(small)["parts"] > 1
    # (the guide lists every file, so it grows with their number; the data files keep to the cap)
    assert all(p.stat().st_size <= 30 * 1024 for p in (small / "reading").glob("[1-9]*"))


def test_a_repeated_id_in_the_pack_is_indexed_to_every_file_that_holds_it(tmp_path, ctx):
    pack = json.loads(json.dumps(ctx["domain_pack"]))
    links = pack["domain_specific_support_objects"]["macro_transmission_links"]
    links.append({**links[0], "mechanism_label": "a second link under the same id"})
    again = {**ctx, "domain_pack": pack}
    out, _m, check = export(tmp_path, again)
    assert check["ok"]
    assert f"{reading.SUP}macro_transmission_links:{links[0]['link_id']}" in check["ids_repeated_in_the_pack_itself"]
    index = read_index(out)
    assert isinstance(index["ids"][f"macro_transmission_links:{links[0]['link_id']}"], list)


def test_groups_stay_whole_and_an_object_is_never_cut():
    items = [("s", {"v": "x" * 30}, g) for g in "aabbbc" for _ in range(1)]
    size = reading.size_of(items[0][1])
    shards = reading.pack_groups(items, size * 3)
    assert [len(s) for s in shards] == [2, 3, 1]               # group "b" (3) does not share a file with "a" (2)
    assert reading.pack_groups([], 100) == []
    # a group larger than the budget splits between objects, after the file in progress is closed
    big = [("s", {"v": "y" * 30}, "g") for _ in range(7)]
    shards = reading.pack_groups([("s", {"v": "z" * 30}, "h"), *big], size * 3)
    assert [len(s) for s in shards] == [1, 3, 3, 1]
    assert [len(s) for s in reading.pack_groups(big, size * 3)] == [3, 3, 1]
    with pytest.raises(ValueError, match="larger than"):
        reading.pack_groups([("s", {"v": "q" * 500}, "g")], 100)


def test_ids_and_sections_of_a_small_pack():
    assert reading.oid("transmission_paths", {"path_id": "P"}) == "P"
    assert reading.oid("transmission_paths", {"other": 1}) is None
    assert reading.oid("transmission_paths", "text") is None
    assert reading.oid("activation_terms", {"path_id": "P"}) is None
    header, items = reading.flatten({"a": 1, "terms": ["x", "y"], "one": {"k": 1}, "domain_specific_support_objects":
                                     {"state": {"v": 2}, "rows": [{"r": 1}], "none": []}})
    assert header == {"a": 1}
    assert items == [("terms", "x"), ("terms", "y"), ("one", {"k": 1}), (reading.SUP + "state", {"v": 2}),
                     (reading.SUP + "rows", {"r": 1})]
    counts, scope = reading.describe([("terms", "x")])
    assert counts == {"terms": 1} and scope == {}


def test_a_company_without_residual_or_eliminations_and_an_unlisted_company(tmp_path, ctx):
    pack = json.loads(json.dumps(ctx["domain_pack"]))
    sup = pack["domain_specific_support_objects"]
    for b in sup["financial_bridge"]:
        b["residual_metric"] = b["eliminations_metric"] = None
    rel = json.loads(json.dumps(pack["company_edge_relationships"][0]))
    rel.update(company_id="N_STRANGER", relationship_id="REL_STRANGER")
    pack["company_edge_relationships"].append(rel)
    out, _m, check = export(tmp_path, {**ctx, "domain_pack": pack})
    assert check["ok"]
    assert (out / "reading" / "20_relationships_n_stranger_01.json").exists()
    first = pack["companies"][0]["axelrod_entity_id"]
    assert "residual" not in (out / "reading" / f"01_overview_{first}.md").read_text().split("## Transmission")[0]


def test_a_too_small_cap_fails_loudly(tmp_path, ctx):
    with pytest.raises(ValueError, match="larger than"):
        export(tmp_path, ctx, cap_kb=1)
