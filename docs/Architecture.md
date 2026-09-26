# Architecture

## 1. Tech Stack
| Layer | Choice | Why |
|---|---|---|
| Language | Python 3.12 | Stable, well supported |
| Framework | Django 5.x | Mature ORM, migrations, admin |
| API | Django REST Framework (DRF) | Serializers, permissions, throttling, pagination built in |
| Auth | `djangorestframework-simplejwt` | Standard JWT for DRF |
| Database | PostgreSQL 16 | Required/preferred; row locks, constraints |
| DB driver | `psycopg[binary]` (v3) | Modern Postgres driver |
| Config | `django-environ` | Settings from `.env` |
| API docs | `drf-spectacular` | OpenAPI 3 + Swagger UI |
| Filtering | `django-filter` | Query filters on list endpoints |
| Tests | `pytest`, `pytest-django`, `pytest-cov`, `factory-boy` | Fast, readable tests + coverage |
| Lint/format | `ruff` | One tool for lint + format |
| Dependencies | `uv` (`pyproject.toml` + `uv.lock`) | Fast, reproducible installs (also in Docker/CI) |
| Container | Docker + docker-compose (`db` + `web`) | One-command setup |
| Server | `gunicorn` (in Docker) | Production-style WSGI server |
| Static files | `whitenoise` | Serves admin/Swagger assets from gunicorn, no nginx needed |
| Logging | stdlib `logging` + `apps/common/logging.py` | JSON lines with request id (no extra library) |
| CI | GitHub Actions | ruff, format check, migrations check, pytest + coverage on Postgres |
| Not used | Redis, Celery | Not needed at this load; listed as future improvements |

## 2. High-Level Architecture
```
            ┌──────────────┐        JWT         ┌──────────────────────────────────┐
  Client ──▶│   DRF Views  │───────────────────▶│  Permissions / Throttling        │
 (Postman,  └──────┬───────┘                    └──────────────────────────────────┘
  Swagger)         │ validated data (Serializers)
                   ▼
            ┌──────────────┐   all business rules, transactions, state machine
            │   Services   │   (apps/*/services.py)
            └──────┬───────┘
                   ▼
            ┌──────────────┐
            │ Django ORM   │──────────▶ PostgreSQL
            │   Models     │
            └──────────────┘

  Mock Payment Provider ──(HMAC signed)──▶ POST /payments/webhook/ ──▶ webhook service
```

**Layering rule:** Views are thin (parse request → call service → return response). Serializers validate shape/format. **Services** hold all business logic, transactions and state transitions. Models hold data + DB constraints + simple helpers.

## 3. Main Flows

### 3.1 Auth
```
signup → validate email/password → create User → 201
login  → email + password → simplejwt → {access, refresh}
every protected request → Authorization: Bearer <access>
```

### 3.2 Booking
```
POST /bookings/ {centre_id, test_id, appointment_at}
  → serializer validates types
  → booking_service.create_booking(user, ...)
       - centre exists & active?          else 400
       - CentreTest (centre, test) exists & active?  else 400
       - appointment in future, ≤ 90 days?  else 400
       - duplicate active booking?        else 409
       - amount = CentreTest.price (snapshot)
       - status = PENDING
  → 201 booking
```

### 3.3 Simulated Payment
```
POST /payments/ {booking_id, outcome?}   [Idempotency-Key header optional]
  → if Idempotency-Key already used by this user → return stored payment (200)
  → transaction.atomic():
       booking = Booking.objects.select_for_update().get(id, user=request.user)  else 404
       booking.status must be PENDING or FAILED                                  else 409
       outcome = given or random(PAYMENT_SUCCESS_RATE)
       payment = Payment(reference="pay_<uuid>", amount=booking.amount, status=outcome)
       apply_payment_result(booking, payment)   ← shared with webhook
  → 201 payment (+ booking status)
```

### 3.4 Webhook (idempotent)
```
POST /payments/webhook/ {event_id, payment_reference, status (SUCCESS|FAILED), amount}
  (no JWT, not throttled)
  → verify X-Webhook-Signature = "sha256=" + hex HMAC-SHA256(WEBHOOK_SECRET, raw body)
                                                                   else 401 INVALID_SIGNATURE
  → validate payload                                               else 400 VALIDATION_ERROR
  → process_webhook_event():
       event_id stored as PROCESSED/IGNORED? → attempts += 1, 200 DUPLICATE (no change)
         (stored as FAILED → NOT a duplicate: it is processed again below)
       payment = Payment by reference (plain read)                 else 404 PAYMENT_NOT_FOUND
       transaction.atomic():
         lock booking, THEN lock payment      (same order as create_payment → no deadlock)
         amount == payment.amount?                                 else 400 AMOUNT_MISMATCH
         claim the event row (select_for_update):
           exists PROCESSED/IGNORED (twin finished first) → attempts += 1, 200 DUPLICATE
           exists FAILED   → reuse it, attempts += 1 (retry)
           missing         → savepoint create (UNIQUE event_id);
                             IntegrityError (twin inserted) → 200 DUPLICATE
         payment already in this status  → event IGNORED "already_in_status"
         payment SUCCESS/FAILED (terminal) → event IGNORED "terminal_payment"
         else apply_payment_result()      → event PROCESSED
              booking CANCELLED + SUCCESS → payment SUCCESS, refund_required=True,
                                            booking stays CANCELLED, note "refund_required"
              booking CANCELLED + FAILED  → payment FAILED, booking stays CANCELLED
         event.status / note / attempts / processed_at saved
       UNEXPECTED exception (not a DomainError):
         whole transaction rolls back (booking/payment unchanged)
         → new transaction: event saved/updated as FAILED, note = exception class, attempts += 1
         → logged with traceback → 500 INTERNAL_ERROR (provider retries)
  → 200 {"event_id", "result": PROCESSED|IGNORED|DUPLICATE, "note"}

manage.py reprocess_webhooks [--max-attempts 5] [--dry-run]
  → re-runs every FAILED event from its stored payload through process_webhook_event()
    (signature already verified on receipt); skips events with attempts >= max;
    never touches PROCESSED/IGNORED events.
```
Nothing is stored for 4xx failures (bad signature, bad payload, unknown reference, amount mismatch), so the provider can retry after the problem is fixed. Only events that reach processing get a `webhook_events` row. The payment always follows the provider; the booking follows the user (a cancelled booking is never re-confirmed). Because processing is one transaction and the payment is terminal after SUCCESS/FAILED, a booking/payment can never change twice, even across retries.

### 3.5 Booking State Machine
```
            pay SUCCESS
 PENDING ─────────────────▶ CONFIRMED ──cancel──▶ CANCELLED
   │  │                         ▲
   │  │ pay FAILED              │ retry pay SUCCESS
   │  └──────────▶ FAILED ──────┘
   │                 │
   └──cancel──┐      └──cancel──┐
              ▼                 ▼
          CANCELLED         CANCELLED
```
Allowed transitions (single source of truth in `apps/bookings/state_machine.py`):
```
PENDING   → CONFIRMED, FAILED, CANCELLED
FAILED    → CONFIRMED, FAILED, CANCELLED   (retry allowed)
CONFIRMED → CANCELLED
CANCELLED → (terminal)
```
Any other transition raises `InvalidStateTransition` → `409`. A webhook `FAILED` for a `CONFIRMED` booking is ignored + logged (not an error).

## 4. Database Schema
```
users (custom User, email login)
  id PK, email UNIQUE (case-insensitive), full_name, phone NULL,
  password, is_active, is_staff, date_joined

diagnostic_centres
  id PK, name, address, city (indexed), pincode, is_active, created_at, updated_at

diagnostic_tests          (global catalog)
  id PK, code UNIQUE, name, description, sample_type NULL, is_active, created_at

centre_tests              (which centre offers which test, at what price)
  id PK, centre_id FK → diagnostic_centres, test_id FK → diagnostic_tests,
  price NUMERIC(10,2) CHECK (price > 0), is_active,
  UNIQUE (centre_id, test_id)

bookings
  id PK, user_id FK → users, centre_id FK, test_id FK,
  appointment_at TIMESTAMPTZ, amount NUMERIC(10,2) (snapshot of price),
  status VARCHAR (PENDING|CONFIRMED|FAILED|CANCELLED) indexed,
  created_at, updated_at
  -- partial UNIQUE (user_id, centre_id, test_id, appointment_at)
     WHERE status IN ('PENDING','CONFIRMED')

payments
  id PK, booking_id FK → bookings, reference UNIQUE ("pay_<uuid>"),
  amount NUMERIC(10,2) CHECK (amount > 0), status (PENDING|SUCCESS|FAILED),
  idempotency_key NULL, failure_reason, refund_required BOOL default false,
  user_id FK → users, created_at, updated_at
  -- UNIQUE (user_id, idempotency_key) where idempotency_key IS NOT NULL
  -- partial UNIQUE (booking_id) WHERE status IN ('PENDING','SUCCESS')
     (max one in-flight or successful payment per booking; FAILED retries allowed)

webhook_events
  id PK, event_id UNIQUE, payment_reference (indexed), payload JSONB,
  status (PROCESSED|IGNORED|FAILED), note (e.g. refund_required, already_in_status,
  terminal_payment), attempts INT default 1, received_at, processed_at NULL
```
Design notes:
- `bookings.amount` is a snapshot, so later price changes don't affect existing bookings.
- Money uses `DecimalField`, never float.
- All timestamps stored in UTC (`USE_TZ=True`); API accepts ISO-8601 with offset.
- FKs from bookings to centre/test use `on_delete=PROTECT` (never lose booking history).

## 5. Folder & File Structure
```
eve-diagnostics/
├── README.md
├── conftest.py                 # shared pytest fixtures (api_client, user, auth_client, admin_client)
├── Dockerfile                  # python:3.12-slim + uv, collectstatic, non-root, HEALTHCHECK
├── docker-compose.yml          # db (Postgres 16) + web (gunicorn, prod settings)
├── docker/
│   └── entrypoint.sh           # migrate → seed_data (if SEED_ON_START) → gunicorn
├── .dockerignore
├── .gitattributes              # *.sh eol=lf
├── .github/
│   └── workflows/ci.yml        # ruff, format check, migrations check, pytest + coverage
├── .env.example                # every setting, commented
├── .gitignore
├── pyproject.toml              # dependencies (uv) + ruff + pytest + coverage config
├── uv.lock                     # pinned dependency versions (uv)
├── manage.py
├── docs/                       # AI context files
│   ├── Prd.md
│   ├── Architecture.md
│   ├── Rules.md
│   ├── Phases.md
│   ├── EdgeCases.md            # edge case → handler → tests matrix
│   └── memory.md
├── config/                     # Django project
│   ├── __init__.py
│   ├── settings/
│   │   ├── __init__.py
│   │   ├── base.py             # shared; env-driven; LOGGING
│   │   ├── local.py
│   │   ├── test.py
│   │   └── prod.py             # DEBUG off, whitenoise, HTTPS settings from env
│   ├── urls.py
│   ├── wsgi.py
│   └── asgi.py
├── apps/
│   ├── common/                 # shared utilities, no models
│   │   ├── __init__.py
│   │   ├── exceptions.py       # domain exceptions + custom DRF exception handler
│   │   ├── pagination.py
│   │   ├── permissions.py      # IsAdminOrReadOnly
│   │   ├── logging.py          # JsonFormatter + request_id contextvar
│   │   ├── middleware.py       # RequestIdMiddleware (X-Request-ID)
│   │   ├── views.py            # /health/ + JSON handler404/handler500
│   │   └── models.py           # TimeStampedModel (abstract)
│   ├── accounts/
│   │   ├── models.py           # custom User + UserManager
│   │   ├── serializers.py
│   │   ├── views.py
│   │   ├── urls.py
│   │   ├── admin.py
│   │   └── tests/
│   ├── centres/
│   │   ├── models.py           # DiagnosticCentre, DiagnosticTest, CentreTest
│   │   ├── serializers.py
│   │   ├── filters.py
│   │   ├── views.py
│   │   ├── urls.py
│   │   ├── admin.py
│   │   ├── management/commands/seed_data.py
│   │   └── tests/
│   ├── bookings/
│   │   ├── models.py           # Booking, BookingStatus
│   │   ├── state_machine.py    # allowed transitions
│   │   ├── services.py         # create_booking, cancel_booking
│   │   ├── serializers.py
│   │   ├── views.py
│   │   ├── urls.py
│   │   ├── admin.py
│   │   └── tests/
│   └── payments/
│       ├── models.py           # Payment, WebhookEvent
│       ├── services.py         # create_payment, apply_payment_result
│       ├── webhook.py          # signature verify + process_webhook_event (+ FAILED/retry)
│       ├── serializers.py
│       ├── views.py
│       ├── urls.py
│       ├── admin.py
│       ├── management/commands/reprocess_webhooks.py
│       └── tests/
├── scripts/
│   └── send_webhook.py         # simulates provider: signs + sends webhook (for demo)
└── tests/                      # project-level tests (health, error shapes)
    ├── test_health.py
    └── test_error_responses.py
```

## 6. API Endpoints
| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/auth/signup/` | none | Register |
| POST | `/auth/login/` | none | Get JWT pair |
| POST | `/auth/token/refresh/` | none | Refresh access token |
| GET | `/auth/me/` | JWT | Current user |
| GET | `/centres/` | none | List centres (filters: city, test) |
| GET | `/centres/{id}/` | none | Centre + offered tests with prices |
| POST/PATCH | `/centres/`, `/centres/{id}/` | admin | Manage centres |
| POST | `/centres/{id}/tests/` | admin | Add/update test offering + price |
| GET | `/tests/` | none | Test catalog |
| POST/PATCH | `/tests/`, `/tests/{id}/` | admin | Manage catalog |
| POST | `/bookings/` | JWT | Create booking |
| GET | `/bookings/` | JWT | Own bookings (filter: status) |
| GET | `/bookings/{id}/` | JWT | Own booking detail |
| POST | `/bookings/{id}/cancel/` | JWT | Cancel own booking |
| POST | `/payments/` | JWT | Simulated payment |
| GET | `/payments/{reference}/` | JWT | Own payment detail |
| POST | `/payments/webhook/` | HMAC signature | Provider status update |
| GET | `/api/schema/`, `/api/docs/` | none | OpenAPI + Swagger UI |
| GET | `/health/` | none | Health check (DB ping) |

## 7. Error Response Format (all errors)
```json
{
  "error": {
    "code": "BOOKING_NOT_FOUND",
    "message": "Booking not found.",
    "details": {}
  }
}
```
Implemented via a custom DRF `EXCEPTION_HANDLER` in `apps/common/exceptions.py`. Validation errors put field errors in `details`.

## 8. Configuration (.env)
```
DJANGO_SETTINGS_MODULE=config.settings.local
SECRET_KEY=change-me
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1
DATABASE_URL=postgres://eve:eve@db:5432/eve
JWT_ACCESS_MINUTES=30
JWT_REFRESH_DAYS=7
WEBHOOK_SECRET=change-me-webhook
PAYMENT_SUCCESS_RATE=0.8
MAX_BOOKING_DAYS_AHEAD=90
```