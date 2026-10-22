"""OCR (Oct 22): the text of a PDF page that has no text layer, deterministically, and only when an engine is there.

A scanned deck is a PDF whose pages are pictures: the text layer is empty, and without OCR the document parses to
nothing. `parse` finds those pages (a page with drawn content and no text) and, when an `Ocr` is given, reads them here;
when none is given or the engine is missing, the document is marked `needs_ocr` with the pages, never left silently empty.

Deterministic by construction:

- **A fixed configuration.** The page is drawn in grayscale at 200 dpi, written as a PGM (no image library: a header and
  the pixel rows), and read by `tesseract --psm 3 --oem 1 -l <lang> --dpi 200` with one thread (OMP_THREAD_LIMIT=1) and
  nothing else from the environment that changes a result. The engine's name, version, and this configuration are recorded in
  the document's metadata.
- **Cached by content.** A page's text is kept under the hash of (engine, version, configuration, the document's SHA-256,
  the page), so reading the same file again never runs the engine again and gives the same text. Nothing about
  the cache (a hit, a miss) enters a document's metadata or its bundle.

The engine is optional: `ocr_from_env` returns None when OCR is off (`AXELROD_OCR=off`) or no `tesseract` is on the
path (or at `AXELROD_TESSERACT`), and the pipeline then reports `needs_ocr`.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

DPI = 200
PSM, OEM = 3, 1
TIMEOUT_SECONDS = 600
DEFAULT_LANG = "eng"


class OcrError(RuntimeError):
    """The engine could not read a page (it failed, timed out, or answered with an error)."""


@dataclass(frozen=True)
class Tesseract:
    command: str
    version: str
    lang: str = DEFAULT_LANG
    name: str = "tesseract"

    @property
    def config(self) -> str:
        return f"lang={self.lang} psm={PSM} oem={OEM} dpi={DPI} threads=1"

    def read(self, pgm: bytes) -> str:
        """The text of one page image (a PGM)."""
        argv = [self.command, "stdin", "stdout", "-l", self.lang, "--psm", str(PSM), "--oem", str(OEM), "--dpi", str(DPI)]
        env = {"PATH": os.environ.get("PATH", ""), "OMP_THREAD_LIMIT": "1", "LC_ALL": "C",
               **({"TESSDATA_PREFIX": os.environ["TESSDATA_PREFIX"]} if "TESSDATA_PREFIX" in os.environ else {})}
        try:
            done = subprocess.run(argv, input=pgm, capture_output=True, env=env, timeout=TIMEOUT_SECONDS, check=False)
        except (OSError, subprocess.TimeoutExpired) as err:
            raise OcrError(f"{self.name} could not run: {err}") from err
        if done.returncode != 0:
            raise OcrError(f"{self.name} failed ({done.returncode}): {done.stderr.decode('utf-8', 'replace')[:200]}")
        return done.stdout.decode("utf-8", "replace")


def find_tesseract(env: Mapping[str, str] | None = None) -> Tesseract | None:
    """The `tesseract` binary (AXELROD_TESSERACT, else the path) with its version, or None when it is missing or does not
    answer `--version`."""
    env = os.environ if env is None else env
    command = env.get("AXELROD_TESSERACT") or shutil.which("tesseract")
    if not command:
        return None
    try:
        done = subprocess.run([command, "--version"], capture_output=True, timeout=30, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    # "tesseract 5.5.1" on the first line (older builds print it on stderr)
    first = (done.stdout or done.stderr).decode("utf-8", "replace").strip().splitlines()
    parts = first[0].split() if first and done.returncode == 0 else []
    return Tesseract(command, parts[1], env.get("AXELROD_OCR_LANG") or DEFAULT_LANG) if len(parts) >= 2 else None


class Ocr:
    """An engine and a cache of page texts."""

    def __init__(self, engine: Tesseract, cache_dir: Path | None = None) -> None:
        self.engine = engine
        self.cache_dir = cache_dir

    @property
    def meta(self) -> dict[str, str]:
        """What a document records of its OCR: the engine, its version, and the configuration."""
        return {"engine": self.engine.name, "version": self.engine.version, "config": self.engine.config}

    def key(self, doc_sha: str, page: int) -> str:
        e = self.engine
        return hashlib.sha256(f"{e.name}|{e.version}|{e.config}|{doc_sha}|{page}".encode()).hexdigest()

    def page_text(self, doc_sha: str, page: int, image: Callable[[], bytes]) -> str:
        """The page's text: from the cache, else from the engine (the image is drawn only then), then cached."""
        path = self.cache_dir / self.key(doc_sha, page)[:2] / f"{self.key(doc_sha, page)}.txt" if self.cache_dir else None
        if path is not None and path.exists():
            return path.read_text(encoding="utf-8")
        text = self.engine.read(image())
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_text(text, encoding="utf-8")
            tmp.replace(path)                                 # a reader never sees half a page
        return text


def ocr_from_env(env: Mapping[str, str] | None = None) -> Ocr | None:
    """OCR as the environment asks: None when `AXELROD_OCR` is "off" or no engine is found. The cache is
    AXELROD_OCR_CACHE, else an `ocr` folder in the lake (WORLD_MODEL_LAKE_DIR), else no cache."""
    env = os.environ if env is None else env
    engine = None if env.get("AXELROD_OCR", "auto").lower() == "off" else find_tesseract(env)
    if engine is None:
        return None
    where = env.get("AXELROD_OCR_CACHE") or (str(Path(env["WORLD_MODEL_LAKE_DIR"]) / "ocr") if env.get("WORLD_MODEL_LAKE_DIR") else "")
    return Ocr(engine, Path(where) if where else None)


def pgm_of(width: int, height: int, stride: int, pixels: bytes) -> bytes:
    """A binary graymap (P5) from 8-bit gray rows of `stride` bytes each (the rows' padding dropped)."""
    rows = b"".join(pixels[r * stride:r * stride + width] for r in range(height))
    return b"P5\n%d %d\n255\n" % (width, height) + rows
