# Small official Python image. "slim" keeps the final image a lot smaller than
# the full one and is enough because the app has no native dependencies.
FROM python:3.12-slim

# Do not write .pyc files into the image, and flush logs straight away so
# `docker logs` shows output as it happens.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /srv

# Install dependencies before copying the source. Docker caches each step, so
# editing app code does not trigger a slow reinstall of the packages.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# Run as an ordinary user. If someone ever finds a bug in the service, this
# stops them from having root inside the container.
RUN useradd --create-home appuser
USER appuser

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
