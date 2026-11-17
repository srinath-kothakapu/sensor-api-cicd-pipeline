# sensor-api-cicd-pipeline

[![CI/CD](https://github.com/srinath-kothakapu/sensor-api-cicd-pipeline/actions/workflows/ci-cd.yml/badge.svg)](https://github.com/srinath-kothakapu/sensor-api-cicd-pipeline/actions/workflows/ci-cd.yml)

A small FastAPI service that checks temperature and humidity readings from sensor nodes, with a full GitHub Actions CI/CD pipeline around it. The app itself is tiny on purpose. What I wanted to learn was the pipeline: every change gets linted, tested on two Python versions, built into a Docker image, started as a real container and called over HTTP. Only after all that is the image published to GitHub Container Registry.

It follows on from my other projects (`sensor-data-logger`, `stm32-freertos-environmental-monitor`, `envsense-dashboard-fullstack`), which all deal with the same kind of temperature and humidity data.

## What it does

A sensor node sends a device name, a temperature and a humidity. The service checks that the values are physically possible, rejects them if not, and sends the reading back with an "apparent" temperature (how warm it feels with the humidity).

Rejecting bad data early is the useful part. A loose wire or a corrupted message often gives values like 250 °C or 180 % humidity, and it's much easier to refuse those at the API than to clean them out of a database later.

The service doesn't store anything. So the container can be started and stopped any time, and the tests don't need a database.

## Folder structure

```
app/main.py              the FastAPI app
tests/test_api.py        pytest tests (FastAPI TestClient, in-process)
.github/workflows/ci-cd.yml   the pipeline
Dockerfile               image build
.dockerignore            keeps tests and git data out of the image
requirements.txt         runtime dependencies (go into the image)
requirements-dev.txt     test and lint dependencies (CI and local only)
pyproject.toml           ruff and pytest config
```

I kept runtime and dev dependencies separate so pytest, httpx and ruff don't end up in the image. The image only needs FastAPI and Uvicorn.

## The API

### `GET /health`

Returns `{"status": "ok", "version": "1.0.0"}`. The smoke test in the pipeline uses it to know when the container is up, and it's what you would use as a health probe.

### `POST /readings`

Request:

```json
{
  "device_id": "node-1",
  "temperature_c": 22.5,
  "humidity_pct": 40
}
```

Response (200):

```json
{
  "device_id": "node-1",
  "temperature_c": 22.5,
  "humidity_pct": 40.0,
  "apparent_temperature_c": 22.09
}
```

Rules:

- `device_id`: text, 1 to 64 characters
- `temperature_c`: -40 to 85 (inclusive)
- `humidity_pct`: 0 to 100 (inclusive)

If a rule is broken you get HTTP 422 with a JSON body that says which field failed. The limits are the normal range of cheap DHT and SHT sensors. The rules are written once on the `Reading` model and FastAPI/Pydantic enforce them, so the endpoint function doesn't check anything by hand.

With the server running, the auto-generated docs are at `http://localhost:8000/docs`.

The apparent temperature uses a Steadman-style approximation: water vapour pressure from humidity and temperature, then a linear correction. It behaves the right way (humid air feels warmer than dry air at the same temperature), but it's a simple approximation and not a certified heat index. Don't use it for safety decisions.

## The pipeline

Everything is in [`.github/workflows/ci-cd.yml`](.github/workflows/ci-cd.yml).

```
lint --+
       +--> docker-smoke-test --> publish   (only main and version tags)
test --+
```

1. **lint** runs `ruff check .` on Python 3.12 (pycodestyle, pyflakes, import order and some likely bugs, configured in `pyproject.toml`). It only takes a few seconds, so style problems fail before the slow jobs start.
2. **test** runs `pytest -v` on Python 3.10 and 3.12 in parallel, the oldest and newest version I support. Pip downloads are cached.
3. **docker-smoke-test** only starts when lint and both test jobs passed. It builds the image, starts the container, waits for it, and makes three real HTTP calls: `GET /health` must say `ok`, a valid `POST /readings` must return an `apparent_temperature_c`, and a reading with temperature 999 must give 422. The unit tests show the code is right; this job shows the image is right. It catches things like a file missing from the image, a wrong start command, a package that's only installed on my laptop, or a port that isn't exposed. If it fails, it prints the container logs.
4. **publish** only runs if all earlier jobs passed, the event is a push (never a pull request), and the push is to `main` or a tag starting with `v`. It logs in to GHCR with the built-in `GITHUB_TOKEN` (no extra secrets), builds the image and pushes these tags:
   - `sha-<short commit>` on every publish, so any image can be traced back to its commit
   - `latest` for pushes to `main`
   - `1.2.3` when a tag like `v1.2.3` is pushed

   Build layers are cached in the GitHub Actions cache.

## Why I set it up like this

- Cheap checks first: lint and tests run before the Docker build, so a typo doesn't cost a full build.
- Testing the running container, not only the Python code, is what tells me the published image actually starts.
- Publishing depends on the smoke test and only happens for `main` and version tags, so a broken change or a pull request can't produce an image.
- The workflow's default permission is read-only. Only `publish` gets `packages: write`.
- The commit hash in the tag means I always know which code an image came from.
- The container doesn't run as root.

## Run it locally

You need Python 3.10 or newer.

```bash
git clone https://github.com/srinath-kothakapu/sensor-api-cicd-pipeline.git
cd sensor-api-cicd-pipeline

python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt

ruff check .                       # same lint as CI
pytest                             # same tests as CI
uvicorn app.main:app --reload      # API on http://localhost:8000
```

Try it:

```bash
curl http://localhost:8000/health

curl -X POST http://localhost:8000/readings \
  -H "Content-Type: application/json" \
  -d '{"device_id":"node-1","temperature_c":22.5,"humidity_pct":40}'

# this one gets a 422:
curl -i -X POST http://localhost:8000/readings \
  -H "Content-Type: application/json" \
  -d '{"device_id":"node-1","temperature_c":999,"humidity_pct":40}'
```

Or build and run the container yourself:

```bash
docker build -t sensor-api .
docker run --rm -p 8000:8000 sensor-api
```

## Using the published image

After the pipeline has run on `main`:

```bash
docker run --rm -p 8000:8000 ghcr.io/srinath-kothakapu/sensor-api-cicd-pipeline:latest
```

If Docker can't pull it, the package may still be private. Packages created by a workflow start as private, and you change that in the package settings on GitHub.

## Releasing a version

A push to `main` publishes `latest` and a `sha-` tag. For a numbered release, tag a commit:

```bash
git tag v1.0.1
git push origin v1.0.1
```

The pipeline runs again for the tag and, if it passes, publishes `1.0.1`. The version in `/health` comes from `__version__` in `app/main.py`, so change it in the same commit you tag.

## Tests

The tests in `tests/test_api.py` use FastAPI's `TestClient`, which calls the app in the same process. No server needed, and the whole suite runs in about a second. They cover:

- the health endpoint
- a valid reading being accepted and returned
- the exact limits (-40 and 85 °C, 0 and 100 %) being accepted
- seven kinds of bad input (too hot, too cold, humidity too high and too low, empty device id, missing device id, wrong type), all giving 422
- the apparent temperature being higher for humid air than for dry air

## The Dockerfile

Each step in the Dockerfile has a comment. In short, it:

- starts from `python:3.12-slim`
- copies and installs `requirements.txt` before the source code, so Docker's cache skips the slow install when only the code changes
- creates a normal user and switches to it
- starts Uvicorn on port 8000

## What this project doesn't do

I want to be clear about the limits:

- No live deployment. "Delivery" here means publishing a tested image to a registry. There is no server or cluster that pulls and runs it, so no deploy health checks, rollbacks or environments.
- No storage. Readings are checked and returned, not saved.
- No authentication or rate limiting. Anyone who can reach the service can post to it.
- The apparent temperature is an approximation (see above).
- No load or performance tests, only correctness.

## Next steps I'm thinking about

- Deploy the image to a small server or a managed container service and add a health check after deploy.
- Store readings in PostgreSQL and add a query endpoint (`envsense-dashboard-fullstack` already has a schema for this).
- API keys per device and rate limiting.
- An image vulnerability scan in the pipeline.
- Coverage reporting with a minimum coverage gate.
- Dependabot, so dependency and action updates come as pull requests through the same pipeline.
