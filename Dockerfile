# Example Dockerfile (placed at repo root)
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

# Expose the port the service expec8080)
EXPOSE 10000

ENV PORT=10000
CMD ["uvicorn", "api:app", "--host"T}"]
