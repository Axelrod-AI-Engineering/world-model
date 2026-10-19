"""docs/api/README.md's route reference, generated from the contract, docs/api/openapi.yaml.

The reference sits between `<!-- reference:start -->` and `<!-- reference:end -->` in docs/api/README.md: every
operation by tag (method, path, summary, scope, pinning, statuses), the error codes, and the schemas. The prose around
it is kept by hand; `--check` fails while the block is stale (tests/service/test_openapi_contract.py runs it).

    uv run python scripts/api/reference.py            # rewrite the block
    uv run python scripts/api/reference.py --check    # exit 1 if it is stale
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
SPEC = ROOT / "docs" / "api" / "openapi.yaml"
DOC = ROOT / "docs" / "api" / "README.md"
START, END = "<!-- reference:start -->", "<!-- reference:end -->"
METHODS = ("get", "post", "patch", "put", "delete")


def _cell(text: str) -> str:
    return " ".join(str(text).split()).replace("|", "\\|")


def render(spec: dict) -> str:
    """The reference block's body, in tag order."""
    params = spec["components"]["parameters"]
    by_tag: dict[str, list[tuple[str, str, dict]]] = {t["name"]: [] for t in spec["tags"]}
    for path, item in spec["paths"].items():
        for method in METHODS:
            if method in item:
                by_tag[item[method]["tags"][0]].append((method.upper(), path, item[method]))
    lines = [f"All {sum(len(v) for v in by_tag.values())} operations, from the contract "
             "([openapi.yaml](openapi.yaml)). Paths are under `/v1`; `{wm}` is `/world-models/{world_model_id}`.",
             ""]
    for tag in spec["tags"]:
        ops = by_tag[tag["name"]]
        lines += [f"### {tag['name']}", "", _cell(tag["description"]), "",
                  "| Route | What it does | Scope | Pinned | Answers |", "|---|---|---|---|---|"]
        for method, path, op in ops:
            names = {params[p["$ref"].rsplit("/", 1)[1]]["name"] for p in op.get("parameters", []) if "$ref" in p}
            pinned = "yes" if {"version", "as_of"} <= names else ""
            short = path.replace("/world-models/{world_model_id}", "{wm}")
            lines.append(f"| `{method} {short}` | {_cell(op['summary'])} | `{op['x-required-scope']}` | {pinned} | "
                         f"{', '.join(sorted(op['responses']))} |")
        lines.append("")
    codes = spec["components"]["schemas"]["ProblemCode"]["enum"]
    lines += ["### Errors", "", "Every failure is `application/problem+json` (RFC 9457): `type` "
              "(`https://docs.axelrod.ai/problems/{code}`), `title`, `status`, `detail`, `instance`, `code`, "
              "`request_id`, and `errors` (each invalid field).", "", "| Status | When |", "|---|---|"]
    for name, resp in spec["components"]["responses"].items():
        status = next(s for s, (n, _t) in _statuses(spec).items() if n == name)
        lines.append(f"| {status} | {_cell(resp['description'])} |")
    lines += ["", "Codes: " + ", ".join(f"`{c}`" for c in codes) + ".", "", "### Schemas", "",
              "| Schema | What it is |", "|---|---|"]
    for name, s in spec["components"]["schemas"].items():
        if name.endswith(("Response", "Page")):
            continue
        lines.append(f"| `{name}` | {_cell(s.get('description', ''))} |")
    return "\n".join(lines) + "\n"


def _statuses(spec: dict) -> dict[int, tuple[str, str]]:
    out = {}
    for item in spec["paths"].values():
        for method in METHODS:
            for status, resp in item.get(method, {}).get("responses", {}).items():
                if "$ref" in resp:
                    out[int(status)] = (resp["$ref"].rsplit("/", 1)[1], "")
    return out


def rewrite(doc: str, body: str) -> str:
    head, rest = doc.split(START, 1)
    _old, tail = rest.split(END, 1)
    return f"{head}{START}\n{body}{END}{tail}"


def main(argv: list[str]) -> int:
    spec = yaml.safe_load(SPEC.read_text())
    doc = DOC.read_text()
    new = rewrite(doc, render(spec))
    if "--check" in argv:
        if new != doc:
            print("docs/api/README.md's reference is stale: run uv run python scripts/api/reference.py")
            return 1
        return 0
    DOC.write_text(new)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
