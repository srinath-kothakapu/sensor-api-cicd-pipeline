# sensor-api-cicd-pipeline

[![CI/CD](https://github.com/srinath-kothakapu/sensor-api-cicd-pipeline/actions/workflows/ci-cd.yml/badge.svg)](https://github.com/srinath-kothakapu/sensor-api-cicd-pipeline/actions/workflows/ci-cd.yml)

A small FastAPI service that validates temperature and humidity readings from sensor nodes, wrapped in a complete
GitHub Actions CI/CD pipeline. The application is intentionally tiny. The point of the project is the pipeline
around it: every change is linted, tested on two Python versions, built into a Docker image, started as a real
container and called over HTTP, and only then is the image published to GitHub Container Registry.

I built it to practise the parts of delivering software that sit around the code: automated checks, repeatable
builds, and a release step that cannot run unless everything before it passed. It follows on from my embedded and
data projects (`sensor-data-logger`, `stm32-freertos-environmental-monitor`, `envsense-dashboard-fullstack`),
which all deal with the same kind of temperature and humidity data.

## Table of contents

1. [What the project does](#what-the-project-does)
2. [Repository layout](#repository-layout)
3. [The API](#the-api)
4. [The pipeline, step by step](#the-pipeline-step-by-step)
5. [Why it is built this way](#why-it-is-built-this-way)
6. [Run it locally](#run-it-locally)
7. [Use the published image](#use-the-published-image)
8. [Releasing a version](#releasing-a-version)
9. [Testing](#testing)
10. [The Dockerfile](#the-dockerfile)
11. [What this project does not do](#what-this-project-does-not-do)
12. [Ideas for next steps](#ideas-for-next-steps)

## What the project does

Sensor nodes send a measurement (a device name, a temperature and a relative humidity). The service checks that the
numbers are physically believable, rejects them if not, and returns the reading together with an estimated
"apparent" temperature, meaning how warm the air feels once humidity is taken into account.

Rejecting bad data at the door is the useful part. A loose wire or a corrupted message on a real sensor often
produces values like 250 degrees or 180 % humidity, and it is much easier to refuse those at the API than to
clean them out of a database later.

The service is stateless. It stores nothing, which means the container can be started and stopped freely and the
tests need no database.

## Repository layout

```
.
├── app/
│   ├── __init__.py          package marker
│   └── main.py              the FastAPI application
├── tests/
│   └── test_api.py          pytest tests run in-process with FastAPI's TestClient
├── .github/workflows/
│   └── ci-cd.yml            the whole pipeline
├── Dockerfile               how the container image is built
├── .dockerignore            keeps tests and git data out of the image
├── requirements.txt         runtime dependencies (go into the image)
├── requirements-dev.txt     test and lint dependencies (CI and local only)
├── pyproject.toml           ruff and pytest configuration
└── README.md
```

Runtime and development dependencies are kept in separate files on purpose. The image only needs FastAPI and
Uvicorn, so pytest, httpx and ruff stay out of it. That keeps the image smaller and reduces what could go wrong
in it.

## The API

### `GET /health`

Returns `{"status": "ok", "version": "1.0.0"}`. This is the liveness check. The pipeline's smoke test uses it to
find out when the container has finished starting, and it is what you would point an orchestrator's health probe
at.

### `POST /readings`

Request body:

```json
{
  "device_id": "node-1",
  "temperature_c": 22.5,
  "humidity_pct": 40
}
```

Response (HTTP 200):

```json
{
  "device_id": "node-1",
  "temperature_c": 22.5,
  "humidity_pct": 40.0,
  "apparent_temperature_c": 22.09
}
```

Validation rules:

| Field | Rule |
|-------|------|
| `device_id` | text, 1 to 64 characters |
| `temperature_c` | number from -40 to 85 inclusive |
| `humidity_pct` | number from 0 to 100 inclusive |

Anything that breaks a rule gets HTTP 422 with a JSON body that names the field that failed. The limits match the
usual operating range of low-cost DHT and SHT type sensors. The validation is declared once on the `Reading`
model, and FastAPI and Pydantic enforce it, so the endpoint function itself never checks anything by hand.

FastAPI also generates interactive documentation. With the server running, open `http://localhost:8000/docs`.

### About the apparent temperature

The estimate uses a Steadman-style approximation: water vapour pressure is derived from relative humidity and
air temperature, then a linear correction is applied. It shows the right behaviour (humid air feels warmer than
dry air at the same temperature) but it is a simple approximation, not a certified heat-index calculation. Do not
use it for safety decisions.

## The pipeline, step by step

Everything is defined in [`.github/workflows/ci-cd.yml`](.github/workflows/ci-cd.yml).

```
lint ──┐
       ├──> docker-smoke-test ──> publish   (main branch and version tags only)
test ──┘
```

### 1. `lint`

Runs `ruff check .` on Python 3.12. Ruff is configured in `pyproject.toml` to look for pycodestyle errors,
pyflakes problems, unsorted imports and a set of likely bugs. It takes a few seconds, so style and obvious
mistakes fail fast before slower jobs start.

### 2. `test`

Runs `pytest -v` on a matrix of Python 3.10 and Python 3.12, the oldest and newest versions I claim to support.
The two versions run in parallel. Pip downloads are cached between runs so installs are quick.

### 3. `docker-smoke-test`

Starts only when lint and both test jobs have passed. It builds the Dockerfile, starts the container, waits for it
to answer, then makes three real HTTP calls:

1. `GET /health` must return status `ok`.
2. A valid `POST /readings` must come back with an `apparent_temperature_c` value.
3. An out-of-range reading (temperature 999) must return HTTP 422.

Unit tests prove the code is right. This job proves the image is right. It catches problems tests cannot see, such
as a file missing from the image, a wrong start command, a package that is installed on a developer machine but
missing from `requirements.txt`, or a port that is not exposed. If the smoke test fails, the container logs are
printed in the job output.

### 4. `publish`

This is the delivery step. It runs only when all of these are true:

- every earlier job succeeded, and
- the event is a push (never a pull request), and
- the push is to `main` or a tag that starts with `v`.

It logs in to GitHub Container Registry with the built-in `GITHUB_TOKEN`, so no extra secrets need to be stored,
then builds the image and pushes it with these tags:

| Tag | When |
|-----|------|
| `sha-<short commit>` | every publish, so any build can be traced to the exact commit |
| `latest` | pushes to `main` |
| `1.2.3` | when a tag like `v1.2.3` is pushed |

Build layers are cached in the GitHub Actions cache to make repeated builds faster.

## Why it is built this way

- **Cheap checks first.** Lint and tests run before the image is built, so a typo does not cost a Docker build.
- **A real container test.** Testing the running image, not just the Python code, is what gives confidence that
  what gets published actually starts.
- **Publishing is gated.** The `publish` job depends on the smoke test and is limited to `main` and version tags.
  A broken change or a pull request cannot produce an image.
- **Least privilege.** The workflow's default permission is read-only. Only the `publish` job is given
  `packages: write`.
- **Traceable images.** The commit hash in the tag means you can always say which source produced an image.
- **Runs as a normal user.** The container does not run as root.

## Run it locally

You need Python 3.10 or newer.

```bash
git clone https://github.com/srinath-kothakapu/sensor-api-cicd-pipeline.git
cd sensor-api-cicd-pipeline

python -m venv .venv
source .venv/bin/activate          # on Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt

ruff check .                       # the same lint step CI runs
pytest                             # the same tests CI runs
uvicorn app.main:app --reload      # start the API on http://localhost:8000
```

Try it:

```bash
curl http://localhost:8000/health

curl -X POST http://localhost:8000/readings \
  -H "Content-Type: application/json" \
  -d '{"device_id":"node-1","temperature_c":22.5,"humidity_pct":40}'

# This one is refused with HTTP 422:
curl -i -X POST http://localhost:8000/readings \
  -H "Content-Type: application/json" \
  -d '{"device_id":"node-1","temperature_c":999,"humidity_pct":40}'
```

To build and run the container yourself:

```bash
docker build -t sensor-api .
docker run --rm -p 8000:8000 sensor-api
```

## Use the published image

After the pipeline has run on `main`, the image is available from GitHub Container Registry:

```bash
docker run --rm -p 8000:8000 ghcr.io/srinath-kothakapu/sensor-api-cicd-pipeline:latest
```

If Docker says it cannot pull the image, the package may still be set to private. A package created by a workflow
starts private by default, and its visibility is changed in the package settings on GitHub.

## Releasing a version

Pushing to `main` publishes `latest` and a `sha-` tag. To publish a numbered release, tag a commit:

```bash
git tag v1.0.1
git push origin v1.0.1
```

The pipeline runs again for the tag and, if it passes, publishes the image as `1.0.1`. The version reported by
`/health` comes from `__version__` in `app/main.py`, so update it in the same commit you tag.

## Testing

The tests are in `tests/test_api.py` and use FastAPI's `TestClient`, which calls the application in the same
process. No server needs to be running, and the whole suite finishes in about a second. They cover:

- the health endpoint,
- a valid reading being accepted and echoed back,
- the exact boundary values (-40 and 85 degrees, 0 and 100 % humidity) being accepted,
- seven kinds of bad input (too hot, too cold, humidity above and below range, empty device id, missing device
  id, wrong data type) all returning 422,
- the apparent temperature being higher for humid air than for dry air.

## The Dockerfile

The Dockerfile has comments on each step. In short:

- it starts from `python:3.12-slim`, which is small and has everything this app needs,
- it copies and installs `requirements.txt` before copying the source, so Docker's layer cache skips the slow
  install when only application code changes,
- it creates and switches to an unprivileged user,
- it starts Uvicorn on port 8000.

## What this project does not do

I want to be clear about the limits so nothing here is read as more than it is.

- **There is no live deployment.** "Delivery" in this project means publishing a tested image to a registry. I have
  not set up a server or cluster that pulls and runs it, so there are no deployment health checks, rollbacks or
  environments.
- **No persistence.** Readings are validated and returned, not stored.
- **No authentication or rate limiting.** Anyone who can reach the service can post to it.
- **The apparent-temperature formula is an approximation**, as described above.
- **No load or performance testing.** The tests check correctness only.

## Ideas for next steps

- Deploy the image to a small host or a managed container service and add a post-deploy health check.
- Store readings in PostgreSQL and add a query endpoint (`envsense-dashboard-fullstack` already has a schema for this).
- Add API keys per device and rate limiting.
- Add a vulnerability scan of the image to the pipeline.
- Add test coverage reporting and a minimum coverage gate.
- Add Dependabot so dependency and action updates arrive as pull requests that go through the same pipeline.
