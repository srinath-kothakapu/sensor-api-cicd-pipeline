import pytest
from fastapi.testclient import TestClient

from app.main import app, heat_index_c

client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_valid_reading_is_accepted():
    r = client.post("/readings", json={"device_id": "n1", "temperature_c": 22.5, "humidity_pct": 40})
    assert r.status_code == 200
    body = r.json()
    assert body["device_id"] == "n1"
    assert "apparent_temperature_c" in body


@pytest.mark.parametrize(
    "payload",
    [
        {"device_id": "n1", "temperature_c": 90, "humidity_pct": 40},
        {"device_id": "n1", "temperature_c": -41, "humidity_pct": 40},
        {"device_id": "n1", "temperature_c": 20, "humidity_pct": 101},
        {"device_id": "n1", "temperature_c": 20, "humidity_pct": -1},
        {"device_id": "", "temperature_c": 20, "humidity_pct": 50},
        {"temperature_c": 20, "humidity_pct": 50},
        {"device_id": "n1", "temperature_c": "hot", "humidity_pct": 50},
    ],
)
def test_invalid_readings_are_rejected(payload):
    assert client.post("/readings", json=payload).status_code == 422


def test_heat_index_rises_with_humidity():
    assert heat_index_c(30, 80) > heat_index_c(30, 20)
