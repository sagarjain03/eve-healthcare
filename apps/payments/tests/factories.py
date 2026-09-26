import uuid

import factory

from apps.bookings.tests.factories import BookingFactory
from apps.payments.models import Payment


class PaymentFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Payment

    booking = factory.SubFactory(BookingFactory)
    user = factory.SelfAttribute("booking.user")
    amount = factory.SelfAttribute("booking.amount")
    reference = factory.LazyFunction(lambda: f"pay_{uuid.uuid4().hex}")
