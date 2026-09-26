from django.contrib import admin

from .models import Payment


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    """View-only: payments change only through the payment service."""

    list_display = ("reference", "booking", "user", "amount", "status", "created_at")
    list_filter = ("status",)
    search_fields = ("reference", "user__email", "idempotency_key")
    list_select_related = ("booking", "user")
    readonly_fields = (
        "reference",
        "booking",
        "user",
        "amount",
        "status",
        "failure_reason",
        "idempotency_key",
        "created_at",
        "updated_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
