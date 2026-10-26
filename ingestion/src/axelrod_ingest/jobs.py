"""Ingest jobs (Oct 26): the work behind `POST /v1/ingest?mode=async`, run one at a time on a background thread.

The hosted service sits behind a proxy that cuts any request at 300 s, and a large scanned PDF takes longer than that to
OCR. In async mode the upload is validated, held in memory as a job, and answered with `202` and a `Location`; this
module's single worker thread runs the jobs first in, first out (one at a time, so memory stays bounded and CPU-bound OCR
never competes with itself), and the caller polls `GET /v1/jobs/{id}`.

A job is a progress handle, not a record: the lake holds the result (the document is there once it is stored). Jobs live
in memory, the newest `history` of them; a finished job past that is forgotten, a queued or running one never is, and a
restart forgets all of them. The work of a job (and with it the uploaded bytes) is dropped as soon as it finishes.
"""

from __future__ import annotations

import queue
import threading
import uuid
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from axelrod_ingest.lake.store import content_id

HISTORY = 500        # jobs remembered, finished or not
BACKLOG = 100        # jobs waiting at once; past this a new one is refused so held uploads cannot fill memory

Work = Callable[[Callable[[int, str], None]], list[dict]]


def _now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class Job:
    id: str
    files: list[dict[str, Any]]
    work: Work | None = field(repr=False)
    status: str = "queued"
    created_at: str = field(default_factory=_now)
    started_at: str | None = None
    finished_at: str | None = None
    results: list[dict] | None = None
    error: str | None = None
    done: int = 0
    current: str | None = None
    finished: threading.Event = field(default_factory=threading.Event, repr=False)

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "status": self.status, "files": self.files, "created_at": self.created_at,
                "started_at": self.started_at, "finished_at": self.finished_at, "results": self.results,
                "error": self.error, "progress": {"done": self.done, "total": len(self.files), "current": self.current}}


class JobQueue:
    def __init__(self, history: int = HISTORY, backlog: int = BACKLOG) -> None:
        self.history, self.backlog = history, backlog
        self._jobs: OrderedDict[str, Job] = OrderedDict()
        self._queue: queue.Queue[Job] = queue.Queue()
        self._lock = threading.Lock()
        self._worker: threading.Thread | None = None

    def submit(self, files: list[tuple[bytes, str]], work: Work) -> Job:
        """Queue `work(progress)`, which returns the results and calls `progress(done, current)`. Raises `OverflowError`
        when `backlog` jobs are already waiting."""
        job = Job(uuid.uuid4().hex, [{"name": n, "size": len(b), "content_id": content_id(b)} for b, n in files], work)
        with self._lock:
            if self._queue.qsize() >= self.backlog:
                raise OverflowError(f"{self.backlog} jobs are already waiting")
            self._jobs[job.id] = job
            while len(self._jobs) > self.history:
                old = next((j for j in self._jobs.values() if j.finished.is_set()), None)
                if old is None:
                    break
                del self._jobs[old.id]
            self._queue.put(job)
            if self._worker is None:
                self._worker = threading.Thread(target=self._run, name="ingest-jobs", daemon=True)
                self._worker.start()
        return job

    def get(self, job_id: str) -> Job:
        with self._lock:
            job = self._jobs.get(job_id)
        if job is None:
            raise KeyError(f"no job {job_id}: it may have been lost when the service restarted, or be older than the "
                           f"last {self.history}; check the lake for the document")
        return job

    def _run(self) -> None:
        while True:
            job = self._queue.get()
            work = job.work
            job.status, job.started_at = "running", _now()

            def progress(done: int, current: str, job: Job = job) -> None:
                job.done, job.current = done, current

            try:
                job.results = work(progress)    # type: ignore[misc]     (a queued job always holds its work)
                job.status = "succeeded"
            except Exception as exc:
                job.status, job.error = "failed", f"{type(exc).__name__}: {exc}"
            job.work, job.current = None, None
            job.finished_at = _now()
            job.finished.set()


__all__ = ["BACKLOG", "HISTORY", "Job", "JobQueue"]
