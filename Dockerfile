FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
ENV PATH="/app/.venv/bin:$PATH"
WORKDIR /app

RUN pip install --no-cache-dir uv==0.9.2
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN uv sync --frozen --no-dev --no-editable
COPY configs ./configs
COPY data ./data
COPY web ./web
COPY scripts/start-railway.sh ./scripts/start-railway.sh
# Keep source available: the app resolves bundled data/web relative to src.
ENV PYTHONPATH=/app/src
CMD ["sh", "scripts/start-railway.sh"]
