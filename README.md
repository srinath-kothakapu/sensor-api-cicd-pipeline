# sensor-api-cicd-pipeline

[![CI/CD](https://github.com/srinath-kothakapu/sensor-api-cicd-pipeline/actions/workflows/ci-cd.yml/badge.svg)](https://github.com/srinath-kothakapu/sensor-api-cicd-pipeline/actions/workflows/ci-cd.yml)

A small FastAPI service that validates temperature/humidity readings, built mainly to demonstrate a complete
GitHub Actions CI/CD pipeline. The application is intentionally small; the pipeline is the point.

## Pipeline

Defined in [`.github/workflows/ci-cd.yml`](.github/workflows/ci-cd.yml).

| Stage | Runs on | What it does |
|-------|---------|--------------|
| `lint` | every push and PR | `ruff check` |
| `test` | every push and PR | `pytest` on Python 3.10 and 3.12 |
| `docker-smoke-test` | after lint and test | builds the image, starts the container, calls `/health`, posts a valid reading, and checks that an out-of-range reading gets HTTP 422 |
| `publish` | only pushes to `main` or `v*` tags, after all of the above pass | builds and pushes the image to GitHub Container Registry (`ghcr.io/srinath-kothakapu/sensor-api-cicd-pipeline`) tagged `sha-<commit>`, `latest` (main) and the semantic version (tags) |

Pull requests run the checks but never publish.

## API

- `GET /health` returns `{"status": "ok", "version": ...}`
- `POST /readings` accepts `{"device_id", "temperature_c", "humidity_pct"}`. Temperature must be -40 to 85 C and humidity 0 to 100 %RH, otherwise the API returns 422. A valid reading is returned with an estimated apparent temperature.

## Run locally

```bash
pip install -r requirements-dev.txt
pytest
uvicorn app.main:app --reload
```

Or with the published image:

```bash
docker run -p 8000:8000 ghcr.io/srinath-kothakapu/sensor-api-cicd-pipeline:latest
```

## Scope and limits

- "Delivery" here means publishing a tested container image to a registry. There is no live server this deploys to, so no deployment health checks or rollbacks are claimed.
- The service stores nothing and has no authentication.
- The apparent-temperature formula is a simple approximation, not a certified heat index.
