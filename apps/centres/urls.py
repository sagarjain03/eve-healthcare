from rest_framework.routers import DefaultRouter

from .views import CentreViewSet, DiagnosticTestViewSet

router = DefaultRouter()
router.register("centres", CentreViewSet, basename="centre")
router.register("tests", DiagnosticTestViewSet, basename="test")

urlpatterns = router.urls
