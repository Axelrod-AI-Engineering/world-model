"""Ingest a pack of documents (a folder with a MANIFEST.md) into an isolated lake and report what happened to every file.

    uv run python ingestion/scripts/ingest_pack.py "data/sources/sally/byd" --world-view data/work/sally/world_view_packs.json \\
        --lake-dir data/work/sally/lake_2026-10-22 --report data/work/sally/lake_2026-10-22/byd_report.json \\
        --twice data/work/sally/lake_2026-10-22_rerun/byd

Everything is in axelrod_ingest.pack; this file only runs it.
"""

import sys

from axelrod_ingest.pack import main

if __name__ == "__main__":
    sys.exit(main())
