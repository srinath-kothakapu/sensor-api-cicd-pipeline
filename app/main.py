"""A small sensor-reading API.

The service does one job: it accepts a temperature/humidity reading from a
sensor node, refuses anything that is physically implausible, and hands back
the reading together with an estimated "feels like" temperature.

The application is deliberately tiny. The project exists to show a complete
CI/CD pipeline around it (see .github/workflows/ci-cd.yml), so the code is
kept simple enough to read in one sitting.
"""
from __future__ import annotations

import math

from fastapi import FastAPI
from pydantic import BaseModel, Field

__version__ = "1.0.0"

# Limits taken from the typical operating range of low-cost DHT/SHT-type
# sensors. Anything outside this range is almost certainly a wiring fault or
# a corrupted frame, so we reject it instead of storing bad data.
TEMP_MIN_C = -40.0
TEMP_MAX_C = 85.0
HUMIDITY_MIN_PCT = 0.0
HUMIDITY_MAX_PCT = 100.0

app = FastAPI(title="Sensor API", version=__version__)


class Reading(BaseModel):
    """One measurement sent by a sensor node.

    Pydantic enforces the ranges for us. When a field is out of range, FastAPI
    answers with HTTP 422 and a message saying which field was wrong, so the
    endpoint code below never has to check anything by hand.
    """

    device_id: str = Field(min_length=1, max_length=64)
    temperature_c: float = Field(ge=TEMP_MIN_C, le=TEMP_MAX_C)
    humidity_pct: float = Field(ge=HUMIDITY_MIN_PCT, le=HUMIDITY_MAX_PCT)


def apparent_temperature_c(temperature_c: float, humidity_pct: float) -> float:
    """Estimate how warm the air feels, in degrees Celsius.

    This uses the Steadman-style approximation (water vapour pressure from
    relative humidity, then a linear correction). It is good enough to show
    that humid air feels warmer than dry air at the same temperature. It is
    not a certified heat-index calculation and should not be used for safety
    decisions.
    """
    vapour_pressure = (
        humidity_pct / 100
        * 6.105
        * math.exp(17.27 * temperature_c / (237.7 + temperature_c))
    )
    return round(temperature_c + 0.33 * vapour_pressure - 4.0, 2)


@app.get("/health")
def health() -> dict:
    """Liveness check.

    Used by the CI smoke test, and it is what you would point a container
    orchestrator's health probe at.
    """
    return {"status": "ok", "version": __version__}


@app.post("/readings")
def accept_reading(reading: Reading) -> dict:
    """Validate a reading and return it with the estimated apparent temperature.

    Nothing is stored. Keeping the service stateless means the container can
    be started, stopped and tested without a database.
    """
    return {
        "device_id": reading.device_id,
        "temperature_c": reading.temperature_c,
        "humidity_pct": reading.humidity_pct,
        "apparent_temperature_c": apparent_temperature_c(
            reading.temperature_c, reading.humidity_pct
        ),
    }
