"""Portfolio URL routes."""

from rest_framework.routers import DefaultRouter

from .views import PortfolioEntryViewSet

app_name = "portfolio"

router = DefaultRouter()
router.register("entries", PortfolioEntryViewSet, basename="portfolio-entry")

urlpatterns = router.urls
