from django.contrib import admin

from .models import Payment, WebhookEvent


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    """View-only: payments change only through the payment service."""

    list_display = (
        "reference", "booking", "user", "amount", "status", "refund_required", "created_at"
    )
    list_filter = ("status", "refund_required")
    search_fields = ("reference", "user__email", "idempotency_key")
    list_select_related = ("booking", "user")
    readonly_fields = (
        "reference",
        "booking",
        "user",
        "amount",
        "status",
        "failure_reason",
        "refund_required",
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


@admin.register(WebhookEvent)
class WebhookEventAdmin(admin.ModelAdmin):
    """View-only audit trail of provider events."""

    list_display = ("event_id", "payment_reference", "status", "note", "attempts", "received_at")
    list_filter = ("status",)
    search_fields = ("event_id", "payment_reference")
    readonly_fields = (
        "event_id",
        "payment_reference",
        "payload",
        "status",
        "note",
        "attempts",
        "received_at",
        "processed_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
