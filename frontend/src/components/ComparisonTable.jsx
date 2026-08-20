/**
 * ComparisonTable — the core comparison view.
 *
 * Takes a flat list of products (from all platforms) and groups them into
 * comparison rows — one row per product, with a price cell for every platform
 * that carries it. The cheapest cell is highlighted in green.
 *
 * Layout of one row:
 *
 *   ┌─────────────────────────────────────────────────────────────────────┐
 *   │ [img]  Amul Gold Full Cream Milk            1 L      Save ₹3       │
 *   │        🟢 Blinkit  ₹68  │  🟣 Zepto  ₹65 ✓  │  🟠 Instamart  ₹67 │
 *   └─────────────────────────────────────────────────────────────────────┘
 *
 * Products that only appear on a single platform are shown in a separate
 * "Only on one platform" section below.
 *
 * Props:
 *   products  — flat array of product objects (all platforms combined)
 *   platforms — ordered array of platform keys, e.g. ["blinkit", "zepto"]
 */

import { matchProducts } from "../matcher";
import { PLATFORM_META } from "../constants";

export default function ComparisonTable({ products, platforms }) {
  const groups = matchProducts(products, platforms);

  if (groups.length === 0) {
    return <p className="empty-state">No products found.</p>;
  }

  const matched    = groups.filter((g) => g.platformCount > 1);
  const singleOnly = groups.filter((g) => g.platformCount === 1);

  return (
    <div className="comparison-table">

      {/* Quick summary */}
      <p className="comparison-stats">
        <strong>{matched.length}</strong> product{matched.length !== 1 ? "s" : ""}{" "}
        matched across platforms
        {singleOnly.length > 0 && (
          <span className="comparison-stats-secondary">
            {" "}· {singleOnly.length} only on one platform
          </span>
        )}
      </p>

      {/* ── Matched products — the real comparison ── */}
      {matched.length > 0 && (
        <div className="comparison-section">
          {matched.map((group, i) => (
            <ComparisonRow key={i} group={group} platforms={platforms} />
          ))}
        </div>
      )}

      {/* ── Single-platform products ── */}
      {singleOnly.length > 0 && (
        <>
          <p className="comparison-section-label">Only on one platform</p>
          <div className="comparison-section comparison-section--muted">
            {singleOnly.map((group, i) => (
              <ComparisonRow key={i} group={group} platforms={platforms} />
            ))}
          </div>
        </>
      )}
    </div>
  );
}

// ── Individual comparison row ─────────────────────────────────────────────────

function ComparisonRow({ group, platforms }) {
  const {
    displayName,
    unit,
    platformData,
    cheapestPlatform,
    platformCount,
  } = group;

  const isMulti   = platformCount > 1;
  const anyImage  = Object.values(platformData).find((p) => p?.image_url)?.image_url;
  const anyUrl    = Object.values(platformData).find((p) => p?.source_url)?.source_url;

  const rowContent = (
    <div className={`comparison-row ${isMulti ? "comparison-row--multi" : "comparison-row--single"}`}>

      {/* Product image */}
      <div className="comparison-img-wrap">
        {anyImage ? (
          <img src={anyImage} alt={displayName} loading="lazy" />
        ) : (
          <span className="comparison-img-placeholder">🛒</span>
        )}
      </div>

      {/* Product name + unit */}
      <div className="comparison-info">
        <span className="comparison-name">{displayName}</span>
        {unit && unit !== "unknown" && (
          <span className="comparison-unit">{unit}</span>
        )}
      </div>

      {/* Price cells — one per platform */}
      <div className="comparison-prices">
        {platforms.map((platform) => {
          const product = platformData[platform];
          const meta    = PLATFORM_META[platform] || { label: platform, emoji: "🛒", accent: "#888" };
          const isBest  = platform === cheapestPlatform && isMulti;

          return (
            <div
              key={platform}
              className={[
                "price-cell",
                isBest   ? "price-cell--best" : "",
                !product ? "price-cell--na"   : "",
              ].join(" ")}
              style={isBest ? { borderColor: meta.accent } : {}}
            >
              {/* Platform label */}
              <span className="price-cell-platform">
                {meta.emoji} {meta.label}
              </span>

              {product ? (
                <>
                  {/* Selling price */}
                  <span
                    className="price-cell-amount"
                    style={isBest ? { color: meta.accent } : {}}
                  >
                    ₹{product.price}
                  </span>

                  {/* Strikethrough MRP — only show if there's a real discount */}
                  {product.mrp && product.mrp > product.price && (
                    <span className="price-cell-mrp">₹{product.mrp}</span>
                  )}

                  {/* Best deal label */}
                  {isBest && (
                    <span
                      className="price-cell-best-label"
                      style={{ color: meta.accent }}
                    >
                      ✓ Best
                    </span>
                  )}
                </>
              ) : (
                <span className="price-cell-na">—</span>
              )}
            </div>
          );
        })}

      </div>
    </div>
  );

  // If we have a URL to the product, wrap the row in a link
  return anyUrl ? (
    <a href={anyUrl} target="_blank" rel="noreferrer" className="comparison-row-link">
      {rowContent}
    </a>
  ) : rowContent;
}
