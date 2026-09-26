# Rules for the AI Assistant

Read this file, `Prd.md`, `Architecture.md` and `memory.md` before starting any work.

## 0. Working Mode — Developer Writes, AI Debugs
**The developer writes the code themselves, phase by phase. The AI's job is to help fix errors and explain, not to build features.**

1. **Read `memory.md` first** every session to know the current phase and file.
2. **Do NOT write new features, new files, or whole phases** unless the developer explicitly asks ("write this for me").
3. When given an error:
   - First explain **in simple words why** the error happened (root cause, not just the symptom).
   - Then give the **smallest possible fix**, touching only the lines/files involved.
   - Show the fix as a diff or the exact changed lines, so the developer can see and understand it.
   - If there are multiple possible causes, list them in order of likelihood and ask for the extra info needed (full traceback, file content, command run).
4. **Never rewrite, refactor or "clean up" code that isn't part of the error.** Don't rename things, reorder files, or change style unasked.
5. **Don't add new libraries** to fix an error without asking first.
6. If the developer's code breaks a rule in this file or the design in `Architecture.md`, **point it out** briefly, but let the developer decide.
7. If a fix would change the DB schema, a migration, or the booking state machine, **warn first** before applying.
8. After fixing, suggest how to verify it (the command/test to run).
9. When asked, update `memory.md` (errors fixed go under "Known Issues / TODO" or "Log"). Otherwise the developer maintains it.
10. Keep every explanation short and interview-ready — the developer must be able to explain every line in a live interview.

### Developer's own checklist (per phase)
- Work on **one phase at a time** (see `Phases.md`).
- Write tests with the feature; phase is done when `pytest` passes and `ruff check .` is clean.
- Update `memory.md` and commit (Conventional Commits: `feat:`, `fix:`, `test:`, `docs:`, `chore:`).
- Record assumptions in `memory.md` → "Decisions" (goes into README later).

## 1. Libraries — USE
- Django 5.x, Django REST Framework
- `djangorestframework-simplejwt` for JWT
- `psycopg[binary]` (v3) for PostgreSQL
- `django-environ` for settings
- `drf-spectacular` for OpenAPI/Swagger
- `django-filter` for list filtering
- `pytest`, `pytest-django`, `factory-boy` for tests
- `ruff` for lint/format
- `gunicorn` for serving in Docker
- Standard library: `uuid`, `hmac`, `hashlib`, `secrets`, `decimal`, `logging`, `random`

## 2. Libraries — AVOID
- ❌ Any library not listed above without asking first (no random packages "to make it easier").
- ❌ `djangorestframework-jwt` / `django-rest-auth` / `dj-rest-auth` / `djoser` (outdated or unnecessary).
- ❌ `psycopg2` (use psycopg v3).
- ❌ SQLite anywhere, including tests — Postgres features (row locks, partial unique indexes) are required.
- ❌ Real payment SDKs (stripe, razorpay).
- ❌ `float` for money — always `Decimal` / `DecimalField(max_digits=10, decimal_places=2)`.
- ❌ Celery/Redis before the bonus phase.
- ❌ GraphQL, Django Ninja, async views — keep it plain DRF.

## 3. Code Structure Rules
- **Custom User model must exist before the first migration** (`AUTH_USER_MODEL = "accounts.User"`). Never switch later.
- **Thin views, fat services.** Views: parse → call service → serialize response. No business logic in views or serializers.
- Business rules + state changes live in `apps/<app>/services.py`.
- Booking status changes go **only** through `apps/bookings/state_machine.py`. Never assign `booking.status = ...` directly elsewhere.
- Payment result is applied **only** via `payments.services.apply_payment_result()` — used by both `/payments/` and the webhook.
- Use `TextChoices` for statuses; no magic strings.
- Type hints on all service functions. Short docstrings on services explaining rules.
- One responsibility per function; functions ideally < 40 lines.
- Use `select_related` / `prefetch_related` on list endpoints (no N+1 queries).
- Settings come from env via `django-environ`; **no secrets hard-coded**.
- Keep the URL paths exactly as in `Architecture.md` (the assignment requires `POST /payments/` and `POST /payments/webhook/`).

## 4. Database Rules
- Enforce integrity **in the DB**, not only in Python: `UniqueConstraint`, `CheckConstraint`, partial unique constraints (see Architecture schema).
- Use `on_delete=PROTECT` for booking → centre/test and payment → booking.
- Use `transaction.atomic()` + `select_for_update()` for anything that reads-then-updates booking/payment state.
- Never edit a migration that has already been applied; create a new one.
- Add `db_index=True` on columns used in filters (`status`, `city`, `appointment_at`).
- Booking `amount` is copied from `CentreTest.price` at creation time — never accept amount from the client.

## 5. Error Handling Rules
- All errors return the standard shape:
  `{"error": {"code": "SNAKE_UPPER_CODE", "message": "Human readable.", "details": {}}}`
- Define domain exceptions in `apps/common/exceptions.py`, each with `status_code` and `code`, e.g.:
  - `NotFound` (404), `Conflict` (409), `InvalidStateTransition` (409), `BusinessRuleViolation` (400), `InvalidSignature` (401).
- Services raise domain exceptions; the custom DRF exception handler converts them. Views don't build error responses manually.
- Status codes:
  - `400` validation / business rule, `401` no/invalid auth, `403` authenticated but not allowed, `404` not found **or not owned by user**, `409` state conflict / duplicate, `429` throttled, `500` unexpected only.
- **Never return 500 for user mistakes.** Never leak stack traces or internal details in responses (`DEBUG=False` in Docker).
- Catch `IntegrityError` only where it's expected (webhook event_id, idempotency key, duplicate booking) and map it to a clear response.
- Don't use bare `except:` or `except Exception: pass`. Log unexpected errors with context and re-raise.

## 6. Security Rules
- Users can only see/modify their **own** bookings and payments — always filter querysets by `request.user`.
- Admin-only writes use `IsAdminUser` / `IsAdminOrReadOnly`.
- Webhook is authenticated by **HMAC-SHA256 signature** of the raw request body with `WEBHOOK_SECRET`, compared with `hmac.compare_digest`. No JWT on webhook.
- Passwords validated by Django `AUTH_PASSWORD_VALIDATORS`; never log passwords, tokens, or full webhook secrets.
- Emails normalized to lowercase before saving/lookup.

## 7. Idempotency Rules (critical)
- Webhook: insert `WebhookEvent(event_id=...)` inside the transaction first; unique violation ⇒ already processed ⇒ return `200` without changes.
- `/payments/`: optional `Idempotency-Key` header, unique per user; repeated key returns the original payment.
- DB guarantees max **one SUCCESS payment per booking** (partial unique constraint).
- Out-of-order events: a `FAILED` status can never override `CONFIRMED`/`SUCCESS`; log and mark event `IGNORED`.

## 8. Testing Rules
- `pytest` + `pytest-django` + `factory-boy`; tests run against PostgreSQL.
- Test file per area: `test_models.py`, `test_services.py`, `test_api.py`.
- Every edge case in `Prd.md` §F6 needs at least one test.
- Test names describe behaviour: `test_duplicate_webhook_event_does_not_change_state`.
- Payment tests always pass an explicit `outcome` (no randomness in tests); mock `random` if testing default.
- Include at least one concurrency-style test for the webhook/payment path (e.g. process same event twice, pay twice).
- No test depends on another test's data or order.

## 9. Logging Rules
- Use `logging.getLogger(__name__)`; no `print()`.
- Log key events at INFO: booking created/cancelled, payment created, webhook received/processed/ignored/duplicate.
- Include IDs in log `extra` (booking_id, payment_reference, event_id, user_id).
- Bonus phase: JSON formatter in `apps/common/logging.py`.

## 10. Documentation Rules
- Every endpoint gets `@extend_schema` (drf-spectacular) with request/response examples where helpful.
- README is written/updated in the final phase but decisions are collected in `memory.md` as you go.