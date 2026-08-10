FROM python:3.12-slim

WORKDIR /app

# Install OS deps needed by Playwright's Chromium
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
 && playwright install --with-deps chromium

COPY . .

CMD ["celery", "-A", "worker", "worker", "--loglevel=info"]
