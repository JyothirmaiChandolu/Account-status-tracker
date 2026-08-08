FROM mcr.microsoft.com/playwright/python:v1.61.0-jammy

WORKDIR /app

COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt && playwright install chromium

COPY . .

CMD uvicorn backend.app.api:app --host 0.0.0.0 --port $PORT
