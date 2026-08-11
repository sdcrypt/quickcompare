/**
 * ProductGrid — displays results grouped by platform side by side,
 * with a unit/size filter so users can compare the same pack size
 * across platforms for a fair price comparison.
 *
 * Layout:
 *   [ Filter by size: All sizes | 200 ml | 500 ml | 1 L ]
 *
 *   ┌── 🟢 Blinkit  9 items ──┐   ┌── 🟣 Zepto  7 items ──┐
 *   │  [card] [card] [card]   │   │  [card] [card] [card]  │
 *   │  [card] [card] ...      │   │  No 500 ml products    │
 *   └─────────────────────────┘   └────────────────────────┘
 *
 * When a unit chip is selected, both columns update simultaneously so
 * the user sees only that size — making it easy to compare like-for-like.
 * If a platform has no products in the selected size, a short message is
 * shown so the user knows the platform simply doesn't carry that size.
 */

import { useState } from "react";
import ProductCard from "./ProductCard";
import UnitFilter from "./UnitFilter";
import { normalizeUnit, unitToBaseValue } from "../utils";

// Display config per platform — add new ones here as scrapers are built
const PLATFORM_META = {
  blinkit:   { label: "Blinkit",          emoji: "🟢", accent: "#0f9e6e" },
  zepto:     { label: "Zepto",            emoji: "🟣", accent: "#7c3aed" },
  instamart: { label: "Swiggy Instamart", emoji: "🟠", accent: "#f97316" },
};

export default function ProductGrid({ products, query }) {
  // Which unit chip is selected — null means "All sizes"
  const [selectedUnit, setSelectedUnit] = useState(null);

  // ── Build the sorted list of unique unit chips ───────────────────────────
  // Collect normalised units from every product, deduplicate, then sort
  // from smallest to largest so chips read "200 ml → 500 ml → 1 L → 2 L".
  const allUnits = [
    ...new Set(products.map((p) => normalizeUnit(p.unit)).filter(Boolean)),
  ].sort((a, b) => unitToBaseValue(a) - unitToBaseValue(b));

  // ── Filter products by the selected unit ─────────────────────────────────
  const filteredProducts = selectedUnit
    ? products.filter((p) => normalizeUnit(p.unit) === selectedUnit)
    : products;

  // ── Group filtered products by platform ──────────────────────────────────
  const grouped = filteredProducts.reduce((acc, p) => {
    const key = p.source || "unknown";
    if (!acc[key]) acc[key] = [];
    acc[key].push(p);
    return acc;
  }, {});

  // Keep the original platform list so columns don't disappear when
  // a filter is applied — instead, they show a "no results" message.
  const allPlatforms = [
    ...new Set(products.map((p) => p.source || "unknown")),
  ];

  const totalFiltered = filteredProducts.length;

  return (
    <section className="results-section">

      {/* Summary line */}
      <p className="results-meta">
        <strong>{totalFiltered}</strong> result{totalFiltered !== 1 ? "s" : ""}{" "}
        for <strong>"{query}"</strong> across{" "}
        <strong>{allPlatforms.length}</strong> platform{allPlatforms.length !== 1 ? "s" : ""}
        {selectedUnit && (
          <span className="results-meta-filter"> — filtered to {selectedUnit}</span>
        )}
      </p>

      {/* Unit filter chips — hidden if all products have the same unit */}
      <UnitFilter
        units={allUnits}
        selected={selectedUnit}
        onSelect={setSelectedUnit}
      />

      {/* Side-by-side platform columns */}
      <div className="platform-columns">
        {allPlatforms.map((platform) => {
          const meta  = PLATFORM_META[platform] || { label: platform, emoji: "🛒", accent: "#888" };
          const items = grouped[platform] || [];

          return (
            <div key={platform} className="platform-column">

              {/* Column header */}
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

              {/* Product cards — or a helpful message if none match the filter */}
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
    </section>
  );
}
