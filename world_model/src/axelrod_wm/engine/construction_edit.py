"""Exact, minimal edits of one interaction in a world's construction YAML (Oct 17).

A construction file is written by hand: comments, flow mappings, and line breaks carry meaning for its readers. An
edit therefore changes only the text of the keys it must change, inside the one interaction's entry, and never dumps
the file. Entries may be block mappings (`- id: x` then `key: value` lines) or flow mappings (`- {id: x, ...}`, over
one or more lines), and their nested `transition` and `evidence` may be either.

Every edit is checked: the edited file is parsed and must equal the original with exactly that interaction replaced
by its intended new value. If not (an unusual layout), nothing is written and the error says to edit by hand.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from axelrod_wm.model.calibrate import LinkCalibration, calibrated_entry, new_state


class EditError(ValueError):
    """An edit that cannot be made exactly; the file is left as it was."""


_KEY = re.compile(r"([A-Za-z_][\w-]*):(?=\s|$)")
_PLAIN = re.compile(r"[A-Za-z0-9_.\-]+")


def scalar(v: float | str) -> str:
    """A YAML scalar's text, safe in flow and block context: a number to four decimals, a plain word when it reads
    back as itself, else a quoted string."""
    if isinstance(v, float):
        return f"{v:.4f}".rstrip("0").rstrip(".")
    return v if _PLAIN.fullmatch(v) and yaml.safe_load(v) == v else json.dumps(v)


def flow(v: object) -> str:
    """A value as YAML flow text (a mapping, a list, or a scalar), for keys an edit replaces whole."""
    if isinstance(v, dict):
        return "{" + ", ".join(f"{k}: {flow(x)}" for k, x in v.items()) + "}"
    if isinstance(v, list):
        return "[" + ", ".join(flow(x) for x in v) + "]"
    if isinstance(v, bool):
        return "true" if v else "false"
    if v is None:
        return "null"
    return scalar(float(v)) if isinstance(v, int | float) else scalar(str(v))


def _skip_quote(text: str, j: int) -> int:
    q, k = text[j], j + 1
    while k < len(text):
        if q == '"' and text[k] == "\\":
            k += 2
            continue
        if text[k] == q:
            if q == "'" and text[k + 1:k + 2] == "'":
                k += 2
                continue
            return k + 1
        k += 1
    raise EditError("an unterminated quoted string")


def _scan_value(text: str, j: int, stop: str) -> int:
    """The end of a flow value starting at j: the first character of `stop` at depth zero."""
    while j < len(text):
        c = text[j]
        if c in "\"'" and text[:j].rstrip()[-1:] in ("{", "[", ",", ":"):    # a quote only opens a scalar
            j = _skip_quote(text, j)
        elif c in "{[":
            j = _close(text, j) + 1
        elif c in stop:
            return j
        elif c == "#" and text[j - 1] in " \t\n":
            j = text.index("\n", j)
        else:
            j += 1
    raise EditError("an unterminated flow collection")


def _close(text: str, i: int) -> int:
    """The index of the bracket closing the one at i."""
    return _scan_value(text, i + 1, "}" if text[i] == "{" else "]")


@dataclass
class Entry:
    key: str
    start: int                       # where the entry (its key) starts
    value_start: int
    value_end: int
    end: int                         # block: the end of its last line, newline included; flow: value_end


class Edits:
    """Replacements of the original text, applied from the end; insertions at one place keep their order."""

    def __init__(self) -> None:
        self.items: list[tuple[int, int, int, str]] = []

    def add(self, start: int, end: int, text: str) -> None:
        self.items.append((start, end, len(self.items), text))

    def apply(self, text: str) -> str:
        for start, end, _, new in sorted(self.items, reverse=True):
            text = text[:start] + new + text[end:]
        return text


class FlowMap:
    def __init__(self, text: str, open_at: int) -> None:
        self.text, self.open, self.close = text, open_at, _close(text, open_at)
        self.entries: list[Entry] = []
        self.added = False               # a key was inserted into an empty mapping
        j = open_at + 1
        while True:
            while text[j] in " \t\r\n,":
                j += 1
            if text[j] == "#":
                j = text.index("\n", j)
                continue
            if j >= self.close:
                break
            m = _KEY.match(text, j)
            if m is None:
                raise EditError(f"an unexpected flow key at {text[j:j + 20]!r}")
            vs = m.end()
            while text[vs] in " \t\r\n":
                vs += 1
            ve = _scan_value(text, vs, ",}")
            ve_strip = ve
            while text[ve_strip - 1] in " \t\r\n":
                ve_strip -= 1
            self.entries.append(Entry(m.group(1), j, vs, ve_strip, ve_strip))
            j = ve

    def get(self, key: str) -> Entry | None:
        return next((e for e in self.entries if e.key == key), None)

    def set(self, ed: Edits, key: str, value: str, after: str | None = None) -> None:
        e = self.get(key)
        if e is not None:
            ed.add(e.value_start, e.value_end, value)
            return
        anchor = (self.get(after) if after else None) or (self.entries[-1] if self.entries else None)
        if anchor is None:
            ed.add(self.open + 1, self.open + 1, f"{', ' if self.added else ''}{key}: {value}")
            self.added = True
        else:
            ed.add(anchor.end, anchor.end, f", {key}: {value}")

    def delete(self, ed: Edits, key: str) -> None:
        """Remove an entry that is not the first, with one comma, keeping the line breaks around it."""
        e = self.get(key)
        k = self.entries.index(e)
        nxt = self.entries[k + 1] if k + 1 < len(self.entries) else None
        if nxt is None or "\n" in self.text[e.end:nxt.start]:
            ed.add(self.entries[k - 1].end, e.end, "")
        else:
            ed.add(e.start, nxt.start, "")

    def rename(self, ed: Edits, key: str, new_key: str, value: str) -> None:
        e = self.get(key)
        ed.add(e.start, e.value_end, f"{new_key}: {value}")


class BlockMap:
    """A block mapping: the keys at `indent` on the lines from `start` (the first key may follow a list dash)."""

    def __init__(self, text: str, start: int, indent: int, first_key_at: int | None = None) -> None:
        self.text, self.indent = text, indent
        self.entries: list[Entry] = []
        lines: list[tuple[int, int, int]] = []         # (line start, key offset, line end incl. newline)
        pos, first = start, True
        while pos < len(text):
            nl = text.find("\n", pos)
            end = len(text) if nl < 0 else nl + 1
            body = text[pos:end].rstrip("\r\n")
            stripped = body.lstrip(" ")
            ind = len(body) - len(stripped)
            if first and first_key_at is not None:
                lines.append((pos, first_key_at, end))
            elif not stripped or stripped.startswith("#"):
                lines.append((pos, -1, end))
            elif ind < indent:
                break
            else:                        # deeper lines, and an indentless list under a key, continue the key
                lines.append((pos, pos + ind if ind == indent and not stripped.startswith("- ") else -2, end))
            first = False
            pos = end
        self.end = pos
        cur: Entry | None = None
        for ls, ko, le in lines:
            if ko >= 0:
                m = _KEY.match(text, ko)
                if m is None:
                    raise EditError(f"an unexpected line {text[ls:le].strip()!r}")
                vs = m.end()
                while vs < le and text[vs] in " \t":
                    vs += 1
                cur = Entry(m.group(1), ko, vs, le, le)
                self.entries.append(cur)
            elif ko == -2:
                cur.end = cur.value_end = le                    # a continuation line belongs to the current key
        for e in self.entries:                                  # a value ends before its trailing newline or comment
            c = text[e.value_start]
            if c in "{[":
                e.value_end = _close(text, e.value_start) + 1
            elif c in "\"'":
                e.value_end = _skip_quote(text, e.value_start)
            else:
                v = text[e.value_start:e.value_end].rstrip("\r\n")
                if "\n" not in v:
                    v = re.sub(r"\s+#.*$", "", v)
                e.value_end = e.value_start + len(v.rstrip())

    def get(self, key: str) -> Entry | None:
        return next((e for e in self.entries if e.key == key), None)

    def set(self, ed: Edits, key: str, value: str, after: str | None = None) -> None:
        e = self.get(key)
        if e is not None:
            if self.text[e.value_start] == "\n":                # a nested block value becomes inline
                ed.add(e.value_start, e.end, f" {value}\n")
            else:
                ed.add(e.value_start, e.value_end, value)
            return
        anchor = self.get(after) if after else None
        at = anchor.end if anchor else self.entries[-1].end
        line = " " * self.indent + f"{key}: {value}\n"
        if not self.text[:at].endswith("\n"):
            line = "\n" + line.rstrip("\n")
        ed.add(at, at, line)

    def delete(self, ed: Edits, key: str) -> None:
        """Remove an entry that is not the first (its own lines)."""
        e = self.get(key)
        ed.add(self.text.rfind("\n", 0, e.start) + 1, e.end, "")

    def rename(self, ed: Edits, key: str, new_key: str, value: str) -> None:
        e = self.get(key)
        ed.add(e.start, e.value_end, f"{new_key}: {value}")


def child(node: FlowMap | BlockMap, key: str) -> FlowMap | BlockMap | None:
    """The mapping under `key`, flow or block, or None when the key is absent."""
    e = node.get(key)
    if e is None:
        return None
    text = node.text
    if text[e.value_start] == "{":
        return FlowMap(text, e.value_start)
    if text[e.value_start] != "\n":
        raise EditError(f"{key!r} is not a mapping")
    first = e.value_start + 1
    while text[first:].lstrip(" ").startswith(("#", "\n")):
        first = text.index("\n", first) + 1
    body = text[first:]
    return BlockMap(text, first, len(body) - len(body.lstrip(" ")))


def append_to_list(node: FlowMap | BlockMap, ed: Edits, key: str, item: str) -> None:
    e = node.get(key)
    if e is None:
        node.set(ed, key, f"[{item}]")
        return
    text = node.text
    if text[e.value_start] == "[":
        close = _close(text, e.value_start)
        ed.add(close, close, item if not text[e.value_start + 1:close].strip() else f", {item}")
        return
    if text[e.value_start] != "\n":
        raise EditError(f"{key!r} is not a list")
    first = re.compile(r"^([ \t]*)- ", re.M).search(text, e.value_start)
    line = f"{first.group(1)}- {item}\n"
    ed.add(e.end, e.end, line if text[:e.end].endswith("\n") else "\n" + line.rstrip("\n"))


def find_interaction(text: str, interaction_id: str) -> FlowMap | BlockMap:
    """The entry of `interaction_id` in the file's top-level `interactions:` list."""
    m = re.search(r"^interactions:[ \t]*(#.*)?$", text, re.M)
    if m is None:
        raise EditError("the file has no interactions")
    end = re.search(r"^[^\s#-]", text[m.end():], re.M)
    section = (m.end(), m.end() + end.start() if end else len(text))
    q = re.escape(interaction_id)
    body = text[:section[1]]
    hit = re.compile(rf"^[ \t]*-[ \t]+id:[ \t]*([\"']?){q}\1[ \t]*(#.*)?$", re.M).search(body, section[0])
    if hit:
        key_at = text.index("id:", hit.start())
        return BlockMap(text, hit.start(), key_at - hit.start(), first_key_at=key_at)
    hit = re.compile(rf"^[ \t]*-[ \t]+\{{\s*id:[ \t]*([\"']?){q}\1\s*[,}}]", re.M).search(body, section[0])
    if hit:
        return FlowMap(text, text.index("{", hit.start()))
    raise EditError(f"no entry for {interaction_id} in the file")


def edit_calibration(text: str, cal: LinkCalibration) -> str:
    """`text` with the interaction calibrated (see model/calibrate.py), changed only where it must be."""
    node = find_interaction(text, cal.interaction_id)
    doc = yaml.safe_load(text)
    entries = doc["interactions"]
    k = next(n for n, x in enumerate(entries) if x.get("id") == cal.interaction_id)
    want = calibrated_entry(entries[k], cal)
    ed = Edits()
    effect = f"{{mu: {scalar(cal.effect)}, sigma: {scalar(cal.sigma)}}}"
    if cal.asymmetry is not None:
        # the sizes move into state.asymmetry: the link keeps no effect of its own
        for key in ("effect", "calibration"):
            if node.get(key) is not None:
                node.delete(ed, key)
    elif node.get("effect") is not None:
        node.set(ed, "effect", effect)
        if node.get("calibration") is not None:
            node.delete(ed, "calibration")
    elif node.get("calibration") is not None:
        node.rename(ed, "calibration", "effect", effect)
    else:
        node.set(ed, "effect", effect, after="label")
    state = new_state(entries[k], cal)
    if state is not None:
        node.set(ed, "state", flow(state), after="label")
    tr = child(node, "transition")
    ev = child(tr, "evidence")
    if ev is None:
        direction = f"direction: {scalar(cal.support)}, " if cal.flip_reason is not None else ""
        tr.set(ed, "evidence", f"{{{direction}magnitude: {scalar(cal.support)}, sources: [{scalar(cal.evidence)}]}}")
    else:
        ev.set(ed, "magnitude", scalar(cal.support))
        if cal.evidence not in (entries[k]["transition"].get("evidence") or {}).get("sources", []):
            append_to_list(ev, ed, "sources", scalar(cal.evidence))
        if cal.flip_reason is not None:
            ev.set(ed, "direction", scalar(cal.support))
    if cal.flip_reason is not None:
        tr.set(ed, "sign", json.dumps(cal.sign), after="mechanism")
    if cal.flip_reason is not None or cal.scenario_note is not None:
        node.set(ed, "note", json.dumps(want["note"]), after="label")
    new = ed.apply(text)
    expected = {**doc, "interactions": [*entries[:k], want, *entries[k + 1:]]}
    if yaml.safe_load(new) != expected:
        raise EditError(f"the edit of {cal.interaction_id} would change more than the link; edit it by hand")
    return new


def interaction_file(world: Path, interaction_id: str) -> Path:
    """The construction file that defines `interaction_id`: construction/*.yaml, else interactions.yaml."""
    for f in [*sorted((world / "construction").glob("*.yaml")), world / "interactions.yaml"]:
        if f.is_file():
            doc = yaml.safe_load(f.read_text()) or {}
            if any(x.get("id") == interaction_id for x in doc.get("interactions", []) or []):
                return f
    raise EditError(f"no construction file in {world} defines {interaction_id} (a kind's default link is written "
                    "out in a construction file before it is calibrated)")


__all__ = ["EditError", "edit_calibration", "find_interaction", "flow", "interaction_file", "scalar"]
