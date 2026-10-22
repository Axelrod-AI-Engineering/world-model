"""RFC 9457 problem details, the headers every v1 answer carries, and the route class that applies both.

Every failure is `application/problem+json`: `type` (https://docs.axelrod.ai/problems/{code}), `title`, `status`,
`detail`, `instance` (the path), `code` (stable, from world_model/docs/api/openapi.yaml's ProblemCode), `request_id`, and `errors`
(each invalid field). Every answer carries `X-Request-Id` (the caller's, when it sent a usable one),
`X-Axelrod-API-Version: 1`, and the caller's `traceparent`; an answer with an ETag that matches `If-None-Match` is a
304.
"""

from __future__ import annotations

import json
import re
import secrets
from collections.abc import Callable
from typing import Any

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from fastapi.routing import APIRoute
from pydantic import ValidationError

API_VERSION = "1"
PROBLEM_BASE = "https://docs.axelrod.ai/problems/"
_RID = re.compile(r"[A-Za-z0-9._:-]{1,128}")

# code -> (status, title)
CODES: dict[str, tuple[int, str]] = {
    "invalid_request": (422, "Invalid request"), "invalid_json": (400, "Invalid JSON"),
    "invalid_cursor": (400, "Invalid cursor"), "authentication_required": (401, "Authentication required"),
    "invalid_token": (401, "Invalid credential"), "insufficient_scope": (403, "Insufficient scope"),
    "human_approval_required": (403, "A person must decide"),
    "internal_only": (403, "Internal staff only"), "compartment_not_found": (404, "Compartment not found"), "not_found": (404, "Not found"),
    "world_model_not_found": (404, "World model not found"), "version_not_found": (404, "Version not found"),
    "entity_not_found": (404, "Entity not found"), "attribute_not_found": (404, "Attribute not found"),
    "relationship_not_found": (404, "Relationship not found"), "evidence_not_found": (404, "Evidence not found"),
    "composition_not_found": (404, "Composition not found"), "path_not_found": (404, "Path not found"),
    "event_not_found": (404, "Event not found"), "document_not_found": (404, "Document not found"),
    "chunk_not_found": (404, "Chunk not found"), "file_missing": (404, "File missing"),
    "bundle_not_found": (404, "Bundle not found"), "change_not_found": (404, "Change not found"),
    "thesis_not_found": (404, "Thesis not found"), "simulation_not_found": (404, "Simulation not found"),
    "concept_not_found": (404, "Concept not found"), "group_not_found": (404, "Group not found"),
    "job_not_found": (404, "Job not found"), "conflict": (409, "Conflict"),
    "update_in_progress": (409, "Update in progress"), "already_decided": (409, "Already decided"),
    "not_parsed": (409, "Not parsed"), "version_moved": (412, "The model has moved"),
    "payload_too_large": (413, "Payload too large"), "too_many_files": (413, "Too many files"),
    "unsupported_media_type": (415, "Unsupported media type"),
    "idempotency_key_reused": (422, "Idempotency key reused"), "note_required": (422, "A reason is required"),
    "question_not_understood": (422, "Question not understood"), "thesis_unbound": (422, "Thesis unbound"),
    "precondition_required": (428, "If-Match required"), "issuer_unavailable": (503, "Issuer unavailable"),
}
BY_STATUS = {400: "invalid_request", 401: "authentication_required", 403: "insufficient_scope", 404: "not_found",
             405: "not_found", 409: "conflict", 413: "payload_too_large", 415: "unsupported_media_type"}


class ApiError(Exception):
    """A failure with a code; its status comes from CODES."""

    def __init__(self, code: str, detail: str, *, errors: list[dict] | None = None,
                 headers: dict[str, str] | None = None) -> None:
        super().__init__(detail)
        self.code, self.detail, self.errors, self.headers = code, detail, errors, headers or {}
        self.status = CODES[code][0]


def request_id_of(headers: dict) -> str:
    """The caller's X-Request-Id when usable, else a new one."""
    raw = headers.get(b"x-request-id", headers.get("x-request-id", b""))
    rid = raw.decode("latin-1") if isinstance(raw, bytes) else str(raw)
    return rid if _RID.fullmatch(rid) else f"req_{secrets.token_hex(8)}"


def problem_body(status: int, code: str, detail: str, instance: str, request_id: str,
                 errors: list[dict] | None = None) -> dict:
    body = {"type": PROBLEM_BASE + code, "title": CODES[code][1], "status": status, "detail": detail,
            "instance": instance, "code": code, "request_id": request_id}
    if errors is not None:
        body["errors"] = errors
    return body


def _field_errors(raw: list[dict]) -> list[dict]:
    return [{"location": [str(x) if not isinstance(x, int) else x for x in e.get("loc", [])],
             "message": str(e.get("msg", "")), "type": str(e.get("type", ""))} for e in raw]


def problem(request: Request, err: ApiError) -> JSONResponse:
    rid = request.state.request_id
    return JSONResponse(problem_body(err.status, err.code, err.detail, request.url.path, rid, err.errors),
                        status_code=err.status, media_type="application/problem+json",
                        headers={**err.headers, **standard_headers(request)})


def standard_headers(request: Request) -> dict[str, str]:
    out = {"X-Request-Id": request.state.request_id, "X-Axelrod-API-Version": API_VERSION}
    trace = request.headers.get("traceparent")
    if trace:
        out["traceparent"] = trace
    return out


def as_api_error(exc: Exception) -> ApiError | None:
    """The problem an exception from a handler stands for, or None for one that is a bug."""
    from axelrod_wm.control.controller import ControllerError
    from axelrod_wm.inference.task import UnboundThesis
    from axelrod_wm.repo.snapshots import RestoreError

    if isinstance(exc, ApiError):
        return exc
    if isinstance(exc, RequestValidationError):
        return ApiError("invalid_request", "the request is not valid",
                        errors=_field_errors(json.loads(json.dumps(exc.errors(), default=str))))
    if isinstance(exc, ValidationError):
        return ApiError("invalid_request", "the request is not valid", errors=_field_errors(json.loads(exc.json())))
    if isinstance(exc, HTTPException):
        return ApiError(BY_STATUS.get(exc.status_code, "invalid_request"), "the request could not be processed")
    if isinstance(exc, UnboundThesis):
        return ApiError("thesis_unbound", "the thesis names ends the model cannot bind")
    if isinstance(exc, ControllerError):
        return ApiError("conflict", "the request conflicts with the current state")
    if isinstance(exc, RestoreError):
        return ApiError("version_not_found", "the requested version was not found")
    if isinstance(exc, KeyError):
        return ApiError("not_found", "not found")
    if isinstance(exc, ValueError):
        return ApiError("invalid_request", "the request is not valid")
    return None


class V1Route(APIRoute):
    """Every v1 route answers failures as problems and carries the standard headers; a matching If-None-Match is
    a 304."""

    def get_route_handler(self) -> Callable:
        handler = super().get_route_handler()

        async def wrapped(request: Request) -> Response:
            request.state.request_id = request_id_of(dict(request.headers))
            try:
                resp = await handler(request)
            except Exception as exc:
                err = as_api_error(exc)
                if err is None:
                    raise
                return problem(request, err)
            etag = resp.headers.get("etag")
            if etag and request.method == "GET" and request.headers.get("if-none-match") == etag:
                resp = Response(status_code=304, headers={"ETag": etag})
            resp.headers.update(standard_headers(request))
            return resp

        return wrapped


def not_found_handler(original: Callable) -> Callable:
    """An unknown /v1 path (or method) as a problem; every other path as the app already answers it."""

    async def handle(request: Request, exc: Any) -> Response:
        if not request.url.path.startswith("/v1"):
            return await original(request, exc)
        request.state.request_id = request_id_of(dict(request.headers))
        code = "not_found" if exc.status_code == 404 else BY_STATUS.get(exc.status_code, "invalid_request")
        return problem(request, ApiError(code, f"{request.method} {request.url.path}: {exc.detail}"))

    return handle
