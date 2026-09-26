import logging

from django.db import IntegrityError, transaction

from apps.common.exceptions import EmailAlreadyExists

from .models import User

logger = logging.getLogger(__name__)


def register_user(*, email: str, password: str, full_name: str, phone: str | None = None) -> User:
    """Create a new user. Email is unique case-insensitively; a duplicate raises 409."""
    email = email.strip().lower()
    if User.objects.filter(email__iexact=email).exists():
        raise EmailAlreadyExists()

    try:
        # Savepoint so a unique-violation from a concurrent signup can be caught cleanly
        with transaction.atomic():
            user = User.objects.create_user(
                email=email, password=password, full_name=full_name, phone=phone
            )
    except IntegrityError as exc:
        raise EmailAlreadyExists() from exc

    logger.info("User registered", extra={"user_id": user.id})
    return user
