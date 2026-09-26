from django.urls import path
from rest_framework.routers import SimpleRouter

from .views import PaymentViewSet, WebhookView

router = SimpleRouter()
router.register("", PaymentViewSet, basename="payment")

urlpatterns = [
    # Listed first; the detail route only matches pay_<32 hex> anyway
    path("webhook/", WebhookView.as_view(), name="payment-webhook"),
    *router.urls,
]
