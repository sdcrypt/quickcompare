FROM python:3.12-slim
WORKDIR /app
RUN pip install playwright celery redis && playwright install --with-deps chromium
COPY . .
CMD ["celery", "-A", "worker", "worker", "--loglevel=info"]