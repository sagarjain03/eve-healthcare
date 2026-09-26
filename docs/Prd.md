# PRD — Diagnostic Test Booking & Payments Backend

## 1. Summary
A backend-only REST API service where users can sign up, browse diagnostic centres and the tests they offer, book a test for a date/time, and pay for it through a **simulated** payment service. A **payment webhook** receives status updates from a mock payment provider and must be **idempotent**.

This is an internship assignment for EVE Healthcare (SDE Intern — Backend). Evaluation values **clean design, correct data modelling, edge-case handling and tests** over feature count. A small, well-structured, tested solution beats a large messy one.

## 2. Goals
- Clean, predictable REST APIs with consistent error responses.
- Correct, normalized PostgreSQL schema with proper constraints.
- A clear booking state machine that can never be corrupted.
- An idempotent, safe webhook (duplicate / out-of-order events handled).
- Good automated test coverage of happy paths and edge cases.
- A README that lets a reviewer run the project in under 5 minutes.

## 3. Non-Goals
- No frontend / UI.
- No real payment gateway (Razorpay, Stripe, etc.).
- No refunds, invoices, notifications (email/SMS), or slot-capacity management.
- No multi-tenant / centre-staff dashboards.

## 4. Target Users
| User | Description | What they do |
|---|---|---|
| **Patient (regular user)** | Anyone who signs up | Browses centres & tests, creates bookings, pays, views/cancels own bookings |
| **Admin (staff user)** | `is_staff=True` user, created via `createsuperuser` or seed script | Creates/updates centres, tests and prices |
| **Payment provider (system)** | Simulated external service | Calls the webhook with payment status updates |
| **Reviewer (evaluator)** | EVE Healthcare engineer | Runs the project, reads README, runs tests, reads code |

## 5. Features

### F1. Authentication
- `POST /auth/signup/` — register with email, password, full name, phone (optional).
- `POST /auth/login/` — returns JWT access + refresh tokens.
- `POST /auth/token/refresh/` — new access token from refresh token.
- `GET /auth/me/` — current user profile.
- Validation: valid email, unique email (case-insensitive), password strength via Django password validators.
- All booking/payment endpoints require a valid JWT.

### F2. Diagnostic Centres & Tests
- A **centre** has: name, address, city, pincode, is_active.
- A **test** (catalog item) has: name, code, description, sample type (optional).
- A centre offers many tests; each offering has its **own price** (same test can cost differently at different centres).
- Public (read) endpoints:
  - `GET /centres/` — list, paginated, filter by `city`, `test` (test id or code).
  - `GET /centres/{id}/` — centre detail with offered tests and prices.
  - `GET /tests/` — list test catalog.
- Admin-only (write) endpoints:
  - `POST/PATCH /centres/`, `POST/PATCH /tests/`, `POST/PATCH /centres/{id}/tests/` (add/update offering price).

### F3. Booking System
- `POST /bookings/` — authenticated user books `{centre_id, test_id, appointment_at}`.
  - Amount is **always taken from the server-side price**, never from the client.
  - Booking starts in `PENDING`.
- `GET /bookings/` — list **own** bookings (paginated, filter by status).
- `GET /bookings/{id}/` — own booking detail (others' bookings → 404).
- `POST /bookings/{id}/cancel/` — cancel own booking.
- Booking fields: user, test, centre, appointment date/time, amount, status, timestamps.
- Statuses: `PENDING`, `CONFIRMED`, `FAILED`, `CANCELLED`.

### F4. Simulated Payment
- `POST /payments/` — `{booking_id, outcome?}` where `outcome` is `SUCCESS` | `FAILED` | `PENDING`.
  - `SUCCESS` → payment `SUCCESS`, booking `CONFIRMED`.
  - `FAILED` → payment `FAILED`, booking `FAILED` (user may retry with a new payment).
  - `PENDING` → payment and booking stay `PENDING`; the result arrives later via the webhook (F5). Simulates an async provider.
  - If `outcome` omitted → random `SUCCESS`/`FAILED` using `PAYMENT_SUCCESS_RATE` setting (default 0.8).
  - Only `PENDING`/`FAILED` bookings with a future appointment can be paid; at most one `PENDING`/`SUCCESS` payment per booking.
  - Supports optional `Idempotency-Key` header (per user, bound to one booking): same key → original payment (200), no second payment.
  - Creates a `Payment` record with a unique `reference` (`pay_<uuid4 hex>`); amount always comes from the booking.
- `GET /payments/` — own payments (filter `?booking=<id>`).
- `GET /payments/{reference}/` — own payment detail.

### F5. Payment Webhook
- `POST /payments/webhook/` — called by the simulated provider:
  `{event_id, payment_reference, status, amount}`.
- Authenticated by an HMAC-SHA256 signature header `X-Webhook-Signature` using `WEBHOOK_SECRET` (not JWT).
- **Idempotent**: the same `event_id` processed any number of times has the effect of processing it once. Duplicate → `200 {"detail": "already processed"}`.
- Safe against out-of-order events: a late `FAILED` must never downgrade a `CONFIRMED` booking.

### F6. Edge Cases (must be handled and tested)
| Case | Expected behaviour |
|---|---|
| Invalid / missing fields | `400` with field errors |
| No / invalid / expired JWT | `401` |
| Non-admin trying to create centre/test | `403` |
| Booking ID doesn't exist | `404` |
| Accessing another user's booking/payment | `404` (don't leak existence) |
| Test not offered by that centre, or centre inactive | `400` |
| Appointment in the past or > 90 days ahead | `400` |
| Duplicate active booking (same user, test, centre, slot) | `409` |
| Paying for CONFIRMED / CANCELLED booking | `409` |
| Retry payment after FAILED | Allowed |
| Cancel CONFIRMED booking | Allowed (refund out of scope, noted in README) |
| Cancel already CANCELLED booking | `409` |
| Same webhook event received twice | `200`, no state change second time |
| Webhook with bad signature | `401` |
| Webhook for unknown payment reference | `404` |
| Webhook amount ≠ payment amount | `400`, logged |
| Webhook FAILED after booking CONFIRMED | Ignored, logged |
| Concurrent payment requests for same booking | Only one succeeds (row lock) |

### F7. Bonus (in priority order)
1. Swagger / OpenAPI docs (`/api/docs/`)
2. Unit + integration tests (pytest)
3. Docker + docker-compose
4. Pagination (on all list endpoints)
5. Rate limiting (DRF throttling on auth + payments)
6. Structured (JSON) logging
7. Retry handling for webhook processing (event stored with status, failed events can be reprocessed)
8. Redis caching for centre list (only if time permits)
9. Celery (only if time permits — e.g. async webhook processing)

## 6. Success Criteria
- `docker compose up` starts the app + Postgres; migrations + seed run cleanly.
- All endpoints documented in Swagger and README with example requests.
- `pytest` passes; every edge case in F6 has at least one test.
- No endpoint can put a booking into an invalid state.