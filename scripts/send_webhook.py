"""Simulate the payment provider: sign and send a webhook event (standard library only).

Usage (server must be running):
    uv run python scripts/send_webhook.py --reference pay_<32 hex> --status SUCCESS --amount 400.00
    uv run python scripts/send_webhook.py --reference pay_... --status SUCCESS --amount 400.00 --times 5
    uv run python scripts/send_webhook.py --reference pay_... --status FAILED --amount 400.00 --bad-signature

--times N sends the SAME event (same event_id) N times, to show idempotency.
The secret comes from --secret, else the WEBHOOK_SECRET env var, else the project's .env file.
"""

import argparse
import hashlib
import hmac
import json
import os
import urllib.error
import urllib.request
import uuid
from pathlib import Path

DEFAULT_URL = "http://localhost:8000/payments/webhook/"
ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


def secret_from_env() -> str | None:
    if os.environ.get("WEBHOOK_SECRET"):
        return os.environ["WEBHOOK_SECRET"]
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            if line.startswith("WEBHOOK_SECRET="):
                return line.split("=", 1)[1].strip()
    return None


def sign(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def send(url: str, body: bytes, signature: str) -> tuple[int, str]:
    request = urllib.request.Request(url, data=body, method="POST")
    request.add_header("Content-Type", "application/json")
    request.add_header("X-Webhook-Signature", signature)
    try:
        with urllib.request.urlopen(request) as response:
            return response.status, response.read().decode()
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode()


def main() -> None:
    parser = argparse.ArgumentParser(description="Send a signed payment webhook event.")
    parser.add_argument("--reference", required=True, help="Payment reference (pay_...)")
    parser.add_argument("--status", required=True, choices=["SUCCESS", "FAILED"])
    parser.add_argument("--amount", required=True, help='Payment amount, e.g. "400.00"')
    parser.add_argument("--event-id", default=None, help="Default: random evt_<uuid>")
    parser.add_argument("--times", type=int, default=1, help="Send the SAME event N times")
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--secret", default=None, help="Default: WEBHOOK_SECRET env or .env")
    parser.add_argument("--bad-signature", action="store_true", help="Send a wrong signature")
    args = parser.parse_args()

    secret = args.secret or secret_from_env()
    if not secret:
        parser.error("No secret: pass --secret or set WEBHOOK_SECRET (env or .env).")

    payload = {
        "event_id": args.event_id or f"evt_{uuid.uuid4().hex}",
        "payment_reference": args.reference,
        "status": args.status,
        "amount": args.amount,
    }
    body = json.dumps(payload).encode()
    signature = "sha256=" + "0" * 64 if args.bad_signature else sign(secret, body)

    print(f"event_id={payload['event_id']} status={args.status} amount={args.amount}")
    for attempt in range(1, args.times + 1):
        status_code, text = send(args.url, body, signature)
        print(f"  send {attempt}/{args.times}: HTTP {status_code} {text}")


if __name__ == "__main__":
    main()
