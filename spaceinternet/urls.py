from django.contrib import admin
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from satellites.views import SatelliteViewSet, GroundStationViewSet

router = DefaultRouter()
router.register(r'satellites', SatelliteViewSet, basename='satellite')
router.register(r'ground-stations', GroundStationViewSet, basename='groundstation')

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include(router.urls)),
]
