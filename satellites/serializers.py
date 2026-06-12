from rest_framework import serializers
from .models import Satellite, GroundStation

class SatelliteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Satellite
        fields = '__all__'

class GroundStationSerializer(serializers.ModelSerializer):
    class Meta:
        model = GroundStation
        fields = '__all__'
