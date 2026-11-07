FROM python:3.12-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=10000

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . ./
# Generate/refresh committed-input artifacts without network access, so the
# image contains a usable rainfall-forecast demonstration on first start.
RUN python orchestrator/run_pipeline.py offline

EXPOSE 10000
CMD exec uvicorn api:app --host 0.0.0.0 --port "${PORT}"
