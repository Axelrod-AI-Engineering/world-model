"""Boot the world model's image as Railway does, before it is deployed (Oct 26).

Every world-model deployment that failed on Railway (Oct 10–26) built fine and then failed to boot: a restore whose
state hash differed under a new process's hash seed (Oct 26, three times), a Mac resource fork (`._entities.yaml`) on
the volume that the loader read as YAML (Oct 22), and a startup that outlasted the healthcheck (Oct 22). The unit and
service suites run in one process and never boot the image, so none of them could see these. This does:

1. Builds nothing itself: it runs an image already built from the repository's Dockerfile (CI builds it first).
2. Boots it on an empty volume, the way `.railway/railway.ts` runs it: the start script, the dev profile, Basic Auth,
   logins that open compartments, a static API key, and client content on the volume. The content is the synthetic
   client (world_model/tests/fixtures/clients: a unified model over two worlds, and a focus per login), with the junk a
   Mac copy brings (`._*` resource forks, `.DS_Store`) planted beside it.
3. Requires `GET /api/health` within the budget (default 300 s, half of Railway's 600 s healthcheck).
4. Writes: an upload read into a bundle, its changes proposed and applied, so the volume holds versions, snapshots,
   and a lakehouse; and reads each login's compartment.
5. Stops it (SIGTERM, as a redeploy does) and boots it again twice, each under another PYTHONHASHSEED. Each boot must be
   healthy within the budget and resume the same version with the same state hash.

    python3 scripts/deploy/boot_check.py --image world-model:ci [--budget 300] [--summary FILE]

Stdlib only (and the docker CLI), so it runs before any environment is installed. Exit 0 when every check passes, 1
otherwise, with the container's log tail printed.
"""

from __future__ import annotations

import argparse
import http.cookiejar
import json
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "world_model" / "tests" / "fixtures" / "clients"
SCENARIO = "unified_demo"
LOGINS = {"acme": "acme_unified_focus", "nw": "northwind_focus"}
SCOPES = "world_model:read+documents:create+changes:create+simulations:create+admin"
SEEDS = ("1", "2", "3")                      # one per boot: the first writes, the others must resume the same state
NOTE = (b"Data, September 1, 2026. The central bank held rates at 4.0%. The crude price rose to $103 a barrel.\n\n"
        b"Northwind Air said jet fuel costs rose as crude climbed.")
# what a Mac copy leaves beside the content (an AppleDouble header, then bytes that are not UTF-8)
APPLE_DOUBLE = b"\x00\x05\x16\x07\x00\x02\x00\x00Mac OS X        \x00\x02\xa3\xa3\xa3\x00"
JUNK = ("worlds/acme_demo/._entities.yaml", "worlds/northwind_demo/construction/._harbor_steel.yaml",
        f"scenarios/{SCENARIO}/._scenario.yaml", "scenarios/.DS_Store")


class Failed(Exception):
    """A check that did not pass."""


def docker(*args: str, check: bool = True) -> str:
    out = subprocess.run(["docker", *args], capture_output=True, text=True)
    if check and out.returncode != 0:
        raise Failed(f"docker {' '.join(args[:2])}: {out.stderr.strip()[:500]}")
    return out.stdout.strip()


def plant_content(dest: Path) -> Path:
    """The synthetic client content, as it would sit on the volume, with a Mac copy's junk beside it."""
    root = dest / "clients"
    shutil.copytree(FIXTURE, root)
    for rel in JUNK:
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_bytes(APPLE_DOUBLE)
    return root


def environment(user: str, password: str, key: str) -> dict[str, str]:
    """The service's variables, as railway.ts and the creds sync set them on dev (with throwaway secrets)."""
    return {
        "PORT": "8080", "WORLD_MODEL_SCENARIO": SCENARIO, "WORLD_MODEL_CLIENT_DIR": "/app/var/clients",
        "RAILWAY_ENVIRONMENT_NAME": "dev", "WORLD_MODEL_REQUIRE_BASIC_AUTH": "1",
        "WORLD_MODEL_BASIC_AUTH_USERNAME": user, "WORLD_MODEL_BASIC_AUTH_PASSWORD": password,
        "WORLD_MODEL_LOGINS": ",".join(f"{login}:{password}:{scenario}" for login, scenario in LOGINS.items()),
        "WORLD_MODEL_API_KEYS": f"boot:{key}:axelrod-internal:{SCOPES}",
        "WORLD_MODEL_EMBEDDER": "hashing",          # on Railway the ingestion service embeds; no model download here
    }


class Http:
    """A client of one running container: JSON calls with the API key, and a signed-in session per login."""

    def __init__(self, base: str, key: str, password: str) -> None:
        self.base, self.key, self.password = base, key, password

    def call(self, method: str, path: str, body: bytes | None = None, headers: dict | None = None,
             opener: urllib.request.OpenerDirector | None = None, timeout: float = 120) -> tuple[int, dict]:
        req = urllib.request.Request(self.base + path, data=body, method=method, headers=headers or {})
        try:
            with (opener or urllib.request.build_opener()).open(req, timeout=timeout) as r:
                raw = r.read()
                return r.status, json.loads(raw) if raw else {}
        except urllib.error.HTTPError as err:
            raw = err.read()
            try:
                return err.code, json.loads(raw)
            except ValueError:
                return err.code, {"raw": raw[:300].decode(errors="replace")}

    def v1(self, method: str, path: str, **kw) -> tuple[int, dict]:
        return self.call(method, "/v1" + path, headers={"Authorization": f"Bearer {self.key}", **kw.pop("headers", {})},
                         **kw)

    def session(self, user: str) -> urllib.request.OpenerDirector:
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        form = urllib.parse.urlencode({"username": user, "password": self.password, "next": "/"}).encode()
        opener.open(urllib.request.Request(self.base + "/login", data=form, method="POST"), timeout=30)
        return opener

    def upload(self, wm: str, name: str, data: bytes) -> tuple[int, dict]:
        boundary = "boot" + secrets.token_hex(8)
        body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"files\"; filename=\"{name}\"\r\n"
                "Content-Type: text/plain\r\n\r\n").encode() + data + f"\r\n--{boundary}--\r\n".encode()
        return self.v1("POST", f"/world-models/{wm}/documents", body=body,
                       headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})


def wait_healthy(http: Http, container: str, budget: float) -> tuple[float, dict]:
    """Seconds until /api/health answered 200, and its answer; Failed when the budget runs out or the container exits."""
    t0 = time.monotonic()
    while time.monotonic() - t0 < budget:
        if docker("inspect", "-f", "{{.State.Running}}", container) != "true":
            raise Failed("the container exited during startup")
        try:
            status, body = http.call("GET", "/api/health", timeout=5)
            if status == 200 and body.get("ok"):
                return time.monotonic() - t0, body
        except (urllib.error.URLError, ConnectionError, TimeoutError, OSError):
            pass
        time.sleep(2)
    raise Failed(f"/api/health did not answer within {budget:.0f} s")


def latest(http: Http) -> dict:
    status, body = http.v1("GET", f"/world-models/{SCENARIO}/versions/latest")
    if status != 200:
        raise Failed(f"versions/latest answered {status}: {body}")
    return {k: body["data"][k] for k in ("number", "state_hash")}


def write_versions(http: Http, user: str) -> dict:
    """Upload a note, propose its changes under auto-approval, and return the version it reached."""
    before = latest(http)
    admin = http.session(user)
    status, _ = http.call("PATCH", "/api/config/review", json.dumps({"policy": "auto_approve_all", "by": "boot-check"}).encode(),
                          {"Content-Type": "application/json"}, opener=admin)
    if status != 200:
        raise Failed(f"setting auto-approval answered {status}")
    status, job = http.upload(SCENARIO, "2026-09-01_data.txt", NOTE)
    if status != 202 or job["data"]["status"] != "succeeded":
        raise Failed(f"the upload answered {status}: {json.dumps(job)[:300]}")
    bundle = job["data"]["result"]["detail"]["results"][0]["bundle_id"]
    status, job = http.v1("POST", f"/world-models/{SCENARIO}/changes", body=json.dumps({"bundle_id": bundle}).encode(),
                          headers={"Content-Type": "application/json"})
    if status != 202 or job["data"]["status"] != "succeeded":
        raise Failed(f"proposing the changes answered {status}: {json.dumps(job)[:300]}")
    after = latest(http)
    if after["number"] <= before["number"]:
        raise Failed(f"no version was written: still {after['number']}")
    return after


def read_compartments(http: Http) -> None:
    for login in LOGINS:
        status, body = http.call("GET", "/api/state", opener=http.session(login))
        if status != 200 or not body.get("entities"):
            raise Failed(f"login {login} could not read its compartment ({status})")


def run(image: str, budget: float) -> list[tuple[str, str]]:
    """Every boot's checks, as (check, result) rows; raises Failed at the first that fails."""
    rows: list[tuple[str, str]] = []
    user, password, key = "boot-admin", secrets.token_urlsafe(16), secrets.token_hex(16)
    env = [x for k, v in environment(user, password, key).items() for x in ("-e", f"{k}={v}")]
    volume = docker("volume", "create")
    container = ""
    try:
        with tempfile.TemporaryDirectory() as tmp:
            content = plant_content(Path(tmp))
            state = None
            for n, seed in enumerate(SEEDS):
                container = docker("create", "-p", "127.0.0.1::8080", "-v", f"{volume}:/app/var", *env,
                                   "-e", f"PYTHONHASHSEED={seed}", image)
                if n == 0:
                    docker("cp", str(content), f"{container}:/app/var/clients")
                docker("start", container)
                port = docker("port", container, "8080/tcp").splitlines()[0].rsplit(":", 1)[1]
                http = Http(f"http://127.0.0.1:{port}", key, password)
                secs, health = wait_healthy(http, container, budget)
                rows.append((f"boot {n + 1} (PYTHONHASHSEED={seed}) healthy", f"{secs:.0f} s of {budget:.0f}"))
                if n == 0:
                    read_compartments(http)
                    rows.append(("each login reads its compartment", ", ".join(LOGINS)))
                    state = write_versions(http, user)
                    rows.append(("an upload's changes applied", f"version {state['number']}"))
                else:
                    got = latest(http)
                    if got != state:
                        raise Failed(f"boot {n + 1} resumed {got}, not {state}")
                    rows.append((f"boot {n + 1} resumed the same state", f"version {got['number']}, {got['state_hash'][:12]}"))
                docker("stop", "-t", "30", container)
                docker("rm", container)
                container = ""
        return rows
    except Failed:
        if container:
            print(docker("logs", "--tail", "120", container, check=False), file=sys.stderr)
        raise
    finally:
        if container:
            docker("rm", "-f", container, check=False)
        docker("volume", "rm", "-f", volume, check=False)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--image", required=True)
    ap.add_argument("--budget", type=float, default=300.0, help="seconds a boot may take to be healthy")
    ap.add_argument("--summary", help="a Markdown file to append the results to (GitHub's step summary)")
    args = ap.parse_args(argv)
    try:
        rows, error = run(args.image, args.budget), None
    except Failed as err:
        rows, error = [], str(err)
    lines = ["### Boot check", "", "| Check | Result |", "|---|---|", *[f"| {a} | {b} |" for a, b in rows]]
    if error:
        lines.append(f"| **failed** | {error} |")
    print("\n".join(lines))
    if args.summary:
        with open(args.summary, "a") as f:
            f.write("\n".join(lines) + "\n")
    return 1 if error else 0


if __name__ == "__main__":
    sys.exit(main())
