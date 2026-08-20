/**
 * ProductGrid — the results area below the search bar.
 *
 * Two display modes, switchable via a toggle button:
 *
 *   📊 Compare (default)
 *      Matches the same product across platforms into one row so the user
 *      can see at a glance which platform is cheapest.
 *
 *   ▦ By Platform
 *      The original side-by-side columns view — one column per platform,
 *      each card showing a single product. Useful for browsing all results.
 *
 * Both modes respect the unit filter chips so the user can narrow to a
 * specific pack size (e.g. "1 L only") before comparing prices.
 */

import { useState } from "react";
import ProductCard from "./ProductCard";
import UnitFilter from "./UnitFilter";
import ComparisonTable from "./ComparisonTable";
import { normalizeUnit, unitToBaseValue } from "../utils";
import { PLATFORM_META } from "../constants";

export default function ProductGrid({ products, query }) {
  // "comparison" shows the matched table; "columns" shows the platform columns
  const [viewMode, setViewMode]       = useState("comparison");
  const [selectedUnit, setSelectedUnit] = useState(null);

  // ── Derived data ─────────────────────────────────────────────────────────

  // Sorted unique normalised units for the filter chips
  const allUnits = [
    ...new Set(products.map((p) => normalizeUnit(p.unit)).filter(Boolean)),
  ].sort((a, b) => unitToBaseValue(a) - unitToBaseValue(b));

  // All platforms that appear in this result set, in a stable order
  const allPlatforms = [...new Set(products.map((p) => p.source).filter(Boolean))];

  // Products filtered to the selected unit (used by the columns view and counts)
  const filteredProducts = selectedUnit
    ? products.filter((p) => normalizeUnit(p.unit) === selectedUnit)
    : products;

  // Group filtered products by platform (columns view only)
  const grouped = filteredProducts.reduce((acc, p) => {
    const key = p.source || "unknown";
    if (!acc[key]) acc[key] = [];
    acc[key].push(p);
    return acc;
  }, {});

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <section className="results-section">

      {/* Header: summary + view toggle */}
      <div className="results-header">
        <p className="results-meta">
          <strong>{filteredProducts.length}</strong>{" "}
          result{filteredProducts.length !== 1 ? "s" : ""} for{" "}
          <strong>"{query}"</strong> across{" "}
          <strong>{allPlatforms.length}</strong>{" "}
          platform{allPlatforms.length !== 1 ? "s" : ""}
          {selectedUnit && (
            <span className="results-meta-filter"> — {selectedUnit}</span>
          )}
        </p>

        <div className="view-toggle">
          <button
            className={`toggle-btn ${viewMode === "comparison" ? "toggle-btn--active" : ""}`}
            onClick={() => setViewMode("comparison")}
            title="Compare the same product across platforms"
          >
            📊 Compare
          </button>
          <button
            className={`toggle-btn ${viewMode === "columns" ? "toggle-btn--active" : ""}`}
            onClick={() => setViewMode("columns")}
            title="See all results grouped by platform"
          >
            ▦ By Platform
          </button>
        </div>
      </div>

      {/* Unit / size filter chips */}
      <UnitFilter
        units={allUnits}
        selected={selectedUnit}
        onSelect={setSelectedUnit}
      />

      {/* ── Comparison table view (default) ── */}
      {viewMode === "comparison" && (
        <ComparisonTable
          products={filteredProducts}
          platforms={allPlatforms}
        />
      )}

      {/* ── Platform columns view ── */}
      {viewMode === "columns" && (
        <div className="platform-columns">
          {allPlatforms.map((platform) => {
            const meta  = PLATFORM_META[platform] || { label: platform, emoji: "🛒", accent: "#888" };
            const items = grouped[platform] || [];

            return (
              <div key={platform} className="platform-column">

                <div
                  className="platform-column-header"
                  style={{ borderTopColor: meta.accent }}
                >
                  <span className="platform-emoji">{meta.emoji}</span>
                  <span className="platform-label">{meta.label}</span>
                  <span className="platform-item-count">
                    {items.length} item{items.length !== 1 ? "s" : ""}
                  </span>
                </div>

                <div className="platform-product-grid">
                  {items.length > 0 ? (
                    items.map((p) => <ProductCard key={p.id} product={p} />)
                  ) : (
                    <p className="no-unit-results">
                      {selectedUnit
                        ? `No ${selectedUnit} products on ${meta.label}`
                        : "No products found"}
                    </p>
                  )}
                </div>

              </div>
            );
          })}
        </div>
      )}

    </section>
  );
}
