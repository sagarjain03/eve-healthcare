"""Production settings (used by the Docker image).

Everything security-related comes from env so the same image works in two modes:

* Local Docker over plain HTTP (defaults below): no SSL redirect, non-secure cookies, no HSTS.
* Real HTTPS deployment (behind a TLS-terminating proxy/load balancer) — set:
      SECURE_SSL_REDIRECT=true
      SESSION_COOKIE_SECURE=true
      CSRF_COOKIE_SECURE=true
      SECURE_HSTS_SECONDS=31536000        (start small, e.g. 3600, then raise)
      SECURE_HSTS_INCLUDE_SUBDOMAINS=true
      SECURE_HSTS_PRELOAD=true            (only if you intend to submit the domain for preload)
  and ALLOWED_HOSTS to your real domain(s). With these, `check --deploy` shows 0 warnings.
"""

from django.core.exceptions import ImproperlyConfigured

from .base import *
from .base import BASE_DIR, LOGGING, MIDDLEWARE, env

DEBUG = False

ALLOWED_HOSTS = env.list("ALLOWED_HOSTS")
if not ALLOWED_HOSTS:
    raise ImproperlyConfigured("ALLOWED_HOSTS must be set in production.")

# Static files: collected at image build time, served by whitenoise (admin + Swagger UI assets)
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}
MIDDLEWARE = [*MIDDLEWARE]
MIDDLEWARE.insert(
    MIDDLEWARE.index("django.middleware.security.SecurityMiddleware") + 1,
    "whitenoise.middleware.WhiteNoiseMiddleware",
)

# HTTPS / security (see module docstring for what to flip in a real deployment)
SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=False)
SESSION_COOKIE_SECURE = env.bool("SESSION_COOKIE_SECURE", default=False)
CSRF_COOKIE_SECURE = env.bool("CSRF_COOKIE_SECURE", default=False)
SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=0)
SECURE_HSTS_INCLUDE_SUBDOMAINS = env.bool("SECURE_HSTS_INCLUDE_SUBDOMAINS", default=False)
SECURE_HSTS_PRELOAD = env.bool("SECURE_HSTS_PRELOAD", default=False)
# Trust the proxy's X-Forwarded-Proto so Django knows the original request was HTTPS
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_CONTENT_TYPE_NOSNIFF = True

# JSON logs by default in production (one object per line, easy to ship/grep)
LOGGING["handlers"]["console"]["formatter"] = env("LOG_FORMAT", default="json")
