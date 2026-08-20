# QuickCompare

QuickCompare is a local price-comparison app for quick-commerce groceries. Search for a product once and the app compares cached or freshly scraped results across Blinkit, Zepto, and Swiggy Instamart, sorted by price.

## What It Does

- Searches products across multiple quick-commerce platforms.
- Caches scraped results for 6 hours to avoid unnecessary re-scraping.
- Shows per-platform scrape progress while background jobs run.
- Normalizes units like `1 Ltr`, `1000 ml`, and `1 Litre Pack` so sizes can be compared cleanly.
- Filters scraped products for relevance before saving them.

## Tech Stack

- Frontend: React 18 + Vite
- Backend: FastAPI + SQLAlchemy
- Database: PostgreSQL 16
- Queue: Redis
- Workers: Celery
- Scraping: Playwright
- Runtime: Docker Compose

## Project Structure

```text
quickcompare/
├── backend/          FastAPI API, database models, migrations, Celery client
├── frontend/         React/Vite user interface
├── scraper/          Playwright scrapers and Celery worker tasks
├── docker-compose.yml
└── README.md
```

## Prerequisites

- Docker
- Docker Compose

You do not need to install Python, Node, Postgres, Redis, or Playwright locally when using Docker.

## Environment Variables

Create a `.env` file in the project root:

```env
DATABASE_URL=postgresql://quickcompare:quickcompare@db:5432/quickcompare
REDIS_URL=redis://redis:6379/0
SCRAPER_PINCODE=110001
```

`SCRAPER_PINCODE` controls the delivery location used by the scrapers. Change it to the pincode you want to compare prices for.

## Run The App

Build and start all services:

```bash
docker compose up --build
```

Then open:

- Frontend: http://localhost:5173
- Backend health check: http://localhost:8000

The app starts these services:

- `frontend` on port `5173`
- `backend` on port `8000`
- `db` on host port `5433`
- `redis` on port `6379`
- `scraper` as a Celery worker

## How Search Works

1. The frontend calls `GET /api/products?q=<query>` to load fresh cached products.
2. If one or more platforms need fresh data, the frontend calls `POST /api/scrape/trigger`.
3. The backend creates one Celery job per missing or stale platform.
4. The scraper worker runs Playwright scrapers and stores products in Postgres.
5. The frontend polls `GET /api/scrape/status/batch` until jobs finish.
6. Products are fetched again and displayed cheapest first.

Cached results are considered fresh for 6 hours.

## API Endpoints

### Health Check

```http
GET /
```

Returns:

```json
{ "message": "QuickCompare API is running" }
```

### Get Products

```http
GET /api/products?q=amul%20milk
```

Returns cached products for the query, sorted by price.

### Trigger Scrape

```http
POST /api/scrape/trigger
Content-Type: application/json

{
  "query": "amul milk"
}
```

Returns scrape jobs for platforms that need fresh data:

```json
{
  "jobs": [
    { "platform": "blinkit", "job_id": "..." },
    { "platform": "zepto", "job_id": "..." },
    { "platform": "instamart", "job_id": "..." }
  ]
}
```

If all platforms already have fresh cache, `jobs` is an empty array.

### Batch Job Status

```http
GET /api/scrape/status/batch?job_ids=id1,id2,id3
```

Returns:

```json
[
  {
    "job_id": "id1",
    "platform": "blinkit",
    "status": "completed",
    "items_count": 18,
    "error": null
  }
]
```

Possible statuses are `pending`, `running`, `completed`, and `failed`.

## Useful Commands

Start services:

```bash
docker compose up
```

Rebuild services:

```bash
docker compose up --build
```

Stop services:

```bash
docker compose down
```

View logs:

```bash
docker compose logs -f
```

View scraper logs:

```bash
docker compose logs -f scraper
```

Clear cached products:

```bash
docker compose exec db psql -U quickcompare -d quickcompare -c "DELETE FROM products;"
```

Clear scrape logs:

```bash
docker compose exec db psql -U quickcompare -d quickcompare -c "DELETE FROM scrape_logs;"
```

Reset the database volume:

```bash
docker compose down -v
docker compose up --build
```

## Adding A New Platform
1. Add a new scraper module in `scraper/` with a `scrape_search(query)` function.
2. Add a matching Celery task in `scraper/worker.py`, such as `scrape_newplatform`.
3. Add the platform name to `PLATFORMS` in `backend/app/api/routes.py`.

The task name must match this pattern:

```text
scraper.worker.scrape_<platform>
```

## Notes
- The backend auto-creates missing tables on startup.
- The frontend talks to the backend through `/api`, which is proxied by Vite in development.
- Scraping depends on the live structure and behavior of third-party websites, so individual scrapers may need updates if those sites change.
