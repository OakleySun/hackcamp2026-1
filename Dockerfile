FROM oven/bun:1 AS bun
FROM node:22-bookworm-slim AS web
COPY --from=bun /usr/local/bin/bun /usr/local/bin/bun
WORKDIR /build/frontend
COPY frontend/package.json frontend/bun.lock frontend/bunfig.toml ./
RUN bun install --frozen-lockfile
COPY frontend/ ./
RUN QUAD_MARITIME_BUILD=1 VITE_API_URL=same-origin bun run build

FROM python:3.12-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates libstdc++6 \
    && rm -rf /var/lib/apt/lists/*
COPY --from=web /usr/local/bin/node /usr/local/bin/node
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY app/ app/
COPY fixtures/ fixtures/
COPY scripts/dbx_worker.py scripts/
COPY maritime/start_quad.py maritime/
COPY --from=web /build/frontend/.output/ web/
ENV APP_MODE=production DATABASE_PATH=/data/quad/club_alerts.db GEMINI_TOPIC_ENRICHMENT=true PYTHONUNBUFFERED=1
CMD ["python", "maritime/start_quad.py"]
