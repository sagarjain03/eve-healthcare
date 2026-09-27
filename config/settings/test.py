from .base import *

# Fast hashing makes user-creating tests much quicker
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# Deterministic regardless of .env / CI env: the playground route exists in tests
PLAYGROUND_ENABLED = True
