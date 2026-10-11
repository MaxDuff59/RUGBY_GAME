# Image de production : l'interface construite par Vite, servie par l'API FastAPI
# dans un seul conteneur (voir backend/api/main.py, `site`).
#
#   docker build -t rugby-manager .
#   docker run -p 8000:8000 -v rugby-data:/data rugby-manager
#
# Les parties et les comptes vivent dans /data : à monter sur un volume persistant.

# --- 1. Interface ----------------------------------------------------------------
FROM node:22-alpine AS frontend
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# --- 2. API + interface construite ------------------------------------------------
FROM python:3.12-slim AS app
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/app/.venv
WORKDIR /app

COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY backend/ ./
COPY --from=frontend /frontend/dist /app/static

ENV PATH="/app/.venv/bin:$PATH" \
    RUGBY_SAVES_DIR=/data/saves \
    RUGBY_STATIC_DIR=/app/static \
    RUGBY_COOKIE_SECURE=1 \
    PORT=8000
RUN mkdir -p /data/saves
VOLUME ["/data"]
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
  CMD python -c "import urllib.request,os;urllib.request.urlopen(f'http://127.0.0.1:{os.environ[\"PORT\"]}/api/health')" || exit 1

# --proxy-headers : derrière le reverse proxy de l'hébergeur (HTTPS, IP du client).
CMD ["sh", "-c", "uvicorn api.main:site --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*'"]
