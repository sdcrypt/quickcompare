/**
 * ScrapeStatus — shows live progress for each platform being scraped.
 *
 * Instead of a single "loading..." message, this shows one row per platform
 * so the user can see exactly what's happening:
 *
 *   ⏳ Fetching prices…
 *      🟡 Blinkit    scraping...
 *      🟢 Zepto      ✓ 14 items found
 */

const PLATFORM_LABELS = {
  blinkit:  "Blinkit",
  zepto:    "Zepto",
  instamart: "Swiggy Instamart",
};

const STATUS_CONFIG = {
  pending:   { icon: "⏸",  label: "queued",       className: "status-pending"   },
  running:   { icon: "🔄", label: "scraping...",   className: "status-running"   },
  completed: { icon: "✅", label: "",              className: "status-completed" },
  failed:    { icon: "❌", label: "failed",        className: "status-failed"    },
};

export default function ScrapeStatus({ platformStatuses }) {
  if (!platformStatuses || platformStatuses.length === 0) return null;

  const doneCount = platformStatuses.filter(
    (s) => s.status === "completed" || s.status === "failed"
  ).length;

  return (
    <div className="status-card">
      {/* Header row */}
      <div className="status-header">
        <span className="spinner" />
        <span className="status-heading">
          Fetching prices… ({doneCount}/{platformStatuses.length} done)
        </span>
      </div>

      {/* One row per platform */}
      <ul className="platform-list">
        {platformStatuses.map((ps) => {
          const cfg   = STATUS_CONFIG[ps.status] || STATUS_CONFIG.pending;
          const label = PLATFORM_LABELS[ps.platform] || ps.platform;

          return (
            <li key={ps.job_id} className={`platform-row ${cfg.className}`}>
              <span className="platform-icon">{cfg.icon}</span>
              <span className="platform-name">{label}</span>
              <span className="platform-detail">
                {ps.status === "completed"
                  ? `${ps.items_count} item${ps.items_count !== 1 ? "s" : ""} found`
                  : ps.status === "failed"
                  ? ps.error || "something went wrong"
                  : cfg.label}
              </span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
