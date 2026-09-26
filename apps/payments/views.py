from django.http import Http404
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
    extend_schema_view,
)
from rest_framework import mixins, status, viewsets
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.common.exceptions import NotFound

from .filters import PaymentFilter
from .models import Payment
from .serializers import PaymentCreateSerializer, PaymentSerializer
from .services import create_payment

IDEMPOTENCY_HEADER = "Idempotency-Key"
IDEMPOTENCY_KEY_MAX_LENGTH = 100


def _idempotency_key(request) -> str | None:
    key = request.headers.get(IDEMPOTENCY_HEADER, "").strip()
    if len(key) > IDEMPOTENCY_KEY_MAX_LENGTH:
        raise ValidationError(
            {IDEMPOTENCY_HEADER: [f"Must be at most {IDEMPOTENCY_KEY_MAX_LENGTH} characters."]}
        )
    return key or None


@extend_schema_view(
    list=extend_schema(
        tags=["Payments"],
        summary="List my payments",
        description="Only the caller's payments, newest first. Filter with `?booking=<id>`.",
    ),
    retrieve=extend_schema(
        tags=["Payments"],
        summary="My payment detail",
        responses={
            200: PaymentSerializer,
            404: OpenApiResponse(description="PAYMENT_NOT_FOUND (missing or not yours)."),
        },
    ),
)
class PaymentViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = (IsAuthenticated,)
    http_method_names = ("get", "post", "head", "options")
    filter_backends = (DjangoFilterBackend,)
    filterset_class = PaymentFilter
    lookup_field = "reference"
    # Only real references match, so this can never shadow /payments/webhook/ (Phase 6)
    lookup_value_regex = r"pay_[0-9a-f]{32}"

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):  # schema generation has no real user
            return Payment.objects.none()
        return Payment.objects.filter(user=self.request.user).select_related("booking")

    def get_serializer_class(self):
        if self.action == "create":
            return PaymentCreateSerializer
        return PaymentSerializer

    def get_throttles(self):
        # Only creating payments is rate limited; reads are not
        self.throttle_scope = "payments" if self.action == "create" else None
        return super().get_throttles()

    def get_object(self):
        try:
            return super().get_object()
        except Http404 as exc:
            raise NotFound("Payment not found.", code="PAYMENT_NOT_FOUND") from exc

    @extend_schema(
        tags=["Payments"],
        summary="Pay for my booking (simulated)",
        description=(
            "`outcome`: SUCCESS → booking CONFIRMED; FAILED → booking FAILED (retry allowed); "
            "PENDING → both stay PENDING until the webhook reports the result; omitted → random "
            "using PAYMENT_SUCCESS_RATE. Returns 201 for a new payment, 200 for an "
            "Idempotency-Key replay. Amount always comes from the booking."
        ),
        parameters=[
            OpenApiParameter(
                IDEMPOTENCY_HEADER,
                OpenApiTypes.STR,
                location=OpenApiParameter.HEADER,
                required=False,
                description="Optional (max 100 chars). Same key + same booking returns the "
                "original payment instead of charging again.",
            )
        ],
        request=PaymentCreateSerializer,
        responses={
            200: PaymentSerializer,
            201: PaymentSerializer,
            400: OpenApiResponse(description="VALIDATION_ERROR or APPOINTMENT_ALREADY_PASSED"),
            404: OpenApiResponse(description="BOOKING_NOT_FOUND"),
            409: OpenApiResponse(
                description="BOOKING_NOT_PAYABLE, PAYMENT_IN_PROGRESS or IDEMPOTENCY_KEY_REUSED"
            ),
            429: OpenApiResponse(description="THROTTLED (20/min)"),
        },
        examples=[
            OpenApiExample(
                "Success", value={"booking_id": 1, "outcome": "SUCCESS"}, request_only=True
            ),
            OpenApiExample(
                "Failed", value={"booking_id": 1, "outcome": "FAILED"}, request_only=True
            ),
            OpenApiExample(
                "Pending (async, settle via webhook)",
                value={"booking_id": 1, "outcome": "PENDING"},
                request_only=True,
            ),
        ],
    )
    def create(self, request):
        idempotency_key = _idempotency_key(request)
        serializer = PaymentCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payment, created = create_payment(
            user=request.user, idempotency_key=idempotency_key, **serializer.validated_data
        )
        return Response(
            PaymentSerializer(payment).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )
