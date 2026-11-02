"""The reader, left running on a person's own computer (Nov 2): it takes unread documents from the desk, reads each with
the person's own Claude Code (reader.py), and hands the checked figures back.

    axelrod-desk reader --url http://localhost:8765 --token <the reader token from the desk's Reader page>

The token is the desk's own: it lets this reader take work and return figures for its account, nothing else. The reading
itself uses whatever Claude Code is signed in to on this machine (`claude` once, then its own sign-in), on that person's
plan; neither the desk nor this command sees or keeps that sign-in. With `--drain` it stops when no document is left.
"""

from __future__ import annotations

import platform
import time
from collections.abc import Callable
from typing import Any

import httpx

from axelrod_desk.reader import ClaudeCode, ReaderError, read


class DeskClient:
    def __init__(self, url: str, token: str, *, client: httpx.Client | None = None) -> None:
        self.http = client or httpx.Client(base_url=url.rstrip("/"), timeout=120)
        self.http.headers["Authorization"] = f"Bearer {token}"

    def _post(self, path: str, body: dict[str, Any]) -> httpx.Response:
        r = self.http.post(path, json=body)
        if r.status_code >= 400:
            raise RuntimeError(f"the desk answered {r.status_code} to {path}: {r.text[:300]}")
        return r

    def claim(self, reader: str) -> dict[str, Any] | None:
        r = self._post("/api/reader/claim", {"reader": reader})
        return None if r.status_code == 204 else r.json()

    def submit(self, reading_id: int, result: dict[str, Any]) -> dict[str, Any]:
        return self._post(f"/api/reader/readings/{reading_id}", result).json()

    def fail(self, reading_id: int, error: str) -> dict[str, Any]:
        return self._post(f"/api/reader/readings/{reading_id}/fail", {"error": error}).json()


def check_claude(claude: ClaudeCode) -> str:
    """Whether Claude Code runs and is signed in here: the model it answered with, or a ReaderError saying what to do."""
    import tempfile
    from pathlib import Path

    schema = {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"], "additionalProperties": False}
    with tempfile.TemporaryDirectory() as tmp:
        try:
            answer = claude('Answer {"ok": true}.', Path(tmp), schema)
        except ReaderError as err:
            raise ReaderError(f"{err}. Install Claude Code, run `claude` once and sign in, then start the reader "
                              "again.") from err
    return answer.model or "your default model"


def run(client: DeskClient, claude: ClaudeCode, *, drain: bool = False, idle: float = 30, rounds: int = 3,
        sleep: Callable[[float], None] = time.sleep, log: Callable[[str], None] = print) -> int:
    """Read until stopped (or, with `drain`, until nothing is left). The number of documents read."""
    name = f"{platform.node() or 'reader'} ({claude.binary})"
    done = 0
    while True:
        job = client.claim(name)
        if job is None:
            if drain:
                return done
            sleep(idle)
            continue
        d = job["document"]
        log(f"reading {d['filename']} ({len(job['pages'])} pages, {job['company_name']}, {d['source_class']})")
        try:
            result = read(job, claude, rounds=rounds)
        except ReaderError as err:
            client.fail(job["reading_id"], str(err))
            log(f"  failed: {err}")
            continue
        res = client.submit(job["reading_id"], result)
        done += 1
        log(f"  {res['accepted']} figures accepted, {res['rejected']} rejected, {res['themes']} themes "
            f"({result['rounds']} round(s))")


__all__ = ["DeskClient", "check_claude", "run"]
