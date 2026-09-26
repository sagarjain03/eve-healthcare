import re
import uuid

from .logging import request_id_var

REQUEST_ID_HEADER = "X-Request-ID"
# Accept a caller's id only if it's short and safe to put in logs/headers
_VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9-]{1,64}$")


class RequestIdMiddleware:
    """Give every request an id (reuse a sane incoming X-Request-ID, else a new uuid4 hex),
    expose it to log records via a contextvar, and echo it in the response header."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        incoming = request.headers.get(REQUEST_ID_HEADER, "")
        request_id = incoming if _VALID_REQUEST_ID.match(incoming) else uuid.uuid4().hex
        request.request_id = request_id
        token = request_id_var.set(request_id)
        try:
            response = self.get_response(request)
        finally:
            request_id_var.reset(token)
        response[REQUEST_ID_HEADER] = request_id
        return response
