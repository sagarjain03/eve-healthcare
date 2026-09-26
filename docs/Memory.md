# Memory

> The AI must read this file at the start of every session and update it after every completed task.
> Keep entries short. Newest entries on top in the Log.

## Current Status
- **Current phase:** Phase 9 complete — **project complete**
- **Currently working on (file):** —
- **Next step:** Developer: replace `<GITHUB_USER>/<REPO>` in the README CI badge, commit, push to GitHub (CI runs on push), interview prep.

## Completed Phases
- [x] Phase 0 — Project Setup (commit: chore: project setup with django, drf and postgres)
- [x] Phase 1 — Common Layer + Custom User (commit: feat: common utilities and custom user model)
- [x] Phase 2 — Authentication APIs (commit: feat: jwt authentication)
- [x] Phase 3 — Centres & Tests catalog (commit: feat: diagnostic centres and tests catalog)
- [x] Phase 4 — Bookings with state machine (commit: feat: booking system with state machine)
- [x] Phase 5 — Simulated Payments (commit: feat: simulated payment service)
- [x] Phase 6 — Idempotent Webhook (commit: feat: idempotent payment webhook)
- [x] Phase 7 — Edge-case hardening & test review (commit: test: edge case coverage and consistent error handling)
- [x] Phase 8 — Docker, structured logging, webhook retries, CI (commit: feat: docker, structured logging, webhook retries and ci)
- [x] Phase 9 — README & submission (commit: docs: readme and submission)

## Coverage
- Phase 8: **98% overall** (1043 stmts, 20 missed) — 223 tests. webhook.py 98%, logging.py / middleware.py / reprocess_webhooks 100%.
- Phase 7: 98% (942 stmts) — 206 tests.
- Uncovered on purpose: model `__str__`, schema-only `swagger_fake_view` branch, final bare `raise` for an unexpected constraint, the concurrent-insert `IntegrityError` branch in `_claim_event` (covered only by real races).

## `check --deploy` (Phase 8 status)
- `--settings=config.settings.prod` **with HTTPS env values** (SECURE_SSL_REDIRECT, SESSION_COOKIE_SECURE, CSRF_COOKIE_SECURE=true, SECURE_HSTS_SECONDS=31536000, SECURE_HSTS_INCLUDE_SUBDOMAINS=true, SECURE_HSTS_PRELOAD=true): **0 issues**.
- With **local-Docker defaults** (plain HTTP on localhost) 4 warnings remain **on purpose**: W004 (no HSTS), W008 (no SSL redirect), W012 / W016 (cookies not `Secure`) — turning these on without HTTPS would break login/admin over `http://localhost`. W018 (DEBUG) is gone: prod forces `DEBUG=False`.

## Files Created / Modified
### Phase 9
- README.md — full reviewer README (quick start, API table, e2e curl walkthrough, ER + state diagrams, constraints, webhook outcomes, errors, structure, security, assumptions, limitations, improvements); Python snippet formatted by `ruff format` (ruff also checks Markdown code blocks)
- docs/Phases.md — Phase 9 ticked (push + interview prep left to developer)

### Phase 8
- pyproject.toml, uv.lock — `whitenoise` (only new library)
- config/settings/prod.py — DEBUG off, required ALLOWED_HOSTS, whitenoise + STORAGES, env-driven HTTPS settings, JSON logs
- config/settings/base.py — `RequestIdMiddleware` first in MIDDLEWARE; `LOGGING` (LOG_FORMAT text|json, LOG_LEVEL)
- apps/common/logging.py — `JsonFormatter`, `RequestIdFilter`, `request_id_var`
- apps/common/middleware.py — `RequestIdMiddleware` (X-Request-ID)
- apps/common/exceptions.py — `WebhookProcessingError` (500 `INTERNAL_ERROR`)
- apps/payments/webhook.py — FAILED events re-processed; `_claim_event`, `_record_failure`, `_process_locked`
- apps/payments/management/commands/reprocess_webhooks.py — `--max-attempts`, `--dry-run`
- Dockerfile, docker/entrypoint.sh, docker-compose.yml (`web` service), .dockerignore, .gitattributes
- .env.example — every variable, commented
- .github/workflows/ci.yml — ruff, format check, makemigrations --check, pytest --cov on Postgres 16
- 29 files reformatted once by `ruff format .` (quotes/wrapping only, no behaviour change)
- tests: apps/common/tests/test_logging.py, apps/payments/tests/test_reprocess_webhooks.py, retry tests in test_webhook.py
- docs/Architecture.md — tech stack, §3.4 retry flow, file tree; docs/EdgeCases.md — retry + request-id rows; docs/Phases.md — Phase 8 ticked (Redis/Celery marked skipped)

### Phase 7
- apps/common/views.py — `json_page_not_found` / `json_server_error` (handler404/500); health 503 now uses the standard error shape (`DATABASE_UNAVAILABLE`)
- config/urls.py — `handler404`, `handler500`
- apps/common/exceptions.py — 429 responses include `details.wait` (seconds)
- apps/centres/services.py, apps/bookings/services.py, apps/payments/services.py — docstrings/type hints only
- pyproject.toml — `[tool.coverage.run]` (source apps; omit migrations, tests, admin.py, apps.py)
- tests/test_error_responses.py — 404/500 JSON handlers, 503, 405, 415, PARSE_ERROR, 429, page out of range, expired JWT, UPPER_SNAKE_CASE code checks
- apps/centres/tests/test_seed_data.py — seed idempotency
- apps/centres/tests/test_api.py — non-admin POST /tests/ 403, admin create test, page_size cap, /tests/ query count
- apps/bookings/tests/test_api.py — naive/offset timezone tests
- apps/payments/tests/test_api.py — /payments/ query count
- apps/payments/tests/test_services.py — 5-thread concurrent payments, DB-constraint race branches
- apps/accounts/tests/test_services.py, apps/bookings/tests/test_services.py — race-branch tests
- apps/common/tests/test_exceptions.py — non-field ValidationError
- docs/EdgeCases.md — full edge-case matrix (F6 + phases 2–7 → handler → tests)
- docs/Phases.md — ticked Phase 7

### Phase 6
- apps/payments/models.py — `Payment.refund_required`; `WebhookEventStatus`, `WebhookEvent` (table `webhook_events`)
- apps/payments/migrations/0002_webhook_event_and_refund_required.py
- apps/payments/services.py — `ApplyResult` enum; `apply_payment_result` returns it and never touches a CANCELLED booking (flags refund on SUCCESS)
- apps/payments/webhook.py — `compute_signature`, `verify_signature`, `process_webhook_event`, `WebhookResult`
- apps/payments/serializers.py — `WebhookPayloadSerializer`, `WebhookResponseSerializer`; `refund_required` in `PaymentSerializer`
- apps/payments/views.py — `WebhookView` (`POST /payments/webhook/`)
- apps/payments/urls.py — webhook path listed before the router
- apps/payments/admin.py — `refund_required` on payments; view-only `WebhookEventAdmin`
- apps/payments/tests/test_webhook.py — signature, payload, processing, routing, throttle, 5-thread concurrency
- scripts/send_webhook.py — stdlib CLI that signs + sends events (`--times`, `--bad-signature`)
- config/settings/base.py, .env, .env.example — `WEBHOOK_SECRET` (required)
- docs/Architecture.md — §3.4 webhook flow + §4 payments/webhook_events schema updated
- docs/Phases.md — ticked Phase 6

### Phase 5
- apps/payments/models.py — `PaymentStatus`, `Payment` (table `payments`; amount > 0, one PENDING/SUCCESS per booking, unique (user, idempotency_key) when key set)
- apps/payments/migrations/0001_initial.py
- apps/payments/services.py — `PAYMENT_TRANSITIONS`, `apply_payment_result` (only payment → booking mapping), `create_payment`
- apps/payments/serializers.py — `PaymentCreateSerializer`, `PaymentSerializer`
- apps/payments/filters.py — `PaymentFilter` (`?booking=`)
- apps/payments/views.py — `PaymentViewSet` (create/list/retrieve by reference, Idempotency-Key header, create-only throttle)
- apps/payments/urls.py — SimpleRouter mounted at `payments/` in config/urls.py
- apps/payments/admin.py — view-only (no add/change/delete)
- apps/payments/tests/ — factories.py, test_models.py, test_services.py, test_api.py; old stub tests.py deleted
- config/settings/base.py — `PAYMENT_SUCCESS_RATE`, `payments: 20/min` throttle, `ENUM_NAME_OVERRIDES` (schema)
- .env, .env.example — `PAYMENT_SUCCESS_RATE=0.8`
- docs/Prd.md — F4 updated (PENDING outcome, rules, list endpoint)
- docs/Phases.md — ticked Phase 5

### Phase 4
- apps/bookings/models.py — `BookingStatus`, `Booking` (table `bookings`; amount > 0 check, partial unique on active slot, `(user, -created_at)` index)
- apps/bookings/migrations/0001_initial.py
- apps/bookings/state_machine.py — `ALLOWED_TRANSITIONS`, `can_transition`, `transition` (only place that sets `booking.status`)
- apps/bookings/services.py — `create_booking`, `cancel_booking`
- apps/bookings/serializers.py — `BookingCreateSerializer`, `BookingSerializer` (nested centre/test)
- apps/bookings/filters.py — `BookingFilter` (`?status=` ChoiceFilter → 400 on bad value)
- apps/bookings/views.py — `BookingViewSet` (list/retrieve/create + `POST /bookings/{id}/cancel/`)
- apps/bookings/urls.py — SimpleRouter, mounted at root in config/urls.py
- apps/bookings/admin.py — read-only status/amount, no "add" in admin
- apps/bookings/tests/ — factories.py, test_state_machine.py, test_services.py, test_api.py; old stub tests.py deleted
- apps/common/exceptions.py — `DuplicateBooking`; `DomainError(..., code=...)` optional per-raise code
- config/settings/base.py, .env, .env.example — `MAX_BOOKING_DAYS_AHEAD` (default 90)
- docs/Phases.md — ticked Phase 4

### Phase 3
- apps/centres/models.py — `DiagnosticCentre`, `DiagnosticTest`, `CentreTest` (tables `diagnostic_centres`, `diagnostic_tests`, `centre_tests` as in Architecture §4)
- apps/centres/migrations/0001_initial.py — the three tables + constraints
- apps/centres/services.py — `create_centre`/`update_centre`, `create_test`/`update_test` (IntegrityError → 409), `upsert_offering`
- apps/centres/serializers.py — test, centre list/detail/write, offering read/write serializers
- apps/centres/filters.py — `CentreFilter` (`city` iexact, `test` id or code)
- apps/centres/views.py — `CentreViewSet` (+ `POST /centres/{id}/tests/`), `DiagnosticTestViewSet`
- apps/centres/urls.py — DefaultRouter (`/centres/`, `/tests/`), mounted at root in config/urls.py
- apps/centres/admin.py — all three models; centre admin with offerings inline
- apps/centres/management/commands/seed_data.py — idempotent seed (admin, 8 tests, 4 centres, 25 offerings)
- apps/centres/tests/ — factories.py, test_models.py, test_services.py, test_api.py; old stub tests.py deleted
- apps/common/exceptions.py — added `CentreAlreadyExists`, `TestCodeAlreadyExists`; handler now maps Django `Http404`/`PermissionDenied` to `NOT_FOUND`/`PERMISSION_DENIED` (was `ERROR`)
- apps/common/tests/test_exceptions.py — regression test for Http404 code
- .env.example — `SEED_ADMIN_EMAIL`, `SEED_ADMIN_PASSWORD` (dev only)
- docs/Phases.md — ticked Phases 0–3

### Phase 2
- config/settings/base.py — `SIMPLE_JWT` (lifetimes from env), `ScopedRateThrottle` + `auth: 10/min`
- .env, .env.example — added `JWT_ACCESS_MINUTES`, `JWT_REFRESH_DAYS`
- apps/common/exceptions.py — added `EmailAlreadyExists(Conflict)` (`EMAIL_ALREADY_EXISTS`)
- apps/common/views.py — added `@extend_schema` to `health_check` (it was missing from Swagger)
- apps/accounts/services.py — `register_user()` (duplicate check + IntegrityError → 409)
- apps/accounts/serializers.py — `SignupSerializer`, `UserSerializer`, `EmailTokenObtainPairSerializer`
- apps/accounts/views.py — `SignupView`, `LoginView`, `RefreshView`, `MeView`
- apps/accounts/urls.py — `/auth/signup/`, `/auth/login/`, `/auth/token/refresh/`, `/auth/me/`
- config/urls.py — mounted `auth/`
- apps/accounts/tests/factories.py — `UserFactory` (password "StrongPass!123")
- conftest.py (project root) — shared fixtures: `api_client`, `user`, `admin_user`, `auth_client`, `admin_client`, autouse cache clear
- tests/conftest.py — deleted (moved to root, see Decisions)
- apps/accounts/tests/test_services.py, apps/accounts/tests/test_api.py
- docs/Architecture.md — folder tree: conftest.py now at project root

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
- Duplicate email on signup → **409** `EMAIL_ALREADY_EXISTS` (not 400): it's a conflict with existing state, not bad input.
- Login email is case-insensitive (`EmailTokenObtainPairSerializer` lowercases before authenticating).
- Signup returns the created user (201) **without tokens** — client calls `/auth/login/` next. Keeps signup and login single-purpose.
- Signup/login/refresh have `authentication_classes = ()` so a stale or garbage `Authorization` header can't block them.
- Auth endpoints (signup + login) share throttle scope `auth` = 10/min per IP.
- Tests clear Django's cache before/after each test (autouse fixture) so throttle counters don't leak between tests.
- Centres and tests have **no DELETE** (405). Deactivate with `PATCH {"is_active": false}` so booking history is never lost.
- Public (anonymous + non-staff) sees only active centres, active tests, and active offerings of active tests; inactive centre detail → 404. Staff see everything.
- Prices are returned as **strings** (DRF default for `DecimalField`, e.g. `"499.00"`) to avoid float rounding.
- Centre name + city is unique **case-insensitively** (`Lower(name), Lower(city)` constraint) → 409 `CENTRE_ALREADY_EXISTS`.
- Test `code` is stored **UPPERCASE** (stripped in `save()`); duplicate code in any case → 409 `TEST_CODE_ALREADY_EXISTS`.
- `?test=` filter accepts numeric id or code (case-insensitive) and matches only centres with an active offering; `.distinct()` avoids duplicates.
- Offering upsert: `POST /centres/{id}/tests/` → 201 created / 200 updated. Inactive test → 400 `BUSINESS_RULE_VIOLATION`. `CentreTest.centre` is CASCADE, `CentreTest.test` is PROTECT.
- `seed_data` is idempotent (get_or_create / update_or_create; offerings' prices re-synced). Dev admin = `SEED_ADMIN_EMAIL` / `SEED_ADMIN_PASSWORD` (defaults `admin@eve.local` / `Admin@12345`, **dev only**); an existing admin's password is never overwritten.
- Booking `amount` is a **snapshot** of `CentreTest.price` at creation; later price changes don't touch existing bookings. Client-sent `amount`/`status` are ignored.
- Other users' bookings → **404 `BOOKING_NOT_FOUND`** (never 403), so their existence isn't leaked. Querysets are always filtered by `request.user`.
- **CONFIRMED bookings can be cancelled** (refunds are out of scope).
- **Past appointments can't be cancelled** → 400 `APPOINTMENT_ALREADY_PASSED`.
- **Re-booking the same slot is allowed** after the first booking is CANCELLED/FAILED (partial unique only covers PENDING/CONFIRMED).
- **FAILED → FAILED is allowed** so repeated failed payment attempts don't error.
- Invalid/inactive centre or test in the request body → **400** (`CENTRE_NOT_AVAILABLE`, `TEST_NOT_OFFERED`), not 404 — they're input fields, not the URL resource.
- Appointment must be in the future and ≤ `MAX_BOOKING_DAYS_AHEAD` days (default 90) → 400 `APPOINTMENT_IN_PAST` / `APPOINTMENT_TOO_FAR`.
- **Admin can't edit status or amount** (read-only) and can't add bookings in admin — bookings go through the service + state machine.
- `DomainError` accepts an optional `code=` so one exception class (e.g. `BusinessRuleViolation`) can carry specific codes.
- Booking ids in URLs must be digits (`lookup_value_regex = r"\d+"`).
- `POST /payments/` `outcome`: `SUCCESS` → booking CONFIRMED; `FAILED` → booking FAILED (retry allowed); **`PENDING` → both stay PENDING until the webhook settles it (simulates an async provider)**; omitted → random SUCCESS/FAILED via `PAYMENT_SUCCESS_RATE` (default 0.8).
- **One active payment per booking**: DB allows at most one PENDING or SUCCESS payment per booking; any number of FAILED ones (retries). Paying while one is PENDING → 409 `PAYMENT_IN_PROGRESS`; paying CONFIRMED/CANCELLED → 409 `BOOKING_NOT_PAYABLE`; past appointment → 400.
- **Payments are terminal after SUCCESS/FAILED** (`PENDING → SUCCESS|FAILED` only). A retry is a new payment row. Re-applying the same status is a no-op.
- `apply_payment_result()` is the **only** code that maps a payment result onto a booking (webhook will reuse it); it calls `state_machine.transition`.
- **Idempotency-Key** (optional header, ≤ 100 chars): scoped **per user** and **bound to one booking**. Same key + same booking → original payment, 200 (created=False). Same key + different booking → 409 `IDEMPOTENCY_KEY_REUSED`. Race on the key is caught via the DB constraint name.
- **Reference format** `pay_` + uuid4 hex (32 chars). Detail URL only matches `pay_[0-9a-f]{32}`, so it can never collide with `/payments/webhook/`.
- **Payments throttle 20/min per user**, only on `POST /payments/` (reads not throttled).
- Payment `amount` is copied from `booking.amount`; client-sent `amount`/`status` are ignored.
- Schema: `ENUM_NAME_OVERRIDES` gives `BookingStatusEnum` / `PaymentStatusEnum` stable names (both models have `status`).
- **Payment follows the provider; booking follows the user.** Webhook SUCCESS for a CANCELLED booking → payment SUCCESS, `refund_required=True`, booking stays CANCELLED, WARNING log, event PROCESSED note `refund_required` (refund itself out of scope). Webhook FAILED for a CANCELLED booking → payment FAILED, booking stays CANCELLED.
- **Payments terminal after SUCCESS/FAILED**: a conflicting later event (FAILED after SUCCESS, SUCCESS after FAILED) → event IGNORED note `terminal_payment`, WARNING log, 200, no change.
- A new event_id reporting the status the payment already has → IGNORED note `already_in_status`, 200.
- **Same event_id again → 200 `{"result": "DUPLICATE"}`**, no change, no new row; `attempts` is incremented. Concurrent twins are caught by the unique `event_id` (savepoint + IntegrityError).
- **Lock order everywhere: booking first, then payment** (matches `create_payment`) to avoid deadlocks.
- **4xx failures store no WebhookEvent** (bad signature 401, bad payload 400, unknown reference 404 `PAYMENT_NOT_FOUND`, amount mismatch 400 `AMOUNT_MISMATCH`) so the provider can retry after a fix. Only events that reach processing are stored.
- **Signature**: header `X-Webhook-Signature: sha256=<hex>`, hex = HMAC-SHA256(`WEBHOOK_SECRET`, exact raw body). Verified on `request.body` before parsing, with `hmac.compare_digest`. Secret/signature never logged. `WEBHOOK_SECRET` is required (no default).
- Webhook `status` accepts only SUCCESS/FAILED (PENDING isn't a result). No JWT, `AllowAny`, not throttled.
- `apply_payment_result` returns `ApplyResult` (APPLIED / NO_CHANGE / REFUND_REQUIRED) so the webhook can record the note.
- Stored `payload` is the validated payload with `amount` as a string (JSON-safe).
- **Every non-2xx response uses the standard error shape**, including unmatched URLs (JSON `handler404` → `NOT_FOUND`), unexpected errors (JSON `handler500` → `INTERNAL_ERROR`, generic message, no traceback; only when `DEBUG=False`) and the health check 503 (`DATABASE_UNAVAILABLE`, changed from `{"status": "error"}` in Phase 7).
- 429 responses include `details.wait` (seconds until retry).
- **Timezone rule**: all datetimes stored/returned in UTC (`...Z`). An appointment_at **without an offset is interpreted as UTC**; one with an offset (e.g. `+05:30`) is converted to UTC.
- **Secrets**: `SECRET_KEY` and `WEBHOOK_SECRET` have **no defaults** (`env('...')` raises `ImproperlyConfigured` if missing), in every environment — stricter than "required when DEBUG=False". Loggers only log ids/references/statuses/amounts; never passwords, tokens, secrets or signatures.
- **Ownership review (Phase 7)**: every bookings/payments query on user-owned rows is scoped by `user` (views' `get_queryset`, `cancel_booking`, `_create_payment_locked`, idempotency lookup). The webhook is the only unscoped path, protected by HMAC.
- **No Redis, no Celery** (Phase 8 scope decision): they add infrastructure the current load doesn't need. Webhook retries are handled by FAILED events + `reprocess_webhooks`; both go in README "Future improvements".
- **whitenoise** is the only library added in Phase 8: serves collected static files (admin CSS/JS) from gunicorn, hashed + compressed, no nginx. Swagger UI JS loads from drf-spectacular's default CDN.
- **Production settings via env** (`config/settings/prod.py`): same image runs local Docker over HTTP (defaults) or real HTTPS (flip SECURE_SSL_REDIRECT / SESSION_COOKIE_SECURE / CSRF_COOKIE_SECURE / SECURE_HSTS_* — documented in prod.py and .env.example). `SECURE_PROXY_SSL_HEADER` trusts `X-Forwarded-Proto` from the TLS proxy.
- **Throttle caveat**: throttles use Django's default **LocMemCache, which is per gunicorn worker** (3 workers → a client could get up to ~3× the limit). Verified the auth 10/min and payments 20/min throttles work under prod settings. A shared Redis cache would make limits exact — future improvement.
- **Webhook FAILED / retry semantics**: an unexpected (non-domain) error rolls back the whole processing transaction (booking/payment unchanged), then the event is stored as FAILED (note = exception class, attempts += 1) in a separate transaction, logged with traceback, and 500 `INTERNAL_ERROR` is returned so the provider retries. A FAILED event is **not** a duplicate: a resend (or `reprocess_webhooks`) processes it again; PROCESSED/IGNORED stay DUPLICATE. `reprocess_webhooks --max-attempts 5 [--dry-run]` re-runs FAILED events from stored payload (signature was verified on receipt) and skips those at max attempts. Booking/payment still can't change twice (single transaction + terminal payments).
- **Structured logging**: `LOG_FORMAT=json` (default in prod/Docker) prints one JSON object per line with timestamp (UTC), level, logger, message, `request_id` and all `extra` fields; `text` locally. `X-Request-ID` is accepted if `[A-Za-z0-9-]{1,64}`, otherwise generated (uuid4 hex), and echoed in the response. Gunicorn access logs stay in gunicorn's own text format.
- **Docker**: `python:3.12-slim` + uv (pinned `0.11.21`), deps layer cached from `uv.lock`, collectstatic at build with throw-away env, non-root user (uid 10001), HEALTHCHECK on `/health/`. Entry: migrate → seed_data (if `SEED_ON_START=true`) → gunicorn (3 workers). Compose web overrides DATABASE_URL (`db:5432`), prod settings, ALLOWED_HOSTS, JSON logs.
- **CI** (GitHub Actions): Postgres 16 service, `uv sync --frozen`, `ruff check`, `ruff format --check`, `makemigrations --check`, `pytest --cov`. Code base was formatted once with `ruff format .` in Phase 8.
- Shared fixtures live in a **root `conftest.py`**, not `tests/conftest.py`: pytest only applies a conftest to tests in its own folder or below, so fixtures in `tests/` were invisible to `apps/*/tests/`.

## Known Issues / TODO
- ~~Cancel while payment PENDING, then webhook SUCCESS~~ — resolved in Phase 6 (`refund_required`).
- Actual refunds for `refund_required` payments are out of scope (flag + admin filter only).
- ~~Non-numeric booking id returns Django's HTML 404~~ — fixed in Phase 7 by the JSON `handler404` (active when `DEBUG=False`; with `DEBUG=True` Django still shows its debug 404 page).
- ~~No superuser yet~~ — `seed_data` creates the dev admin (`SEED_ADMIN_EMAIL` / `SEED_ADMIN_PASSWORD`).
- If `uv run pytest` fails with "uv trampoline failed to canonicalize script path", regenerate the launchers: `uv sync --reinstall-package pytest --reinstall-package django`.

## Log
- 2026-09-27 — Phase 9 finished, **project complete**. README verified from a clean clone (`git clone .` → temp folder; original containers stopped to free ports 8000/5433, then restarted): Quick start exactly as written → db + web healthy, /health/ 200, /api/docs/ 200; README e2e bash block extracted verbatim and run in Git Bash → every step matched (FAILED → SUCCESS 201 → replay 200 same reference → 409 BOOKING_NOT_PAYABLE → PENDING → webhook ×3 = 1 PROCESSED + 2 DUPLICATE → CONFIRMED). Fixed in README: added `-w '\n'` so printed responses don't run together. Temp clone, its containers, volume and image removed. Submission checks: no .env/.venv/staticfiles/pycache/coverage tracked, real secrets not in repo, README doc links resolve, both Mermaid diagrams render with mermaid-cli. Final: pytest 223 passed / 98% ✅, ruff check ✅, ruff format --check ✅ (after formatting README's Python block), makemigrations --check ✅, spectacular ✅.
- 2026-09-27 — Phase 8 finished: prod settings + whitenoise, Docker (web+db, healthchecks), JSON logging + request ids, webhook FAILED/retry + reprocess_webhooks, CI, one-time ruff format. Verified: check ✅, makemigrations --check ✅, pytest 223 passed / 98% ✅, ruff check + format ✅, spectacular ✅, check --deploy prod+HTTPS env 0 issues ✅, throttle tests under prod settings ✅. Docker: down -v → up --build → db + web healthy; logs show migrate → seed → gunicorn with JSON lines; /health/ 200, /api/docs/ 200, /admin/login/ 200, hashed admin CSS 200 via whitenoise; /nope/ JSON 404; signup → login → book → pay PENDING → send_webhook ×3 (1 PROCESSED + 2 DUPLICATE) → booking CONFIRMED; JSON logs carry request_id + payment_reference ✅. Dev DB was reset by `down -v` and re-seeded by the container.
- 2026-09-27 — Phase 7 finished: EdgeCases.md matrix (all F6 rows tested), JSON 404/500 handlers, standard 503, 429 wait, new tests (expired JWT, concurrent payments, races, timezone, query counts, page_size cap, seed idempotency), coverage config. Verified: check ✅, check --deploy (5 warnings, for Phase 8), makemigrations --check ✅, pytest 206 passed, 98% coverage ✅, ruff clean ✅, spectacular --fail-on-warn ✅. .env confirmed untracked by git ✅.
- 2026-09-27 — Phase 6 finished: WebhookEvent + refund_required, HMAC signature, idempotent process_webhook_event, webhook view, send_webhook.py. Verified: check ✅, makemigrations --check ✅, pytest 178 passed (incl. 5-thread concurrency) ✅, ruff clean ✅, spectacular --fail-on-warn ✅. Live on booking #3: same SUCCESS event ×5 → 1 PROCESSED + 4 DUPLICATE, booking CONFIRMED, 1 row with attempts=5 ✅; new FAILED event → IGNORED terminal_payment ✅; bad signature → 401 ✅; wrong amount → 400 AMOUNT_MISMATCH ✅. Grep: booking status only via state_machine; payment → booking only via apply_payment_result ✅.
- 2026-09-27 — Phase 5 finished: Payment model + constraints, create_payment / apply_payment_result, payments API with Idempotency-Key + throttle, admin. Verified: check ✅, makemigrations --check ✅, pytest 156 passed ✅, ruff clean ✅, spectacular --fail-on-warn ✅, live FAILED → FAILED booking → SUCCESS → CONFIRMED → pay again 409 → key replay 200 same reference ✅, PENDING payment left for Phase 6 ✅. Grep: `booking.status =` only in state_machine.py; `payment.status =` only in apply_payment_result ✅.
- 2026-09-27 — Phase 4 finished: Booking model + constraints, state machine, create/cancel services, bookings API, admin. Verified: check ✅, makemigrations --check ✅, pytest 117 passed ✅, ruff clean ✅, spectacular --fail-on-warn ✅, live signup → book → list → cancel → cancel again (409) ✅, grep: `booking.status =` only in state_machine.py ✅.
- 2026-09-27 — Phase 3 finished: centres/tests/offerings catalog, filters, admin, idempotent seed. Fixed handler returning `ERROR` for Django Http404. Verified: check ✅, makemigrations --check ✅, seed_data ×2 (2nd run creates nothing) ✅, pytest 64 passed ✅, ruff clean ✅, spectacular --fail-on-warn ✅, live /centres/ endpoints ✅.
- 2026-09-27 — Phase 2 finished: signup/login/refresh/me with JWT, auth throttle, factories + shared fixtures. Verified: check ✅, makemigrations --check ✅, pytest 32 passed ✅, ruff clean ✅, spectacular --fail-on-warn ✅, live signup → login → /auth/me/ ✅.
- 2026-09-27 — Added DB-level case-insensitive unique constraint on User.email (migration 0002) + bypass-save test. pytest 15 passed ✅, ruff clean ✅.
- 2026-09-27 — Phase 1 finished: TimeStampedModel, domain exceptions + handler, pagination, IsAdminOrReadOnly, custom User + admin, first migrate. Verified: check ✅, showmigrations accounts [X] 0001_initial ✅, pytest 14 passed ✅, ruff clean ✅.
- 2026-09-27 — Phase 0 finished: split settings, env config, health endpoint, Swagger, pytest + ruff setup, docker db. Verified: check ✅, pytest 1 passed ✅, ruff clean ✅, /health/ 200 ✅, /api/schema/ 200 ✅, /api/docs/ 200 ✅.
