import { useState } from "react";
import SearchBar from "./components/SearchBar";
import ProductGrid from "./components/ProductGrid";
import ScrapeStatus from "./components/ScrapeStatus";
import { searchProducts, triggerScrape, checkScrapeStatus } from "./api";

const POLL_INTERVAL_MS = 3000;

export default function App() {
  const [products, setProducts]     = useState([]);
  const [loading, setLoading]       = useState(false);
  const [statusMsg, setStatusMsg]   = useState("");
  const [itemsFound, setItemsFound] = useState(0);
  const [error, setError]           = useState("");
  const [lastQuery, setLastQuery]   = useState("");

  const handleSearch = async (query) => {
    setLoading(true);
    setError("");
    setProducts([]);
    setItemsFound(0);
    setLastQuery(query);
    setStatusMsg("Checking cached results…");

    try {
      // ── 1. Try cache first ────────────────────────────────────────────────
      const cached = await searchProducts(query);
      if (cached.length > 0) {
        setProducts(cached);
        setStatusMsg("");
        setLoading(false);
        return;
      }

      // ── 2. Cache miss → trigger a scrape ─────────────────────────────────
      setStatusMsg("No cached results — starting Blinkit scrape…");
      const { job_id } = await triggerScrape(query);

      // ── 3. Poll until done ────────────────────────────────────────────────
      await pollUntilDone(job_id, query);
    } catch (err) {
      setError(err.message || "Something went wrong. Please try again.");
      setLoading(false);
      setStatusMsg("");
    }
  };

  /** Async poll loop — resolves when the job is completed or failed. */
  const pollUntilDone = async (jobId, query) => {
    while (true) {
      await sleep(POLL_INTERVAL_MS);

      const { status, items_count, error: jobError } = await checkScrapeStatus(jobId);
      setItemsFound(items_count ?? 0);

      if (status === "running") {
        setStatusMsg("Scraping Blinkit…");
      } else if (status === "completed") {
        const fresh = await searchProducts(query);
        setProducts(fresh);
        setStatusMsg("");
        setLoading(false);
        return;
      } else if (status === "failed") {
        setError(jobError || "Scrape failed. Try again.");
        setStatusMsg("");
        setLoading(false);
        return;
      }
      // "pending" → keep polling
    }
  };

  return (
    <div className="app">
      {/* ── Header ── */}
      <header className="header">
        <h1 className="logo">⚡ QuickCompare</h1>
        <p className="tagline">Search any product and see Blinkit prices instantly</p>
      </header>

      {/* ── Search ── */}
      <main className="main">
        <SearchBar onSearch={handleSearch} disabled={loading} />

        {loading && (
          <ScrapeStatus message={statusMsg} itemsFound={itemsFound} />
        )}

        {error && <div className="error-box">{error}</div>}

        {!loading && products.length > 0 && (
          <ProductGrid products={products} query={lastQuery} />
        )}

        {!loading && !error && products.length === 0 && lastQuery && (
          <p className="empty-state">No products found for "{lastQuery}".</p>
        )}
      </main>
    </div>
  );
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
