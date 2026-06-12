# locustfile.py
"""Locust load‑testing script for the Space Internet Service Provider.
It simulates satellite telemetry submissions and subscriber geospatial queries.
"""

import random
from locust import HttpUser, task, between


class SpaceSubscriberUser(HttpUser):
    """Simulates a subscriber client calling the nearest‑satellite endpoint."""
    wait_time = between(0.1, 0.5)

    @task
    def get_nearest_satellites(self):
        lat = random.uniform(-90.0, 90.0)
        lon = random.uniform(-180.0, 180.0)
        self.client.get(f"/api/orbit/nearest/?lat={lat}&lon={lon}")
