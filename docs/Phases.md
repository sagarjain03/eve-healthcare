# Phases

Work through phases **in order**. Each phase ends with: tests passing, `ruff` clean, `memory.md` updated, and a git commit.
Estimated total: ~4–6 hours of focused work (vibe-coded).

---

## Phase 0 — Project Setup
**Goal:** Empty but runnable Django project with Postgres.
- [ ] Create folder structure from `Architecture.md` §5.
- [ ] `pyproject.toml` + `uv.lock` (dependencies via uv, ruff + pytest config), `.gitignore`, `.env.example`.
- [ ] Django project in `config/` with split settings (`base`, `local`, `test`).
- [ ] `docker-compose.yml` with a `db` service (Postgres 16) — app service comes in Phase 8.
- [ ] Create empty apps: `common`, `accounts`, `centres`, `bookings`, `payments` under `apps/`.
- [ ] DRF + simplejwt + drf-spectacular + django-filter configured in settings.
- [ ] `/health/` endpoint (checks DB connection).
- [ ] `/api/docs/` Swagger loads.
- [ ] `tests/conftest.py` with `api_client` fixture; one test for `/health/`.

**Done when:** `docker compose up db` + `python manage.py runserver` works, `/api/docs/` opens, `pytest` passes.
**Commit:** `chore: project setup with django, drf and postgres`

---

## Phase 1 — Common Layer + Custom User
**Goal:** Shared building blocks and the user model (before any other migration!).
- [ ] `apps/common/models.py` — `TimeStampedModel` (abstract).
- [ ] `apps/common/exceptions.py` — domain exceptions + custom DRF exception handler (standard error shape).
- [ ] `apps/common/pagination.py` — default page-number pagination (page size 20, max 100).
- [ ] `apps/common/permissions.py` — `IsAdminOrReadOnly`.
- [ ] `apps/accounts/models.py` — custom `User` (email as username) + `UserManager`.
- [ ] `AUTH_USER_MODEL` set; first migrations created.
- [ ] Register User in admin.
- [ ] Tests: user manager creates user/superuser, email normalized, exception handler output shape.

**Done when:** migrations apply on fresh DB, tests pass.
**Commit:** `feat: common utilities and custom user model`

---

## Phase 2 — Authentication APIs
**Goal:** Signup, login, refresh, me.
- [ ] `SignupSerializer` (email unique case-insensitive, Django password validators, full_name required).
- [ ] Views + URLs: `/auth/signup/`, `/auth/login/`, `/auth/token/refresh/`, `/auth/me/`.
- [ ] JWT lifetimes from env.
- [ ] Throttle on signup/login (scoped throttle, e.g. 10/min).
- [ ] Swagger docs for all auth endpoints.
- [ ] Tests: signup success, duplicate email (409 or 400 — decide + record), weak password, invalid email, login success, wrong password (401), `/me` without token (401), with expired/invalid token (401).

**Done when:** can signup → login → call `/auth/me/` via Swagger.
**Commit:** `feat: jwt authentication`

---

## Phase 3 — Centres & Tests
**Goal:** Catalog of centres, tests and prices.
- [ ] Models: `DiagnosticCentre`, `DiagnosticTest`, `CentreTest` (unique centre+test, price > 0 check).
- [ ] Serializers: list/detail (detail includes offered tests + prices).
- [ ] Viewsets with `IsAdminOrReadOnly`; `/centres/{id}/tests/` action for adding/updating an offering.
- [ ] Filters: centres by `city`, by `test` (id or code).
- [ ] Pagination on lists; `prefetch_related` to avoid N+1.
- [ ] Management command `seed_data` — admin user, 3–4 centres, 6–8 tests, prices.
- [ ] Admin registration.
- [ ] Tests: public list/detail, filters, non-admin POST → 403, admin POST → 201, duplicate offering, invalid price.

**Done when:** `python manage.py seed_data` works and centres show in Swagger.
**Commit:** `feat: diagnostic centres and tests catalog`

---

## Phase 4 — Bookings
**Goal:** Users can create, list, view and cancel their own bookings.
- [ ] `Booking` model + `BookingStatus` choices + partial unique constraint for active duplicates.
- [ ] `state_machine.py` — `ALLOWED_TRANSITIONS` + `transition(booking, new_status)` raising `InvalidStateTransition`.
- [ ] `services.create_booking()` — all validation rules from `Architecture.md` §3.2, amount snapshot.
- [ ] `services.cancel_booking()` — with `select_for_update`.
- [ ] Endpoints: `POST/GET /bookings/`, `GET /bookings/{id}/`, `POST /bookings/{id}/cancel/`.
- [ ] Querysets always filtered by `request.user`.
- [ ] Tests: create success (amount = server price), test not offered at centre, inactive centre, past date, too far ahead, duplicate active booking (409), other user's booking (404), non-existent id (404), cancel twice (409), unauthenticated (401), every state-machine transition (valid + invalid).

**Done when:** full booking lifecycle (without payment) works and is tested.
**Commit:** `feat: booking system with state machine`

---

## Phase 5 — Simulated Payments
**Goal:** `POST /payments/` updates the booking.
- [ ] `Payment` model (unique reference, one SUCCESS per booking constraint, unique user+idempotency_key).
- [ ] `services.create_payment()` — lock booking, check status, decide outcome, create payment.
- [ ] `services.apply_payment_result()` — the **single** function that maps payment status → booking status (used again by webhook).
- [ ] `Idempotency-Key` header support.
- [ ] Endpoints: `POST /payments/`, `GET /payments/{reference}/`.
- [ ] Throttle on payments.
- [ ] Tests: success → CONFIRMED, failed → FAILED, retry after FAILED → CONFIRMED, pay CONFIRMED booking (409), pay CANCELLED (409), other user's booking (404), invalid booking id (404/400), same Idempotency-Key twice returns same payment, random outcome (mocked).

**Done when:** booking → pay → confirmed flow works end-to-end.
**Commit:** `feat: simulated payment service`

---

## Phase 6 — Idempotent Webhook
**Goal:** Safe provider callbacks.
- [ ] `WebhookEvent` model (unique `event_id`, JSONB payload, status, attempts, error).
- [ ] `webhook.py` — `verify_signature(raw_body, header)` + `process_webhook_event(payload)`.
- [ ] View: `POST /payments/webhook/` (no JWT, `AllowAny` + signature check, throttle exempt or high limit).
- [ ] Rules: duplicate event → 200 no-op; unknown payment → 404; amount mismatch → 400; late FAILED after SUCCESS → IGNORED.
- [ ] `scripts/send_webhook.py` — CLI that builds + signs + sends a webhook (for demo and README).
- [ ] Tests: valid event updates booking, same event twice → one state change + one event row, bad signature (401), missing signature (401), unknown reference (404), amount mismatch (400), FAILED after CONFIRMED ignored, two different events for same payment handled correctly.

**Done when:** sending the same webhook 5 times leaves exactly one event row and correct booking state.
**Commit:** `feat: idempotent payment webhook`

---

## Phase 7 — Edge-Case Hardening & Test Review
**Goal:** Nothing in `Prd.md` §F6 is untested.
- [ ] Go through §F6 table row by row; add missing tests.
- [ ] Check every error response follows the standard shape.
- [ ] Check no N+1 queries on list endpoints (`django_assert_num_queries`).
- [ ] Check all list endpoints paginated.
- [ ] Add test coverage report (`pytest --cov`) — aim ≥ 85% on services.

**Done when:** all F6 rows have a passing test.
**Commit:** `test: edge case coverage`

---

## Phase 8 — Docker & Bonus Engineering
**Goal:** One-command run + selected bonuses.
- [ ] `Dockerfile` (python:3.12-slim, non-root user, gunicorn).
- [ ] `docker-compose.yml`: `web` + `db` (healthcheck), web runs migrate + seed on start (entrypoint script).
- [ ] Structured JSON logging (`apps/common/logging.py`).
- [ ] Rate limiting verified (auth, payments).
- [ ] Webhook retry handling: events stored as `FAILED` with error + attempts; management command `reprocess_webhooks` retries them.
- [ ] (Optional, only if time) Redis cache for `GET /centres/` with invalidation on admin write.
- [ ] (Optional, only if time) Celery for async webhook processing.

**Done when:** fresh clone → `cp .env.example .env` → `docker compose up --build` → Swagger works.
**Commit:** `feat: docker, structured logging and webhook retries`

---

## Phase 9 — README & Submission
**Goal:** Reviewer can understand and run everything.
- [ ] README sections: overview, tech stack, run locally (Docker + without Docker), run tests, API endpoints table, example `curl` requests (signup → login → book → pay → webhook), DB schema (+ ER diagram in Mermaid), booking state machine, idempotency explanation, assumptions (from `memory.md` Decisions), future improvements.
- [ ] Final `pytest` + `ruff` run.
- [ ] Clean git history, push to GitHub.
- [ ] Prepare for interview: be able to explain each layer and make a small live change (e.g. add a new booking status or a new filter).

**Commit:** `docs: readme and submission`