/**
 * ProductGrid — displays results grouped by platform side by side.
 *
 * Instead of one flat list, results are split into one column per platform
 * (Blinkit on the left, Zepto on the right). Each column has a header showing
 * the platform name and how many items were found.
 *
 * On narrow screens the columns stack vertically so it still reads cleanly
 * on mobile.
 *
 * If only one platform returned results (e.g. the other scrape failed),
 * that single column expands to fill the full width automatically.
 */

import ProductCard from "./ProductCard";

// Display config for each platform — add new platforms here as scrapers are built
const PLATFORM_META = {
  blinkit: { label: "Blinkit",  emoji: "🟢", accent: "#0f9e6e" },
  zepto:   { label: "Zepto",    emoji: "🟣", accent: "#7c3aed" },
  instamart: { label: "Swiggy Instamart", emoji: "🟠", accent: "#f97316" },
};

export default function ProductGrid({ products, query }) {
  // Split the flat product list into groups, one per platform
  const grouped = products.reduce((acc, product) => {
    const key = product.source || "unknown";
    if (!acc[key]) acc[key] = [];
    acc[key].push(product);
    return acc;
  }, {});

  const platforms   = Object.keys(grouped);
  const totalCount  = products.length;

  return (
    <section className="results-section">

      {/* Summary line above the columns */}
      <p className="results-meta">
        <strong>{totalCount}</strong> result{totalCount !== 1 ? "s" : ""} for{" "}
        <strong>"{query}"</strong> across{" "}
        <strong>{platforms.length}</strong> platform{platforms.length !== 1 ? "s" : ""}
      </p>

      {/* Side-by-side platform columns */}
      <div className="platform-columns">
        {platforms.map((platform) => {
          const meta  = PLATFORM_META[platform] || { label: platform, emoji: "🛒", accent: "#888" };
          const items = grouped[platform];

          return (
            <div key={platform} className="platform-column">

              {/* Column header — platform name + item count */}
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

              {/* Product cards inside this column */}
              <div className="platform-product-grid">
                {items.map((p) => (
                  <ProductCard key={p.id} product={p} />
                ))}
              </div>

            </div>
          );
        })}
      </div>
    </section>
  );
}
