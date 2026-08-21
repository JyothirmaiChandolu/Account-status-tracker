FROM mcr.microsoft.com/playwright/python:v1.61.0-jammy

WORKDIR /app

COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt && playwright install chromium

COPY . .

# xvfb-run gives Playwright a virtual display — needed because Massachusetts'
# corp.sec.state.ma.us (Incapsula) blocks headless Chromium's search submission
# outright but accepts headed mode; running the whole process under a virtual
# display lets that adapter launch headed without needing a real screen.
CMD xvfb-run -a uvicorn backend.app.api:app --host 0.0.0.0 --port $PORT
