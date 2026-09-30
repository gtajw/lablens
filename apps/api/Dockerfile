FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app/apps/api/src OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
WORKDIR /app
COPY requirements.lock ./
RUN pip install --no-cache-dir --require-hashes -r requirements.lock
COPY apps/api ./apps/api
COPY scripts/cleanup.py scripts/maintenance_loop.py ./scripts/
COPY alembic.ini ./
RUN useradd --system --uid 10001 --create-home lablens
USER lablens
EXPOSE 8000
CMD ["uvicorn", "lablens.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2", "--limit-concurrency", "64", "--timeout-keep-alive", "5", "--no-access-log"]
