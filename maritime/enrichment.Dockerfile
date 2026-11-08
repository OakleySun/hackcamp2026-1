FROM python:3.12-slim-bookworm
RUN pip install --no-cache-dir httpx==0.28.1 tzdata
WORKDIR /app
COPY scripts/review_enrichment_worker.py worker.py
ENV PYTHONUNBUFFERED=1
CMD ["python", "worker.py"]
