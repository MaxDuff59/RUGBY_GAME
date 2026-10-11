# Image de production de l'API (Railway, Fly...). L'interface est déployée à part
# (Vercel, voir frontend/vercel.json) et relaie /api/* vers cette API.
#
#   docker build -t rugby-api .
#   docker run -p 8000:8000 -v rugby-data:/data rugby-api
#
# Les parties, les comptes et les photos vivent dans /data : à monter sur un volume.

FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/app/.venv
WORKDIR /app

COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY backend/ ./

ENV PATH="/app/.venv/bin:$PATH" \
    RUGBY_SAVES_DIR=/data/saves \
    RUGBY_COOKIE_SECURE=1 \
    PORT=8000
RUN mkdir -p /data/saves
VOLUME ["/data"]
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
  CMD python -c "import urllib.request,os;urllib.request.urlopen(f'http://127.0.0.1:{os.environ[\"PORT\"]}/health')" || exit 1

# --proxy-headers : derrière le reverse proxy de l'hébergeur (HTTPS, IP du client).
CMD ["sh", "-c", "uvicorn api.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*'"]
