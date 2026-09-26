import django_filters

from .models import Booking, BookingStatus


class BookingFilter(django_filters.FilterSet):
    # ChoiceFilter rejects unknown values, so ?status=WRONG returns 400
    status = django_filters.ChoiceFilter(choices=BookingStatus.choices)

    class Meta:
        model = Booking
        fields = ("status",)
