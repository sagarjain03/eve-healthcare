from django.db.models import Prefetch
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import (
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
    extend_schema_view,
)
from rest_framework import filters, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.common.permissions import IsAdminOrReadOnly

from .filters import CentreFilter
from .models import CentreTest, DiagnosticCentre, DiagnosticTest
from .serializers import (
    CentreDetailSerializer,
    CentreListSerializer,
    CentreWriteSerializer,
    DiagnosticTestSerializer,
    OfferingSerializer,
    OfferingWriteSerializer,
)
from .services import create_centre, create_test, update_centre, update_test, upsert_offering

READ_WRITE_METHODS = ["get", "post", "patch", "head", "options"]  # no DELETE: deactivate instead


@extend_schema_view(
    list=extend_schema(
        tags=["Centres"],
        summary="List centres",
        description="Public. Non-admins only see active centres.",
        parameters=[
            OpenApiParameter("city", OpenApiTypes.STR, description="City (case-insensitive)."),
            OpenApiParameter(
                "test",
                OpenApiTypes.STR,
                description="Test id or code (e.g. `3` or `cbc`); centres actively offering it.",
            ),
        ],
    ),
    retrieve=extend_schema(
        tags=["Centres"],
        summary="Centre detail",
        description="Public. Includes offered tests with prices (active ones for non-admins).",
    ),
    create=extend_schema(
        tags=["Centres"],
        summary="Create centre (admin)",
        responses={
            201: CentreWriteSerializer,
            409: OpenApiResponse(description="CENTRE_ALREADY_EXISTS"),
        },
    ),
    partial_update=extend_schema(
        tags=["Centres"],
        summary="Update / deactivate centre (admin)",
        responses={
            200: CentreWriteSerializer,
            409: OpenApiResponse(description="CENTRE_ALREADY_EXISTS"),
        },
    ),
)
class CentreViewSet(viewsets.ModelViewSet):
    permission_classes = (IsAdminOrReadOnly,)
    http_method_names = READ_WRITE_METHODS
    filter_backends = (DjangoFilterBackend,)
    filterset_class = CentreFilter

    def _is_staff(self) -> bool:
        return bool(self.request.user and self.request.user.is_staff)

    def get_queryset(self):
        queryset = DiagnosticCentre.objects.order_by("name", "id")
        if not self._is_staff():
            queryset = queryset.filter(is_active=True)
        if self.action == "retrieve":
            offerings = CentreTest.objects.select_related("test").order_by("test__name")
            if not self._is_staff():
                offerings = offerings.filter(is_active=True, test__is_active=True)
            queryset = queryset.prefetch_related(Prefetch("offerings", queryset=offerings))
        return queryset

    def get_serializer_class(self):
        if self.action == "list":
            return CentreListSerializer
        if self.action == "retrieve":
            return CentreDetailSerializer
        if self.action == "add_test":
            return OfferingWriteSerializer
        return CentreWriteSerializer

    def perform_create(self, serializer):
        serializer.instance = create_centre(**serializer.validated_data)

    def perform_update(self, serializer):
        serializer.instance = update_centre(serializer.instance, **serializer.validated_data)

    @extend_schema(
        tags=["Centres"],
        summary="Add or update a test offering (admin)",
        description="Creates the offering (201) or updates its price/is_active (200).",
        request=OfferingWriteSerializer,
        responses={
            200: OfferingSerializer,
            201: OfferingSerializer,
            400: OpenApiResponse(description="Invalid price, unknown or inactive test."),
        },
    )
    @action(detail=True, methods=["post"], url_path="tests")
    def add_test(self, request, pk=None):
        centre = self.get_object()
        serializer = OfferingWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        offering, created = upsert_offering(centre=centre, **serializer.validated_data)
        return Response(
            OfferingSerializer(offering).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


@extend_schema_view(
    list=extend_schema(
        tags=["Tests"],
        summary="List tests",
        description="Public test catalog. Non-admins only see active tests.",
    ),
    retrieve=extend_schema(tags=["Tests"], summary="Test detail"),
    create=extend_schema(
        tags=["Tests"],
        summary="Create test (admin)",
        responses={
            201: DiagnosticTestSerializer,
            409: OpenApiResponse(description="TEST_CODE_ALREADY_EXISTS"),
        },
    ),
    partial_update=extend_schema(
        tags=["Tests"],
        summary="Update / deactivate test (admin)",
        responses={
            200: DiagnosticTestSerializer,
            409: OpenApiResponse(description="TEST_CODE_ALREADY_EXISTS"),
        },
    ),
)
class DiagnosticTestViewSet(viewsets.ModelViewSet):
    serializer_class = DiagnosticTestSerializer
    permission_classes = (IsAdminOrReadOnly,)
    http_method_names = READ_WRITE_METHODS
    filter_backends = (filters.SearchFilter, filters.OrderingFilter)
    search_fields = ("name", "code")
    ordering_fields = ("name",)
    ordering = ("name",)

    def get_queryset(self):
        queryset = DiagnosticTest.objects.order_by("name", "id")
        if not (self.request.user and self.request.user.is_staff):
            queryset = queryset.filter(is_active=True)
        return queryset

    def perform_create(self, serializer):
        serializer.instance = create_test(**serializer.validated_data)

    def perform_update(self, serializer):
        serializer.instance = update_test(serializer.instance, **serializer.validated_data)
