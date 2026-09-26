from django.db import DatabaseError, connection
from django.http import JsonResponse
from drf_spectacular.utils import OpenApiResponse, extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .exceptions import _error_body


@extend_schema(
    tags=['Health'],
    summary='Health check',
    auth=[],
    responses={
        200: inline_serializer('HealthResponse', {'status': serializers.CharField()}),
        503: OpenApiResponse(description='DATABASE_UNAVAILABLE'),
    },
)
@api_view(['GET'])
@permission_classes([AllowAny])
def health_check(request):
    """Return 200 if the app can reach the database, else 503."""
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
    except DatabaseError:
        return Response(
            _error_body('DATABASE_UNAVAILABLE', 'Database is unreachable.', {}),
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    return Response({'status': 'ok'})


# Django-level handlers (config/urls.py): used for requests that never reach a DRF view,
# e.g. unmatched URLs, or unexpected errors. Only active when DEBUG=False.


def json_page_not_found(request, exception=None):
    return JsonResponse(_error_body('NOT_FOUND', 'Not found.', {}), status=404)


def json_server_error(request):
    # Generic message only: never expose the exception or traceback to clients
    return JsonResponse(
        _error_body('INTERNAL_ERROR', 'An unexpected error occurred.', {}), status=500
    )
