from django.db import transaction
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import Satellite, GroundStation
from .serializers import SatelliteSerializer, GroundStationSerializer

class SatelliteViewSet(viewsets.ModelViewSet):
    queryset = Satellite.objects.all()
    serializer_class = SatelliteSerializer

class GroundStationViewSet(viewsets.ModelViewSet):
    queryset = GroundStation.objects.all()
    serializer_class = GroundStationSerializer

    @action(detail=True, methods=['post'], url_path='update-capacity')
    def update_capacity(self, request, pk=None):
        bandwidth = request.data.get('bandwidth_capacity_gbps')
        if bandwidth is None:
            return Response({"error": "bandwidth_capacity_gbps is required"}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            bandwidth = float(bandwidth)
            if bandwidth < 0:
                raise ValueError()
        except ValueError:
            return Response({"error": "bandwidth_capacity_gbps must be a non-negative float"}, status=status.HTTP_400_BAD_REQUEST)

        # Apply transactional atomic row locking (select_for_update)
        try:
            with transaction.atomic():
                station = GroundStation.objects.select_for_update().get(pk=pk)
                station.bandwidth_capacity_gbps = bandwidth
                station.save()
            return Response(self.get_serializer(station).data, status=status.HTTP_200_OK)
        except GroundStation.DoesNotExist:
            return Response({"error": "Ground station not found"}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({"error": f"Transaction failed: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
