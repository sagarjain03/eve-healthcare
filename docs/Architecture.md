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
| Tests | `pytest`, `pytest-django`, `factory-boy` | Fast, readable tests |
| Lint/format | `ruff` | One tool for lint + format |
| Container | Docker + docker-compose | One-command setup |
| Server | `gunicorn` (in Docker) | Production-style WSGI server |
| Optional | `redis`, `django-redis`, `celery` | Only in bonus phase |

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
POST /payments/webhook/ {event_id, payment_reference, status, amount}
  → verify X-Webhook-Signature (HMAC-SHA256 of raw body)       else 401
  → validate payload                                            else 400
  → transaction.atomic():
       try: WebhookEvent.objects.create(event_id=..., payload=...)   (UNIQUE event_id)
       except IntegrityError: return 200 "already processed"
       payment = Payment.select_for_update().get(reference)    else 404
       amount matches?                                         else 400
       booking = Booking.select_for_update().get(payment.booking_id)
       apply_payment_result(booking, payment, new_status)
       event.status = PROCESSED
  → 200
```

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
  amount NUMERIC(10,2), status (PENDING|SUCCESS|FAILED),
  idempotency_key NULL, user_id FK → users,
  created_at, updated_at
  -- UNIQUE (user_id, idempotency_key) where idempotency_key IS NOT NULL
  -- partial UNIQUE (booking_id) WHERE status = 'SUCCESS'   (max one successful payment per booking)

webhook_events
  id PK, event_id UNIQUE, payment_reference, payload JSONB,
  status (RECEIVED|PROCESSED|IGNORED|FAILED), error TEXT NULL,
  attempts INT default 0, received_at, processed_at NULL
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
├── Dockerfile
├── docker-compose.yml
├── .env.example
├── .gitignore
├── pyproject.toml              # dependencies (uv) + ruff + pytest config
├── uv.lock                     # pinned dependency versions (uv)
├── manage.py
├── docs/                       # AI context files
│   ├── Prd.md
│   ├── Architecture.md
│   ├── Rules.md
│   ├── Phases.md
│   └── memory.md
├── config/                     # Django project
│   ├── __init__.py
│   ├── settings/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── local.py
│   │   └── test.py
│   ├── urls.py
│   ├── wsgi.py
│   └── asgi.py
├── apps/
│   ├── common/                 # shared utilities, no models
│   │   ├── __init__.py
│   │   ├── exceptions.py       # domain exceptions + custom DRF exception handler
│   │   ├── pagination.py
│   │   ├── permissions.py      # IsAdminOrReadOnly
│   │   ├── logging.py          # JSON log formatter
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
│       ├── webhook.py          # signature verify + process_webhook_event
│       ├── serializers.py
│       ├── views.py
│       ├── urls.py
│       ├── admin.py
│       └── tests/
├── scripts/
│   └── send_webhook.py         # simulates provider: signs + sends webhook (for demo)
└── tests/
    └── conftest.py             # shared fixtures (api_client, user, auth_client, admin)
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