from django.db import DatabaseError, connection
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response


@api_view(['GET'])
@permission_classes([AllowAny])
def health_check(request):
    """Return 200 if the app can reach the database, else 503."""
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
    except DatabaseError:
        return Response({'status': 'error'}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
    return Response({'status': 'ok'})
