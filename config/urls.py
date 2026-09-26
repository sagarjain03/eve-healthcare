from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from apps.common.views import health_check

urlpatterns = [
    path('admin/', admin.site.urls),
    path('health/', health_check, name='health'),
    path('auth/', include('apps.accounts.urls')),
    path('', include('apps.centres.urls')),
    path('', include('apps.bookings.urls')),
    path('payments/', include('apps.payments.urls')),
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
]

handler404 = 'apps.common.views.json_page_not_found'
handler500 = 'apps.common.views.json_server_error'
