const BASE = "/api";

/** Fetch cached products for a query (returns [] if nothing in DB yet). */
export async function searchProducts(query) {
  const res = await fetch(`${BASE}/products?q=${encodeURIComponent(query)}`);
  if (!res.ok) throw new Error("Failed to fetch products");
  return res.json();
}

/** Trigger an async scrape job. Returns { job_id, status }. */
export async function triggerScrape(query) {
  const res = await fetch(`${BASE}/scrape/trigger`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query }),
  });
  if (!res.ok) throw new Error("Failed to trigger scrape");
  return res.json();
}

/** Poll a scrape job status. Returns { job_id, status, items_count, error }. */
export async function checkScrapeStatus(jobId) {
  const res = await fetch(`${BASE}/scrape/status/${jobId}`);
  if (!res.ok) throw new Error("Failed to check scrape status");
  return res.json();
}
