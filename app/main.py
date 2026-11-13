"""Small sensor-reading validation API used to demonstrate a CI/CD pipeline."""
from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel, Field

__version__ = "1.0.0"

app = FastAPI(title="Sensor API", version=__version__)


class Reading(BaseModel):
    device_id: str = Field(min_length=1, max_length=64)
    temperature_c: float = Field(ge=-40.0, le=85.0)
    humidity_pct: float = Field(ge=0.0, le=100.0)


def heat_index_c(temperature_c: float, humidity_pct: float) -> float:
    """Simple apparent-temperature estimate (Steadman-style approximation)."""
    vapour = humidity_pct / 100 * 6.105 * 2.718281828 ** (17.27 * temperature_c / (237.7 + temperature_c))
    return round(temperature_c + 0.33 * vapour - 4.0, 2)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "version": __version__}


@app.post("/readings")
def accept_reading(reading: Reading) -> dict:
    return {
        "device_id": reading.device_id,
        "temperature_c": reading.temperature_c,
        "humidity_pct": reading.humidity_pct,
        "apparent_temperature_c": heat_index_c(reading.temperature_c, reading.humidity_pct),
    }
