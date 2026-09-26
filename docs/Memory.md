# Memory

> The AI must read this file at the start of every session and update it after every completed task.
> Keep entries short. Newest entries on top in the Log.

## Current Status
- **Current phase:** Phase 1 complete
- **Currently working on (file):** —
- **Next step:** Start Phase 2 — Authentication APIs (signup, login, refresh, me)

## Completed Phases
- [x] Phase 0 — Project Setup (commit: chore: project setup with django, drf and postgres)
- [x] Phase 1 — Common Layer + Custom User (commit: feat: common utilities and custom user model)

## Files Created / Modified
### Phase 1
- apps/common/models.py — abstract `TimeStampedModel` (created_at, updated_at)
- apps/common/exceptions.py — `DomainError` + NotFound/Conflict/InvalidStateTransition/BusinessRuleViolation/InvalidSignature, `custom_exception_handler`
- apps/common/pagination.py — `DefaultPagination` (20 per page, `page_size` param, max 100)
- apps/common/permissions.py — `IsAdminOrReadOnly`
- apps/accounts/models.py — custom `User` (email login) + `UserManager`
- apps/accounts/admin.py — `UserAdmin` using email instead of username
- apps/accounts/migrations/0001_initial.py — User table (first migration; `migrate` now applied)
- apps/accounts/migrations/0002_user_email_ci_unique.py — case-insensitive unique index on email
- config/settings/base.py — `AUTH_USER_MODEL`, `DEFAULT_PAGINATION_CLASS`, `EXCEPTION_HANDLER`
- apps/accounts/tests/test_models.py, apps/common/tests/test_exceptions.py, apps/common/tests/test_permissions.py (+ `__init__.py` in each tests/)
- apps/accounts/tests.py, apps/common/tests.py — deleted (empty startapp stubs; clashed with the new tests/ packages)

### Phase 0
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
- Login is by **email** (`USERNAME_FIELD = "email"`); no username field. `full_name` is required.
- Email is stripped + lowercased in both `UserManager.create_user()` and `User.save()`, so the plain `UNIQUE` on email is effectively case-insensitive.
- DB also enforces it: `UniqueConstraint(Lower("email"), name="user_email_ci_unique")` (migration `accounts/0002_user_email_ci_unique`, a unique index on `LOWER(email)`). Catches writes that bypass `save()` (`bulk_create`, `.update()`, raw SQL).
- Error shape is always `{"error": {"code", "message", "details"}}`. Codes: domain errors use their own (`NOT_FOUND`, `CONFLICT`, `INVALID_STATE_TRANSITION`, `BUSINESS_RULE_VIOLATION`, `INVALID_SIGNATURE`); DRF validation → `VALIDATION_ERROR` with field errors in `details`; other DRF errors → `default_code` upper-cased (e.g. `NOT_AUTHENTICATED`, `PERMISSION_DENIED`, `THROTTLED`).
- Class-level Django config (admin options, `REQUIRED_FIELDS`) uses tuples, not lists, to satisfy ruff RUF012.

## Known Issues / TODO
- No superuser yet — developer runs `uv run python manage.py createsuperuser` manually.
- If `uv run pytest` fails with "uv trampoline failed to canonicalize script path", regenerate the launchers: `uv sync --reinstall-package pytest --reinstall-package django`.

## Log
- 2026-09-27 — Added DB-level case-insensitive unique constraint on User.email (migration 0002) + bypass-save test. pytest 15 passed ✅, ruff clean ✅.
- 2026-09-27 — Phase 1 finished: TimeStampedModel, domain exceptions + handler, pagination, IsAdminOrReadOnly, custom User + admin, first migrate. Verified: check ✅, showmigrations accounts [X] 0001_initial ✅, pytest 14 passed ✅, ruff clean ✅.
- 2026-09-27 — Phase 0 finished: split settings, env config, health endpoint, Swagger, pytest + ruff setup, docker db. Verified: check ✅, pytest 1 passed ✅, ruff clean ✅, /health/ 200 ✅, /api/schema/ 200 ✅, /api/docs/ 200 ✅.
