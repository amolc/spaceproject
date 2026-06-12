from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator

class Satellite(models.Model):
    STATUS_CHOICES = [
        ('ACTIVE', 'Active'),
        ('INACTIVE', 'Inactive'),
        ('DEGRADED', 'Degraded'),
        ('DEORBITED', 'Deorbited'),
    ]

    name = models.CharField(max_length=100)
    norad_id = models.CharField(max_length=20, unique=True, db_index=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='ACTIVE')
    launch_date = models.DateField(null=True, blank=True)
    orbit_altitude_km = models.FloatField(validators=[MinValueValidator(100.0)])
    inclination_deg = models.FloatField(
        validators=[MinValueValidator(0.0), MaxValueValidator(180.0)]
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return f"{self.name} ({self.norad_id})"


class GroundStation(models.Model):
    STATUS_CHOICES = [
        ('ONLINE', 'Online'),
        ('OFFLINE', 'Offline'),
        ('MAINTENANCE', 'Maintenance'),
    ]

    name = models.CharField(max_length=100)
    station_id = models.CharField(max_length=50, unique=True, db_index=True)
    latitude = models.FloatField(
        validators=[MinValueValidator(-90.0), MaxValueValidator(90.0)]
    )
    longitude = models.FloatField(
        validators=[MinValueValidator(-180.0), MaxValueValidator(180.0)]
    )
    elevation_m = models.FloatField(default=0.0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='ONLINE')
    bandwidth_capacity_gbps = models.FloatField(validators=[MinValueValidator(0.0)])
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return f"{self.name} ({self.station_id})"
