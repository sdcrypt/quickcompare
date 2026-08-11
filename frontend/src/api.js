/**
 * api.js — all HTTP calls the frontend makes to the backend.
 *
 * Every function here talks to a FastAPI endpoint and returns the parsed JSON.
 * Errors are thrown so the caller (App.jsx) can catch them and show a message.
 */

const BASE = "/api";

/**
 * Fetch cached products from the database for a search query.
 * Returns products from ALL platforms (Blinkit, Zepto, etc.) mixed together,
 * sorted cheapest first.
 * Returns an empty array if nothing has been scraped yet or the cache has expired.
 */
export async function searchProducts(query) {
  const res = await fetch(`${BASE}/products?q=${encodeURIComponent(query)}`);
  if (!res.ok) throw new Error("Failed to fetch products");
  return res.json();
}

/**
 * Ask the backend to start scraping for a product query.
 *
 * The backend figures out which platforms are missing or stale and only
 * fires tasks for those. Returns a list of jobs — one per platform that
 * actually needs scraping.
 *
 * Returns: { jobs: [{ platform: "blinkit", job_id: "..." }, ...] }
 *
 * If every platform already has fresh cache, jobs will be an empty array —
 * no polling needed, just show the cached results.
 */
export async function triggerScrape(query) {
  const res = await fetch(`${BASE}/scrape/trigger`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query }),
  });
  if (!res.ok) throw new Error("Failed to trigger scrape");
  return res.json();
}

/**
 * Check the status of multiple scrape jobs in one request.
 *
 * Pass an array of job_id strings. Returns an array of status objects —
 * one per job — with: job_id, platform, status, items_count, error.
 *
 * Possible status values: "pending", "running", "completed", "failed"
 *
 * Example:
 *   [
 *     { job_id: "abc", platform: "blinkit", status: "completed", items_count: 18 },
 *     { job_id: "def", platform: "zepto",   status: "running",   items_count: 0  }
 *   ]
 */
export async function batchScrapeStatus(jobIds) {
  const res = await fetch(
    `${BASE}/scrape/status/batch?job_ids=${jobIds.join(",")}`
  );
  if (!res.ok) throw new Error("Failed to check scrape status");
  return res.json();
}
