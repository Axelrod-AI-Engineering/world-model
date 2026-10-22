"""Ingest a pack of documents (a folder with a MANIFEST.md) into an isolated lake and report what happened to every file.

    uv run python ingestion/scripts/ingest_pack.py data/sources/<client>/<pack> --world-view data/work/<client>/world_view.json \\
        --lake-dir data/work/<client>/lake_<date> --tenant <pack> --report data/work/<client>/lake_<date>/<pack>.json \\
        --twice data/work/<client>/lake_<date>_rerun

Everything is in axelrod_ingest.pack; this file only runs it.
"""

import sys

from axelrod_ingest.pack import main

if __name__ == "__main__":
    sys.exit(main())
