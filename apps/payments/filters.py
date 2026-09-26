import django_filters

from .models import Payment


class PaymentFilter(django_filters.FilterSet):
    booking = django_filters.NumberFilter(field_name="booking_id")

    class Meta:
        model = Payment
        fields = ("booking",)
