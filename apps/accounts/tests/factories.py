import factory

from apps.accounts.models import User

DEFAULT_PASSWORD = "StrongPass!123"


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User
        skip_postgeneration_save = True

    email = factory.Sequence(lambda n: f"user{n}@example.com")
    full_name = factory.Faker("name")
    # Hashed before insert (no post-generation save needed)
    password = factory.django.Password(DEFAULT_PASSWORD)
