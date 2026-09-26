import django_filters
from django.db.models import Q

from .models import DiagnosticCentre


class CentreFilter(django_filters.FilterSet):
    city = django_filters.CharFilter(lookup_expr="iexact")
    test = django_filters.CharFilter(method="filter_by_test")

    class Meta:
        model = DiagnosticCentre
        fields = ("city", "test")

    def filter_by_test(self, queryset, name, value):
        """Centres with an ACTIVE offering of the test, given its numeric id or code."""
        value = value.strip()
        match = Q(offerings__test__code__iexact=value)
        if value.isdigit():
            match |= Q(offerings__test_id=int(value))
        # One filter() call so all conditions apply to the same offering row
        return queryset.filter(
            match, offerings__is_active=True, offerings__test__is_active=True
        ).distinct()
