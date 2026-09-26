# Phases

Work through phases **in order**. Each phase ends with: tests passing, `ruff` clean, `memory.md` updated, and a git commit.
Estimated total: ~4–6 hours of focused work (vibe-coded).

---

## Phase 0 — Project Setup
**Goal:** Empty but runnable Django project with Postgres.
- [x] Create folder structure from `Architecture.md` §5.
- [x] `pyproject.toml` + `uv.lock` (dependencies via uv, ruff + pytest config), `.gitignore`, `.env.example`.
- [x] Django project in `config/` with split settings (`base`, `local`, `test`).
- [x] `docker-compose.yml` with a `db` service (Postgres 16) — app service comes in Phase 8.
- [x] Create empty apps: `common`, `accounts`, `centres`, `bookings`, `payments` under `apps/`.
- [x] DRF + simplejwt + drf-spectacular + django-filter configured in settings.
- [x] `/health/` endpoint (checks DB connection).
- [x] `/api/docs/` Swagger loads.
- [x] `conftest.py` (project root) with `api_client` fixture; one test for `/health/`.

**Done when:** `docker compose up db` + `python manage.py runserver` works, `/api/docs/` opens, `pytest` passes.
**Commit:** `chore: project setup with django, drf and postgres`

---

## Phase 1 — Common Layer + Custom User
**Goal:** Shared building blocks and the user model (before any other migration!).
- [x] `apps/common/models.py` — `TimeStampedModel` (abstract).
- [x] `apps/common/exceptions.py` — domain exceptions + custom DRF exception handler (standard error shape).
- [x] `apps/common/pagination.py` — default page-number pagination (page size 20, max 100).
- [x] `apps/common/permissions.py` — `IsAdminOrReadOnly`.
- [x] `apps/accounts/models.py` — custom `User` (email as username) + `UserManager`.
- [x] `AUTH_USER_MODEL` set; first migrations created.
- [x] Register User in admin.
- [x] Tests: user manager creates user/superuser, email normalized, exception handler output shape.

**Done when:** migrations apply on fresh DB, tests pass.
**Commit:** `feat: common utilities and custom user model`

---

## Phase 2 — Authentication APIs
**Goal:** Signup, login, refresh, me.
- [x] `SignupSerializer` (email unique case-insensitive, Django password validators, full_name required).
- [x] Views + URLs: `/auth/signup/`, `/auth/login/`, `/auth/token/refresh/`, `/auth/me/`.
- [x] JWT lifetimes from env.
- [x] Throttle on signup/login (scoped throttle, e.g. 10/min).
- [x] Swagger docs for all auth endpoints.
- [x] Tests: signup success, duplicate email (409 or 400 — decide + record), weak password, invalid email, login success, wrong password (401), `/me` without token (401), with expired/invalid token (401).

**Done when:** can signup → login → call `/auth/me/` via Swagger.
**Commit:** `feat: jwt authentication`

---

## Phase 3 — Centres & Tests
**Goal:** Catalog of centres, tests and prices.
- [x] Models: `DiagnosticCentre`, `DiagnosticTest`, `CentreTest` (unique centre+test, price > 0 check).
- [x] Serializers: list/detail (detail includes offered tests + prices).
- [x] Viewsets with `IsAdminOrReadOnly`; `/centres/{id}/tests/` action for adding/updating an offering.
- [x] Filters: centres by `city`, by `test` (id or code).
- [x] Pagination on lists; `prefetch_related` to avoid N+1.
- [x] Management command `seed_data` — admin user, 3–4 centres, 6–8 tests, prices.
- [x] Admin registration.
- [x] Tests: public list/detail, filters, non-admin POST → 403, admin POST → 201, duplicate offering, invalid price.

**Done when:** `python manage.py seed_data` works and centres show in Swagger.
**Commit:** `feat: diagnostic centres and tests catalog`

---

## Phase 4 — Bookings
**Goal:** Users can create, list, view and cancel their own bookings.
- [x] `Booking` model + `BookingStatus` choices + partial unique constraint for active duplicates.
- [x] `state_machine.py` — `ALLOWED_TRANSITIONS` + `transition(booking, new_status)` raising `InvalidStateTransition`.
- [x] `services.create_booking()` — all validation rules from `Architecture.md` §3.2, amount snapshot.
- [x] `services.cancel_booking()` — with `select_for_update`.
- [x] Endpoints: `POST/GET /bookings/`, `GET /bookings/{id}/`, `POST /bookings/{id}/cancel/`.
- [x] Querysets always filtered by `request.user`.
- [x] Tests: create success (amount = server price), test not offered at centre, inactive centre, past date, too far ahead, duplicate active booking (409), other user's booking (404), non-existent id (404), cancel twice (409), unauthenticated (401), every state-machine transition (valid + invalid).

**Done when:** full booking lifecycle (without payment) works and is tested.
**Commit:** `feat: booking system with state machine`

---

## Phase 5 — Simulated Payments
**Goal:** `POST /payments/` updates the booking.
- [x] `Payment` model (unique reference, one SUCCESS per booking constraint, unique user+idempotency_key).
- [x] `services.create_payment()` — lock booking, check status, decide outcome, create payment.
- [x] `services.apply_payment_result()` — the **single** function that maps payment status → booking status (used again by webhook).
- [x] `Idempotency-Key` header support.
- [x] Endpoints: `POST /payments/`, `GET /payments/{reference}/`.
- [x] Throttle on payments.
- [x] Tests: success → CONFIRMED, failed → FAILED, retry after FAILED → CONFIRMED, pay CONFIRMED booking (409), pay CANCELLED (409), other user's booking (404), invalid booking id (404/400), same Idempotency-Key twice returns same payment, random outcome (mocked).

**Done when:** booking → pay → confirmed flow works end-to-end.
**Commit:** `feat: simulated payment service`

---

## Phase 6 — Idempotent Webhook
**Goal:** Safe provider callbacks.
- [x] `WebhookEvent` model (unique `event_id`, JSONB payload, status, attempts, error).
- [x] `webhook.py` — `verify_signature(raw_body, header)` + `process_webhook_event(payload)`.
- [x] View: `POST /payments/webhook/` (no JWT, `AllowAny` + signature check, throttle exempt or high limit).
- [x] Rules: duplicate event → 200 no-op; unknown payment → 404; amount mismatch → 400; late FAILED after SUCCESS → IGNORED.
- [x] `scripts/send_webhook.py` — CLI that builds + signs + sends a webhook (for demo and README).
- [x] Tests: valid event updates booking, same event twice → one state change + one event row, bad signature (401), missing signature (401), unknown reference (404), amount mismatch (400), FAILED after CONFIRMED ignored, two different events for same payment handled correctly.

**Done when:** sending the same webhook 5 times leaves exactly one event row and correct booking state.
**Commit:** `feat: idempotent payment webhook`

---

## Phase 7 — Edge-Case Hardening & Test Review
**Goal:** Nothing in `Prd.md` §F6 is untested.
- [x] Go through §F6 table row by row; add missing tests.
- [x] Check every error response follows the standard shape.
- [x] Check no N+1 queries on list endpoints (`django_assert_num_queries`).
- [x] Check all list endpoints paginated.
- [x] Add test coverage report (`pytest --cov`) — aim ≥ 85% on services.

**Done when:** all F6 rows have a passing test.
**Commit:** `test: edge case coverage`

---

## Phase 8 — Docker & Bonus Engineering
**Goal:** One-command run + selected bonuses.
- [x] `Dockerfile` (python:3.12-slim, non-root user, gunicorn).
- [x] `docker-compose.yml`: `web` + `db` (healthcheck), web runs migrate + seed on start (entrypoint script).
- [x] Structured JSON logging (`apps/common/logging.py`).
- [x] Rate limiting verified (auth, payments).
- [x] Webhook retry handling: events stored as `FAILED` with error + attempts; management command `reprocess_webhooks` retries them.
- [ ] ~~(Optional) Redis cache for `GET /centres/`~~ — **skipped by decision** (not needed at this load; README "Future improvements").
- [ ] ~~(Optional) Celery for async webhook processing~~ — **skipped by decision** (FAILED + `reprocess_webhooks` covers retries; README "Future improvements").

**Done when:** fresh clone → `cp .env.example .env` → `docker compose up --build` → Swagger works.
**Commit:** `feat: docker, structured logging and webhook retries`

---

## Phase 9 — README & Submission
**Goal:** Reviewer can understand and run everything.
- [x] README sections: overview, tech stack, run locally (Docker + without Docker), run tests, API endpoints table, example `curl` requests (signup → login → book → pay → webhook), DB schema (+ ER diagram in Mermaid), booking state machine, idempotency explanation, assumptions (from `memory.md` Decisions), future improvements. *(Verified from a clean clone.)*
- [x] Final `pytest` + `ruff` run.
- [ ] Clean git history, push to GitHub. *(History is one commit per phase; push is the developer's step — replace `<GITHUB_USER>/<REPO>` in the README CI badge.)*
- [ ] Prepare for interview: be able to explain each layer and make a small live change (e.g. add a new booking status or a new filter). *(Developer.)*

**Commit:** `docs: readme and submission`
