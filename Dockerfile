FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
ENV PATH="/app/.venv/bin:$PATH"
WORKDIR /app

RUN pip install --no-cache-dir uv==0.9.2
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
# The semantic extra (fastembed: bge-small on ONNX, CPU) serves semantic search; its model is cached on the volume.
RUN uv sync --frozen --no-dev --no-editable --extra semantic
COPY configs ./configs
COPY world_model ./world_model
COPY web ./web
COPY scripts/start-railway.sh ./scripts/start-railway.sh
# Keep source available: the app resolves bundled world_model and web files relative to src.
ENV PYTHONPATH=/app/src
ENV WORLD_MODEL_LAKE_DIR=/app/var/lake WORLD_MODEL_EMBED_CACHE=/app/var/models
CMD ["sh", "scripts/start-railway.sh"]
