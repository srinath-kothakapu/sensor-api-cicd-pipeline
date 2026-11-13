"""Tests for the sensor API.

FastAPI's TestClient calls the application in-process, so these tests need no
running server and finish in well under a second. That speed matters in CI,
where they run on every push and on two Python versions.
"""
import pytest
from fastapi.testclient import TestClient

from app.main import app, apparent_temperature_c

client = TestClient(app)


def test_health_reports_ok():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_valid_reading_is_accepted_and_echoed():
    payload = {"device_id": "node-1", "temperature_c": 22.5, "humidity_pct": 40}
    response = client.post("/readings", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["device_id"] == "node-1"
    assert body["temperature_c"] == 22.5
    assert "apparent_temperature_c" in body


def test_readings_at_the_exact_limits_are_accepted():
    # The ranges are inclusive, so the boundary values must pass.
    for temp, hum in [(-40, 0), (85, 100)]:
        payload = {"device_id": "edge", "temperature_c": temp, "humidity_pct": hum}
        assert client.post("/readings", json=payload).status_code == 200


@pytest.mark.parametrize(
    "payload",
    [
        {"device_id": "n1", "temperature_c": 90, "humidity_pct": 40},      # too hot
        {"device_id": "n1", "temperature_c": -41, "humidity_pct": 40},     # too cold
        {"device_id": "n1", "temperature_c": 20, "humidity_pct": 101},     # humidity too high
        {"device_id": "n1", "temperature_c": 20, "humidity_pct": -1},      # humidity too low
        {"device_id": "", "temperature_c": 20, "humidity_pct": 50},        # empty device id
        {"temperature_c": 20, "humidity_pct": 50},                         # missing device id
        {"device_id": "n1", "temperature_c": "hot", "humidity_pct": 50},   # wrong type
    ],
)
def test_invalid_readings_are_rejected_with_422(payload):
    assert client.post("/readings", json=payload).status_code == 422


def test_humid_air_feels_warmer_than_dry_air():
    assert apparent_temperature_c(30, 80) > apparent_temperature_c(30, 20)
