import { useState } from "react";
import SearchBar from "./components/SearchBar";
import ProductGrid from "./components/ProductGrid";
import ScrapeStatus from "./components/ScrapeStatus";
import { searchProducts, triggerScrape, batchScrapeStatus } from "./api";

const POLL_INTERVAL_MS = 3000;

export default function App() {
  const [products, setProducts]               = useState([]);
  const [loading, setLoading]                 = useState(false);
  const [platformStatuses, setPlatformStatuses] = useState([]); // per-platform progress
  const [error, setError]                     = useState("");
  const [lastQuery, setLastQuery]             = useState("");

  const handleSearch = async (query) => {
    setLoading(true);
    setError("");
    setProducts([]);
    setPlatformStatuses([]);
    setLastQuery(query);

    try {
      // ── Step 1: Show whatever is already cached immediately ───────────────
      // Users see results from previously scraped platforms right away,
      // even if some platforms still need a fresh scrape.
      const cached = await searchProducts(query);
      if (cached.length > 0) setProducts(cached);

      // ── Step 2: Ask backend which platforms need scraping ─────────────────
      // The backend only fires tasks for platforms that don't have fresh cache.
      const { jobs } = await triggerScrape(query);

      if (jobs.length === 0) {
        // Every platform is already cached — nothing to wait for
        setLoading(false);
        return;
      }

      // ── Step 3: Show initial per-platform status and start polling ────────
      setPlatformStatuses(
        jobs.map((j) => ({ ...j, status: "pending", items_count: 0 }))
      );
      await pollUntilDone(jobs, query);

    } catch (err) {
      setError(err.message || "Something went wrong. Please try again.");
      setLoading(false);
      setPlatformStatuses([]);
    }
  };

  /**
   * Poll all running jobs every POLL_INTERVAL_MS milliseconds.
   * Updates the per-platform status bar as each platform finishes.
   * Once every job is either "completed" or "failed", fetches the full
   * product list (which now includes results from all platforms) and stops.
   */
  const pollUntilDone = async (jobs, query) => {
    const jobIds = jobs.map((j) => j.job_id);

    while (true) {
      await sleep(POLL_INTERVAL_MS);

      const statuses = await batchScrapeStatus(jobIds);
      setPlatformStatuses(statuses);

      const allDone = statuses.every(
        (s) => s.status === "completed" || s.status === "failed"
      );

      if (allDone) {
        // Refresh products — now includes results from newly scraped platforms
        const fresh = await searchProducts(query);
        setProducts(fresh);
        setLoading(false);
        setPlatformStatuses([]);
        return;
      }
      // Some jobs still running — keep polling
    }
  };

  const isStillLoading = loading && platformStatuses.length > 0;
  const isInitialLoad  = loading && platformStatuses.length === 0;

  return (
    <div className="app">
      {/* ── Header ── */}
      <header className="header">
        <h1 className="logo">⚡ QuickCompare</h1>
        <p className="tagline">
          Compare prices across Blinkit &amp; Zepto instantly
        </p>
      </header>

      {/* ── Search ── */}
      <main className="main">
        <SearchBar onSearch={handleSearch} disabled={loading} />

        {/* Initial spinner before jobs are created */}
        {isInitialLoad && (
          <div className="status-bar">
            <span className="spinner" />
            <span className="status-msg">Checking cache…</span>
          </div>
        )}

        {/* Per-platform progress once jobs are running */}
        {isStillLoading && (
          <ScrapeStatus platformStatuses={platformStatuses} />
        )}

        {error && <div className="error-box">{error}</div>}

        {products.length > 0 && (
          <ProductGrid products={products} query={lastQuery} />
        )}

        {!loading && !error && products.length === 0 && lastQuery && (
          <p className="empty-state">
            No products found for "{lastQuery}". Try a different search.
          </p>
        )}
      </main>
    </div>
  );
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
