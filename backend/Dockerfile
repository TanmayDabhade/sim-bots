FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY pyproject.toml ./
COPY app ./app
COPY alembic.ini ./
COPY alembic ./alembic
RUN pip3 install --no-cache-dir .

EXPOSE 8000
CMD ["/bin/sh", "-c", "alembic upgrade head && python -m app.cli init-db && uvicorn app.main:app --host 0.0.0.0 --port 8000"]

