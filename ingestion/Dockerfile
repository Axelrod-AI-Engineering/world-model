# The ingestion service (axelrod-ingest): parses, chunks, embeds, recognizes, extracts, and bundles; reads and writes the lake
# through the data service (WORLD_MODEL_LAKE_URL, WORLD_MODEL_LAKE_TOKEN) and holds no state. The build context is the
# repository root (a uv workspace). Needs INGEST_TOKEN (the service refuses to start without it).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
ENV PATH="/app/.venv/bin:$PATH"
WORKDIR /app

# OCR for scanned PDFs: English (with the engine) and the Chinese and Korean data the corpora need
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-chi-sim tesseract-ocr-chi-tra tesseract-ocr-kor \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir uv==0.9.2
COPY pyproject.toml uv.lock README.md ./
COPY ingestion/pyproject.toml ./ingestion/pyproject.toml
COPY ingestion/src ./ingestion/src
# the workspace names both members, so uv reads the second one's metadata (none of its code is installed)
COPY world_model/pyproject.toml ./world_model/pyproject.toml
RUN uv sync --frozen --no-dev --no-editable --package axelrod-ingest --extra semantic --extra service
# The embedding model (bge-small on ONNX, CPU) is fetched once at build, so a restart never downloads it, and it sits under
# /tmp/models: this service is the only one that holds the weights, and they are a cache, not state to keep.
ENV WORLD_MODEL_EMBED_CACHE=/tmp/models AXELROD_OCR_LANG=eng+chi_sim+chi_tra+kor
RUN python -c "from axelrod_ingest.lake.embed import FastEmbedder; FastEmbedder(cache_dir='/tmp/models')"
CMD ["axelrod-ingest"]
