# syntax=docker/dockerfile:1

# uv binary from the official image (pinned to the version used in development)
FROM ghcr.io/astral-sh/uv:0.11.21 AS uv

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PATH="/app/.venv/bin:$PATH"

COPY --from=uv /uv /usr/local/bin/uv

WORKDIR /app

# 1) Dependencies only (cached until pyproject.toml / uv.lock change)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# 2) Application source
COPY . .

# 3) Static files for admin + Swagger UI. Dummy values exist ONLY for this command (not in the
#    image env); collectstatic never touches the database.
RUN SECRET_KEY=build-only-not-secret \
    WEBHOOK_SECRET=build-only-not-secret \
    DATABASE_URL=postgres://build:build@localhost:5432/build \
    ALLOWED_HOSTS=localhost \
    DJANGO_SETTINGS_MODULE=config.settings.prod \
    python manage.py collectstatic --noinput

# 4) Run as an unprivileged user
RUN useradd --create-home --uid 10001 app \
    && chmod +x docker/entrypoint.sh
USER app

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=5s --start-period=30s --retries=5 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/', timeout=4)"]

ENTRYPOINT ["docker/entrypoint.sh"]
