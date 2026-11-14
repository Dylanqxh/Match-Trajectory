# syntax=docker/dockerfile:1.7

FROM node:22-bookworm-slim AS web-builder
WORKDIR /workspace
COPY package.json package-lock.json ./
RUN npm ci
COPY web ./web
RUN npm run build

FROM python:3.12-slim-bookworm AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONUTF8=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    MATCH_TRAJECTORY_FONT_PATH=/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc \
    PATH=/app/.venv/bin:$PATH

WORKDIR /app
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir uv==0.13.5

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev \
    && uv run playwright install --with-deps chromium \
    && rm -rf /root/.cache/uv

COPY app ./app
COPY skills ./skills
COPY --from=web-builder /workspace/web/dist ./web/dist

RUN mkdir -p /app/data
EXPOSE 18765
VOLUME ["/app/data"]
HEALTHCHECK --interval=15s --timeout=3s --start-period=20s --retries=4 \
    CMD curl --fail --silent http://127.0.0.1:18765/health || exit 1
ENTRYPOINT ["python", "-m", "app.cli"]
CMD ["--host", "0.0.0.0", "--port", "18765", "--no-browser", "--data-dir", "/app/data"]
