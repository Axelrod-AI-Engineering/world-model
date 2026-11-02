"""The desk (Nov 2): the library, the reading queue, facts and their reviews, world models and their builds, behind one
object the web app and the command line share.

**Reading queue.** A reader asks for work (`claim`) and gets the oldest unread document that has a company, with its
pages and its company's catalog; the document is then `reading` until the reader hands figures back (`submit`) or gives up
(`fail`). A claim older than `STALE` is handed out again. The desk checks every figure again on submit (records.check_all),
whatever the reader checked, and keeps the ones that fail as rejected, with their problems.

**Builds** run one at a time on a background thread, in the order asked for.
"""

from __future__ import annotations

import json
import queue
import subprocess
import threading
import traceback
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from axelrod_desk.builds import Builder
from axelrod_desk.catalog import Catalog
from axelrod_desk.db import Db, now
from axelrod_desk.facts import resolve
from axelrod_desk.library import CLASSES, Library
from axelrod_desk.records import check_all
from axelrod_desk.settings import Settings
from axelrod_ingest.contract.world_view import WorldView

STALE = timedelta(hours=2)
MAX_FAILURES = 3


class Desk:
    def __init__(self, settings: Settings, *, poppler: bool | None = None,
                 run: Callable[..., subprocess.CompletedProcess] = subprocess.run) -> None:
        self.s = settings
        settings.home.mkdir(parents=True, exist_ok=True)
        self.db = Db(settings.db)
        raw = json.loads(settings.world_view.read_text(encoding="utf-8"))
        self.catalog = Catalog(raw, scenario_dirs=[settings.clients / "scenarios"], base=settings.base_scenario,
                               groups=settings.groups)
        graph = WorldView.from_json(json.dumps(raw.get("world_view", raw)))
        self.library = Library(self.db, self.catalog, files=settings.files, text=settings.text, lake=settings.lake,
                               world_view=graph, tenant=settings.tenant, poppler=poppler)
        self.builder = Builder(settings, self.db, self.catalog, self.library, run=run)
        self._queue: queue.Queue[int | None] = queue.Queue()
        self._worker: threading.Thread | None = None

    def close(self) -> None:
        if self._worker is not None:
            self._queue.put(None)
            self._worker.join()
        self.db.close()

    # -- reading --------------------------------------------------------------------------------------------------------
    def job(self, sha: str) -> dict[str, Any]:
        d = self.library.get(sha)
        co = self.catalog.companies[d["company"]]
        return {"document": d, "company_name": co.get("name", d["company"]), "pages": self.library.pages(sha),
                "catalog": self.catalog.metrics(d["company"])}

    def claim(self, account: dict[str, Any], reader: str = "") -> dict[str, Any] | None:
        cutoff = (datetime.now(UTC) - STALE).replace(microsecond=0).isoformat()
        for r in self.db.all("select id, sha256 from readings where status = 'running' and started_at < ?", [cutoff]):
            self.db.update("readings", "id", r["id"], {"status": "abandoned", "finished_at": now()})
            self.db.run("update documents set status = 'new' where sha256 = ? and status = 'reading'", [r["sha256"]])
        with self.db.lock:
            d = self.db.one("select sha256 from documents where status = 'new' and company is not null "
                            "order by coalesce(published, added_at), sha256 limit 1")
            if d is None:
                return None
            self.db.update("documents", "sha256", d["sha256"], {"status": "reading"})
            rid = self.db.insert("readings", {"sha256": d["sha256"], "account_id": account["id"],
                                              "reader": reader or "reader", "started_at": now(), "status": "running"})
        return {"reading_id": rid, **self.job(d["sha256"])}

    def _reading(self, reading_id: int) -> dict[str, Any]:
        r = self.db.one("select * from readings where id = ?", [reading_id])
        if r is None:
            raise KeyError(f"no reading {reading_id}")
        if r["status"] != "running":
            raise ValueError(f"reading {reading_id} is {r['status']}, not running")
        return r

    def submit(self, reading_id: int, result: dict[str, Any]) -> dict[str, Any]:
        """Check a reader's figures again and keep them: accepted ones count, rejected ones are kept with their problems."""
        r = self._reading(reading_id)
        sha = r["sha256"]
        d = self.library.get(sha)
        catalog = {m["metric_id"] for m in self.catalog.metrics(d["company"])}
        bare = {"observations": [{k: v for k, v in o.items() if k != "problems"} for o in result.get("observations", [])],
                "themes": result.get("themes", [])}
        checked = check_all(bare, source_class=d["source_class"], pages=self.library.pages(sha), catalog=catalog)
        for i, o in enumerate(checked["observations"], 1):
            problems = o.pop("problems")
            self.db.insert("records", {"id": f"{sha[:12]}-{reading_id}-{i:04d}", "sha256": sha, "reading_id": reading_id,
                                       "company": d["company"], "ok": int(not problems), "problems": problems, "data": o})
        for t in checked["themes"]:
            self.db.insert("themes", {"sha256": sha, "reading_id": reading_id, "data": t})
        n = len(checked["observations"])
        self.db.update("readings", "id", reading_id, {
            "status": "done", "finished_at": now(), "accepted": n - checked["failed"], "rejected": checked["failed"],
            "rounds": int(result.get("rounds") or 1), "cost": result.get("cost"), "model": result.get("model")})
        self.db.update("documents", "sha256", sha, {"status": "read"})
        return {"reading_id": reading_id, "accepted": n - checked["failed"], "rejected": checked["failed"],
                "themes": len(checked["themes"])}

    def fail(self, reading_id: int, error: str) -> dict[str, Any]:
        r = self._reading(reading_id)
        self.db.update("readings", "id", reading_id, {"status": "failed", "finished_at": now(), "error": error[:2000]})
        failures = self.db.one("select count(*) n from readings where sha256 = ? and status = 'failed'", [r["sha256"]])["n"]
        status = "failed" if failures >= MAX_FAILURES else "new"
        self.db.update("documents", "sha256", r["sha256"], {"status": status})
        return {"reading_id": reading_id, "document_status": status}

    def reread(self, sha: str) -> dict[str, Any]:
        d = self.library.get(sha)
        if d is None:
            raise KeyError(sha)
        if not d["company"]:
            raise ValueError("set the document's company first")
        self.db.update("documents", "sha256", sha, {"status": "new"})
        return self.library.get(sha)

    def queue_status(self) -> dict[str, Any]:
        counts = {r["status"]: r["n"] for r in self.db.all("select status, count(*) n from documents group by status")}
        running = self.db.all("select r.id, r.sha256, r.reader, r.started_at, a.name from readings r "
                              "left join accounts a on a.id = r.account_id where r.status = 'running' order by r.id")
        recent = self.db.all("select r.id, r.sha256, r.reader, r.status, r.accepted, r.rejected, r.rounds, r.cost, r.model, "
                             "r.finished_at, r.error, d.filename from readings r join documents d on d.sha256 = r.sha256 "
                             "where r.status != 'running' order by r.id desc limit 20")
        return {"documents": counts, "running": running, "recent": recent}

    def document(self, sha: str) -> dict[str, Any]:
        d = self.library.get(sha)
        if d is None:
            raise KeyError(sha)
        last = self.db.one("select * from readings where sha256 = ? and status = 'done' order by id desc limit 1", [sha])
        records = self.db.all("select id, ok, problems, data from records where reading_id = ? order by id",
                              [last["id"]]) if last else []
        themes = [t["data"] for t in self.db.all("select data from themes where reading_id = ?", [last["id"]])] if last else []
        copies = self.db.all("select sha256, filename, language, origin_role from documents where origin_group = ? "
                             "and sha256 != ?", [d["origin_group"], sha]) if d["origin_group"] else []
        return {"document": d, "readings": self.db.all("select * from readings where sha256 = ? order by id desc", [sha]),
                "records": records, "themes": themes, "copies": copies,
                "uploads": self.db.all("select u.filename, u.at, u.outcome, a.name from uploads u left join accounts a "
                                       "on a.id = u.account_id where u.sha256 = ? order by u.id", [sha])}

    # -- facts ----------------------------------------------------------------------------------------------------------
    def facts(self, company: str, *, classes: list[str] | None = None, conflicts: bool = False) -> list[dict[str, Any]]:
        if company not in self.catalog.companies:
            raise KeyError(f"no company {company}")
        classes = classes or list(CLASSES)
        reviews = {r["fact_key"]: r for r in self.db.all("select * from reviews")}
        out = []
        for f in resolve(self.builder.records([company], classes), self.builder.baseline([company])):
            new = [c for c in f.citations if not c.get("baseline")]
            if not new or (conflicts and not f.conflict):
                continue
            rv = reviews.get(f.key)
            out.append({**f.to_dict(), "review": {"decision": rv["decision"], "at": rv["at"], "note": rv["note"]} if rv else None})
        return out

    def review(self, key: str, decision: str, account: dict[str, Any], note: str = "") -> dict[str, Any]:
        if decision not in ("approve", "reject", "clear"):
            raise ValueError("a review is approve, reject or clear")
        if decision == "clear":
            self.db.run("delete from reviews where fact_key = ?", [key])
        else:
            self.db.insert("reviews", {"fact_key": key, "decision": decision, "account_id": account["id"], "at": now(),
                                       "note": note}, replace=True)
        return {"key": key, "decision": decision}

    # -- world models and builds ----------------------------------------------------------------------------------------
    def _wm_fields(self, body: dict[str, Any]) -> dict[str, Any]:
        name = (body.get("name") or "").strip()
        if not name:
            raise ValueError("a world model needs a name")
        companies, groups = list(body.get("companies") or []), list(body.get("groups") or [])
        self.catalog.expand(companies, groups)
        classes = list(body.get("classes") or [])
        if not classes or set(classes) - set(CLASSES):
            raise ValueError(f"choose source classes among {', '.join(CLASSES)}")
        if not companies and not groups:
            raise ValueError("choose at least one company or group")
        return {"name": name, "companies": companies, "groups": groups, "classes": classes, "apply": int(bool(body.get("apply")))}

    def world_models(self, account: dict[str, Any]) -> list[dict[str, Any]]:
        rows = self.db.all("select * from world_models where account_id = ? order by id desc", [account["id"]])
        for w in rows:
            w["apply"] = bool(w["apply"])
            w["builds"] = self.db.all("select id, status, started_at, finished_at, error from builds "
                                      "where world_model_id = ? order by id desc limit 5", [w["id"]])
        return rows

    def world_model(self, wm_id: int, account: dict[str, Any]) -> dict[str, Any]:
        w = self.db.one("select * from world_models where id = ? and account_id = ?", [wm_id, account["id"]])
        if w is None:
            raise KeyError(f"no world model {wm_id}")
        return {**w, "apply": bool(w["apply"])}

    def save_world_model(self, account: dict[str, Any], body: dict[str, Any], wm_id: int | None = None) -> dict[str, Any]:
        fields = self._wm_fields(body)
        if wm_id is None:
            wm_id = self.db.insert("world_models", {"account_id": account["id"], "created_at": now(), **fields})
        else:
            self.world_model(wm_id, account)
            self.db.update("world_models", "id", wm_id, fields)
        return self.world_model(wm_id, account)

    def delete_world_model(self, wm_id: int, account: dict[str, Any]) -> None:
        self.world_model(wm_id, account)
        self.db.run("delete from world_models where id = ?", [wm_id])

    def start_build(self, wm_id: int, account: dict[str, Any]) -> dict[str, Any]:
        self.world_model(wm_id, account)
        bid = self.db.insert("builds", {"world_model_id": wm_id, "account_id": account["id"], "status": "queued",
                                        "started_at": now()})
        if self._worker is None:
            self._worker = threading.Thread(target=self._work, name="desk-builds", daemon=True)
            self._worker.start()
        self._queue.put(bid)
        return self.build(bid, account)

    def _work(self) -> None:
        while (bid := self._queue.get()) is not None:
            self.run_build(bid)

    def run_build(self, build_id: int) -> dict[str, Any]:
        b = self.db.one("select * from builds where id = ?", [build_id])
        wm = self.db.one("select * from world_models where id = ?", [b["world_model_id"]])
        self.db.update("builds", "id", build_id, {"status": "running"})
        try:
            summary = self.builder.build(build_id, wm)
        except Exception as err:            # a failed build is reported on the build, never raised into the app
            self.db.update("builds", "id", build_id, {"status": "failed", "finished_at": now(),
                                                      "error": f"{err}\n{traceback.format_exc()[-1500:]}"})
        else:
            self.db.update("builds", "id", build_id, {"status": "done", "finished_at": now(), "summary": summary,
                                                      "zip": summary["zip"], "out_dir": summary["out_dir"]})
        return self.db.one("select * from builds where id = ?", [build_id])

    def build(self, build_id: int, account: dict[str, Any]) -> dict[str, Any]:
        b = self.db.one("select b.* from builds b join world_models w on w.id = b.world_model_id "
                        "where b.id = ? and w.account_id = ?", [build_id, account["id"]])
        if b is None:
            raise KeyError(f"no build {build_id}")
        return b


__all__ = ["MAX_FAILURES", "STALE", "Desk"]
