from django.contrib import admin

from .models import Booking


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "test", "centre", "appointment_at", "amount", "status")
    list_filter = ("status",)
    search_fields = ("user__email", "centre__name", "test__code")
    list_select_related = ("user", "centre", "test")
    # Status only changes via the state machine; amount is a price snapshot
    readonly_fields = ("status", "amount", "created_at", "updated_at")

    def has_add_permission(self, request):
        # Bookings are created through the API (service rules + price snapshot), not admin
        return False
