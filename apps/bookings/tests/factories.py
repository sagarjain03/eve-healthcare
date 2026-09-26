from datetime import timedelta

import factory
from django.utils import timezone

from apps.accounts.tests.factories import UserFactory
from apps.bookings.models import Booking
from apps.centres.tests.factories import CentreTestFactory


class BookingFactory(factory.django.DjangoModelFactory):
    """Booking for an existing offering; amount is the offering price (like the service)."""

    class Meta:
        model = Booking

    class Params:
        offering = factory.SubFactory(CentreTestFactory)

    user = factory.SubFactory(UserFactory)
    centre = factory.SelfAttribute("offering.centre")
    test = factory.SelfAttribute("offering.test")
    amount = factory.SelfAttribute("offering.price")
    appointment_at = factory.LazyFunction(lambda: timezone.now() + timedelta(days=2))
