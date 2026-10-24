# The build context is the repository root (a uv workspace: ingestion/ and world_model/). Only the service is built: the
# world model member, with ingestion pulled in as its workspace dependency.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
ENV PATH="/app/.venv/bin:$PATH"
WORKDIR /app

RUN pip install --no-cache-dir uv==0.9.2
COPY pyproject.toml uv.lock README.md ./
COPY ingestion/pyproject.toml ./ingestion/pyproject.toml
COPY ingestion/src ./ingestion/src
COPY world_model/pyproject.toml ./world_model/pyproject.toml
COPY world_model/src ./world_model/src
# The semantic extra (fastembed: bge-small on ONNX, CPU) serves semantic search; it forwards to axelrod-ingest[semantic].
# Its model is cached on the volume. Only the in-process lakehouse uses it: with WORLD_MODEL_INGEST_URL set the ingestion
# service is the only embedder, and this image loads no model and downloads none (docs/deployment.md#three-services).
RUN uv sync --frozen --no-dev --no-editable --package axelrod-world-model --extra semantic
# The package is installed, not editable, so it finds the files it serves through AXELROD_ROOT (axelrod_wm/paths.py):
# <root>/configs (stage settings) and <root>/world_model/{examples,taxonomy,configs,web}.
COPY configs ./configs
COPY world_model/examples ./world_model/examples
COPY world_model/taxonomy ./world_model/taxonomy
COPY world_model/configs ./world_model/configs
COPY world_model/web ./world_model/web
COPY .railway/start-railway.sh ./.railway/start-railway.sh
ENV AXELROD_ROOT=/app
ENV WORLD_MODEL_LAKE_DIR=/app/var/lake WORLD_MODEL_EMBED_CACHE=/app/var/models
CMD ["sh", ".railway/start-railway.sh"]
