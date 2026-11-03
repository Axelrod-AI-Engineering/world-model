"""The desk's web app (Nov 2): sign-in, the library, facts and their review, readers, world models and their builds.

A person signs in with a desk account (a session cookie); the first admin account is made on first visit, and the
admin adds the others. A reader authenticates with its account's reader token (`Authorization: Bearer`) and reaches only the
reader routes. Errors are JSON `{"detail": ...}`: 401 not signed in, 403 not allowed, 404 not found, 422 a bad request.

    GET  /api/setup                 whether the first account is still to be made; POST makes it
    POST /api/login, /api/logout    GET /api/me (with the reader's status)  POST /api/me/reader-token (shown once)
    GET  /api/accounts              (admin) POST adds an account
    GET  /api/catalog               companies, groups and source classes
    GET  /api/documents             ?company=&source_class=&status=   POST (multipart files[], with an optional MANIFEST.md
                                    among them, and company, source_class, publisher, published) adds them
    GET  /api/documents/{sha}       with its readings, figures, themes, copies and uploads   PATCH corrects it
    GET  /api/documents/{sha}/file  the file as added      GET .../pages/{n} one page's text    POST .../reread
    GET  /api/facts?company=&conflicts=1    POST /api/facts/review {key, decision: approve|reject|clear, note}
    GET  /api/reader/status         the queue and the readings
    POST /api/reader/claim          (reader) the next document, or 204    POST /api/reader/readings/{id}[/fail]
    GET  /api/world-models          POST saves one   PUT/DELETE /api/world-models/{id}   POST .../builds starts a build
    GET  /api/builds/{id}           GET /api/builds/{id}/download (the zip)
"""

from __future__ import annotations

from importlib import resources
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, File, Form, Request, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from axelrod_desk import accounts
from axelrod_desk.desk import Desk
from axelrod_desk.library import CLASSES, wanted
from axelrod_ingest.sources import read_manifest

COOKIE = "desk_session"
STATIC = {"/": ("index.html", "text/html"), "/app.js": ("app.js", "text/javascript"), "/app.css": ("app.css", "text/css")}


class Credentials(BaseModel):
    email: str
    password: str
    name: str = ""
    admin: bool = False


class DocumentEdit(BaseModel):
    company: str | None = None
    source_class: str | None = None
    publisher: str | None = None
    published: str | None = None
    note: str | None = None


class Review(BaseModel):
    key: str
    decision: str
    note: str = ""


class Claim(BaseModel):
    reader: str = ""


class Failure(BaseModel):
    error: str


class WorldModelBody(BaseModel):
    name: str
    companies: list[str] = []
    groups: list[str] = []
    classes: list[str] = []
    apply: bool = False


def create_app(desk: Desk, *, secure_cookie: bool = False) -> FastAPI:
    app = FastAPI(title="Axelrod desk", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.desk = desk
    db = desk.db

    @app.exception_handler(KeyError)
    async def _missing(request: Request, exc: KeyError) -> JSONResponse:
        return JSONResponse({"detail": str(exc.args[0]) if exc.args else "not found"}, status_code=404)

    @app.exception_handler(ValueError)
    async def _bad(request: Request, exc: ValueError) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=422)

    @app.exception_handler(PermissionError)
    async def _forbidden(request: Request, exc: PermissionError) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=exc.args[1] if len(exc.args) > 1 else 403)

    def person(request: Request) -> dict[str, Any]:
        a = accounts.resolve(db, request.cookies.get(COOKIE, ""), "web")
        if a is None:
            raise PermissionError("sign in first", 401)
        return a

    def admin(a: dict[str, Any] = Depends(person)) -> dict[str, Any]:
        if not a["admin"]:
            raise PermissionError("only an admin can do this")
        return a

    def reader(request: Request) -> dict[str, Any]:
        scheme, _, token = request.headers.get("authorization", "").partition(" ")
        a = accounts.resolve(db, token, "reader") if scheme.lower() == "bearer" else None
        if a is None:
            raise PermissionError("a reader token is required", 401)
        return a

    def signed_in(response: Response, a: dict[str, Any]) -> dict[str, Any]:
        response.set_cookie(COOKIE, accounts.issue(db, a["id"]), httponly=True, samesite="lax", secure=secure_cookie,
                            max_age=30 * 24 * 3600)
        return a

    # -- the page -------------------------------------------------------------------------------------------------------
    for route, (name, mime) in STATIC.items():
        def page(name: str = name, mime: str = mime) -> Response:
            return Response(resources.files("axelrod_desk").joinpath("web", name).read_bytes(), media_type=mime)
        app.add_api_route(route, page, methods=["GET"], include_in_schema=False)

    # -- accounts -------------------------------------------------------------------------------------------------------
    @app.get("/api/setup")
    def setup_needed() -> dict:
        return {"needed": db.one("select count(*) n from accounts where admin = 1")["n"] == 0}

    @app.post("/api/setup")
    def setup(body: Credentials, response: Response) -> dict:
        if not setup_needed()["needed"]:
            raise PermissionError("the desk already has an admin; ask them for an account")
        return signed_in(response, accounts.create(db, body.email, body.name, body.password, admin=True))

    @app.post("/api/login")
    def login(body: Credentials, response: Response) -> dict:
        a = accounts.sign_in(db, body.email, body.password)
        if a is None:
            raise PermissionError("that email and password do not match an account", 401)
        return signed_in(response, a)

    @app.post("/api/logout")
    def logout(request: Request, response: Response) -> dict:
        accounts.revoke(db, request.cookies.get(COOKIE, ""))
        response.delete_cookie(COOKIE)
        return {"ok": True}

    @app.get("/api/me")
    def me(a: dict = Depends(person)) -> dict:
        return {**a, "reader": accounts.has_reader(db, a["id"])}

    @app.post("/api/me/reader-token")
    def reader_token(a: dict = Depends(person)) -> dict:
        return {"token": accounts.issue(db, a["id"], "reader")}

    @app.get("/api/accounts")
    def list_accounts(a: dict = Depends(admin)) -> list:
        return [accounts.public(x) for x in db.all("select * from accounts order by id")]

    @app.post("/api/accounts", status_code=201)
    def add_account(body: Credentials, a: dict = Depends(admin)) -> dict:
        return accounts.create(db, body.email, body.name, body.password, admin=body.admin)

    # -- catalog and library --------------------------------------------------------------------------------------------
    @app.get("/api/catalog")
    def catalog(a: dict = Depends(person)) -> dict:
        return {"companies": desk.catalog.company_list(), "groups": desk.catalog.groups, "classes": list(CLASSES)}

    @app.get("/api/documents")
    def documents(company: str = "", source_class: str = "", status: str = "", a: dict = Depends(person)) -> list:
        return desk.library.list(company=company, source_class=source_class, status=status)

    @app.post("/api/documents")
    def upload(files: list[UploadFile] = File(...), company: str = Form(""), source_class: str = Form(""),
               publisher: str = Form(""), published: str = Form(""), a: dict = Depends(person)) -> dict:
        blobs = [(Path(f.filename or "upload.bin").name, f.file.read()) for f in files]
        manifest = next((read_manifest(b.decode("utf-8", "replace")) for n, b in blobs if n == "MANIFEST.md"), None)
        added = [desk.library.add(b, n, account=a, company=company or None, source_class=source_class or None,
                                  publisher=publisher or None, published=published or None,
                                  entry=manifest.entry_for(n) if manifest else None)
                 for n, b in blobs if wanted(n)]
        groups = desk.library.link()
        skipped = [n for n, _ in blobs if not wanted(n) and not n.upper().endswith("MANIFEST.MD")]
        return {"added": [x.__dict__ for x in added], "skipped": skipped, "groups": groups}

    @app.get("/api/documents/{sha}")
    def document(sha: str, a: dict = Depends(person)) -> dict:
        return desk.document(sha)

    @app.patch("/api/documents/{sha}")
    def edit_document(sha: str, body: DocumentEdit, a: dict = Depends(person)) -> dict:
        return desk.library.edit(sha, **body.model_dump(exclude_none=True))

    @app.get("/api/documents/{sha}/file")
    def document_file(sha: str, a: dict = Depends(person)) -> FileResponse:
        d = desk.library.get(sha)
        if d is None:
            raise KeyError(sha)
        return FileResponse(desk.library.path_of(sha, d["ext"]), media_type=desk.library.mime_of(d), filename=d["filename"])

    @app.get("/api/documents/{sha}/pages/{n}")
    def document_page(sha: str, n: int, a: dict = Depends(person)) -> dict:
        texts = desk.library.pages(sha)
        if not 1 <= n <= len(texts):
            raise KeyError(f"no page {n}")
        return {"page": n, "pages": len(texts), "text": texts[n - 1]}

    @app.post("/api/documents/{sha}/reread")
    def reread(sha: str, a: dict = Depends(person)) -> dict:
        return desk.reread(sha)

    # -- facts ----------------------------------------------------------------------------------------------------------
    @app.get("/api/facts")
    def facts(company: str, conflicts: bool = False, a: dict = Depends(person)) -> list:
        return desk.facts(company, conflicts=conflicts)

    @app.post("/api/facts/review")
    def review(body: Review, a: dict = Depends(person)) -> dict:
        return desk.review(body.key, body.decision, a, body.note)

    # -- readers --------------------------------------------------------------------------------------------------------
    @app.get("/api/reader/status")
    def reader_status(a: dict = Depends(person)) -> dict:
        return desk.queue_status()

    @app.post("/api/reader/claim")
    def claim(body: Claim, a: dict = Depends(reader)) -> Response:
        job = desk.claim(a, body.reader)
        return Response(status_code=204) if job is None else JSONResponse(job)

    @app.post("/api/reader/readings/{reading_id}")
    def submit(reading_id: int, result: dict, a: dict = Depends(reader)) -> dict:
        return desk.submit(reading_id, result)

    @app.post("/api/reader/readings/{reading_id}/fail")
    def fail(reading_id: int, body: Failure, a: dict = Depends(reader)) -> dict:
        return desk.fail(reading_id, body.error)

    # -- world models and builds ----------------------------------------------------------------------------------------
    @app.get("/api/world-models")
    def world_models(a: dict = Depends(person)) -> list:
        return desk.world_models(a)

    @app.post("/api/world-models", status_code=201)
    def create_world_model(body: WorldModelBody, a: dict = Depends(person)) -> dict:
        return desk.save_world_model(a, body.model_dump())

    @app.put("/api/world-models/{wm_id}")
    def update_world_model(wm_id: int, body: WorldModelBody, a: dict = Depends(person)) -> dict:
        return desk.save_world_model(a, body.model_dump(), wm_id)

    @app.delete("/api/world-models/{wm_id}", status_code=204)
    def delete_world_model(wm_id: int, a: dict = Depends(person)) -> Response:
        desk.delete_world_model(wm_id, a)
        return Response(status_code=204)

    @app.post("/api/world-models/{wm_id}/builds", status_code=202)
    def start_build(wm_id: int, a: dict = Depends(person)) -> dict:
        return desk.start_build(wm_id, a)

    @app.get("/api/builds/{build_id}")
    def build(build_id: int, a: dict = Depends(person)) -> dict:
        return desk.build(build_id, a)

    @app.get("/api/builds/{build_id}/download")
    def download(build_id: int, a: dict = Depends(person)) -> FileResponse:
        b = desk.build(build_id, a)
        if b["status"] != "done":
            raise ValueError(f"build {build_id} is {b['status']}")
        return FileResponse(b["zip"], media_type="application/zip", filename=Path(b["zip"]).name)

    return app


__all__ = ["COOKIE", "create_app"]
