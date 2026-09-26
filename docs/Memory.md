# Memory

> The AI must read this file at the start of every session and update it after every completed task.
> Keep entries short. Newest entries on top in the Log.

## Current Status
- **Current phase:** Phase 0 complete
- **Currently working on (file):** —
- **Next step:** Start Phase 1 — Common Layer + Custom User (`AUTH_USER_MODEL` must be set before the first `migrate`)

## Completed Phases
- [x] Phase 0 — Project Setup (commit: chore: project setup with django, drf and postgres)

## Files Created / Modified
- pyproject.toml — deps (uv) + `[tool.pytest.ini_options]` + `[tool.ruff]`
- config/settings/__init__.py — package marker (empty)
- config/settings/base.py — moved from config/settings.py; env-driven (django-environ), DRF/JWT/spectacular/filter config, 5 local apps
- config/settings/local.py — dev settings (imports base)
- config/settings/test.py — test settings, MD5 password hasher for speed
- config/settings.py — deleted
- config/urls.py — admin/, health/, api/schema/, api/docs/
- manage.py, config/wsgi.py, config/asgi.py — default settings = config.settings.local
- apps/payments/ — created with startapp (folder was empty); apps.py name = "apps.payments"
- apps/*/admin.py, models.py, tests.py, views.py — unused startapp imports removed by `ruff --fix`
- apps/common/views.py — `health_check` (AllowAny, `SELECT 1`, 200 ok / 503 error)
- tests/__init__.py, tests/conftest.py (`api_client`), tests/test_health.py
- docker-compose.yml — `db` service only (postgres:16, host port 5433, healthcheck)
- .env, .env.example, .gitignore — created
- main.py — deleted (uv init leftover)
- docs/Architecture.md, docs/Phases.md — requirements*.txt → pyproject.toml + uv.lock

## Decisions & Assumptions
- Using uv + pyproject.toml (+ uv.lock) instead of requirements.txt / requirements-dev.txt. Run everything with `uv run`.
- Local Postgres container is exposed on host port **5433** (not 5432) because a native Windows PostgreSQL 18 service already listens on 5432. Inside Docker (Phase 8) the app will still use `db:5432`.
- `migrate` not run yet on purpose — custom User model must exist first (Phase 1).

## Known Issues / TODO
- `manage.py check`/`runserver` show "unapplied migrations" warning — expected until Phase 1.
- If `uv run pytest` fails with "uv trampoline failed to canonicalize script path", regenerate the launchers: `uv sync --reinstall-package pytest --reinstall-package django`.

## Log
- 2026-09-27 — Phase 0 finished: split settings, env config, health endpoint, Swagger, pytest + ruff setup, docker db. Verified: check ✅, pytest 1 passed ✅, ruff clean ✅, /health/ 200 ✅, /api/schema/ 200 ✅, /api/docs/ 200 ✅.
