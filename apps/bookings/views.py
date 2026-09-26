from django.http import Http404
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiResponse,
    extend_schema,
    extend_schema_view,
)
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.common.exceptions import NotFound

from .filters import BookingFilter
from .models import Booking
from .serializers import BookingCreateSerializer, BookingSerializer
from .services import cancel_booking, create_booking


@extend_schema_view(
    list=extend_schema(
        tags=["Bookings"],
        summary="List my bookings",
        description="Only the caller's bookings, newest first. Filter with `?status=`.",
    ),
    retrieve=extend_schema(
        tags=["Bookings"],
        summary="My booking detail",
        responses={
            200: BookingSerializer,
            404: OpenApiResponse(description="BOOKING_NOT_FOUND (missing or not yours)."),
        },
    ),
)
class BookingViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    permission_classes = (IsAuthenticated,)
    http_method_names = ("get", "post", "head", "options")
    filter_backends = (DjangoFilterBackend,)
    filterset_class = BookingFilter
    lookup_value_regex = r"\d+"  # ids are integers; lets cancel pass an int to the service

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):  # schema generation has no real user
            return Booking.objects.none()
        # Always scoped to the caller: other users' bookings are simply "not found" (404)
        return Booking.objects.filter(user=self.request.user).select_related("centre", "test")

    def get_serializer_class(self):
        if self.action == "create":
            return BookingCreateSerializer
        return BookingSerializer

    def get_object(self):
        try:
            return super().get_object()
        except Http404 as exc:
            raise NotFound("Booking not found.", code="BOOKING_NOT_FOUND") from exc

    @extend_schema(
        tags=["Bookings"],
        summary="Create a booking",
        description=(
            "Creates a PENDING booking. The amount is taken from the centre's current price "
            "for the test; any `amount`/`status` in the body is ignored."
        ),
        request=BookingCreateSerializer,
        responses={
            201: BookingSerializer,
            400: OpenApiResponse(
                description="VALIDATION_ERROR, CENTRE_NOT_AVAILABLE, TEST_NOT_OFFERED, "
                "APPOINTMENT_IN_PAST or APPOINTMENT_TOO_FAR."
            ),
            409: OpenApiResponse(description="DUPLICATE_BOOKING"),
        },
        examples=[
            OpenApiExample(
                "Book a CBC",
                value={"centre_id": 1, "test_id": 1, "appointment_at": "2026-10-05T09:30:00Z"},
                request_only=True,
            )
        ],
    )
    def create(self, request):
        serializer = BookingCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        booking = create_booking(user=request.user, **serializer.validated_data)
        return Response(BookingSerializer(booking).data, status=status.HTTP_201_CREATED)

    @extend_schema(
        tags=["Bookings"],
        summary="Cancel my booking",
        request=None,
        responses={
            200: BookingSerializer,
            400: OpenApiResponse(description="APPOINTMENT_ALREADY_PASSED"),
            404: OpenApiResponse(description="BOOKING_NOT_FOUND"),
            409: OpenApiResponse(description="INVALID_STATE_TRANSITION (e.g. already cancelled)"),
        },
    )
    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        booking = cancel_booking(user=request.user, booking_id=int(pk))
        return Response(BookingSerializer(booking).data)
