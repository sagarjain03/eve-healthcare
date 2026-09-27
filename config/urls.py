from django.conf import settings
from django.contrib import admin
from django.urls import include, path
from django.views.generic import TemplateView
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from apps.common.views import health_check

urlpatterns = [
    path("admin/", admin.site.urls),
    path("health/", health_check, name="health"),
    path("auth/", include("apps.accounts.urls")),
    path("", include("apps.centres.urls")),
    path("", include("apps.bookings.urls")),
    path("payments/", include("apps.payments.urls")),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
]

if settings.PLAYGROUND_ENABLED:
    # Dev-only browser test page; calls the same API as any client
    urlpatterns.append(
        path(
            "playground/",
            TemplateView.as_view(template_name="common/playground.html"),
            name="playground",
        )
    )

handler404 = "apps.common.views.json_page_not_found"
handler500 = "apps.common.views.json_server_error"
