from .base import *

# Fast hashing makes user-creating tests much quicker
PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']
