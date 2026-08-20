/**
 * matcher.js — groups products from different platforms into comparison rows.
 *
 * The core problem: Blinkit calls it "Amul Gold Full Cream Milk" while Zepto
 * calls it "Amul Gold Milk" — but they are the same product. This module
 * detects when two products from different platforms are the same thing and
 * groups them into one comparison row.
 *
 * How it works:
 *   1. Group all products by their normalised unit (500 ml, 1 L, etc.).
 *      Only same-size products can be the same product.
 *   2. Within each unit group, cluster products whose names have high token
 *      overlap using the Jaccard similarity index.
 *   3. For each cluster, build one comparison row that shows the cheapest
 *      price per platform side by side.
 */

import { normalizeUnit } from "./utils";

// Minimum Jaccard score for two product names to be considered the same product.
// 0.35 means "at least 35% of unique words must match".
// Lower = more aggressive grouping (risk of false matches).
// Higher = stricter (risk of missing genuine matches with different wording).
const MATCH_THRESHOLD = 0.35;

// Words that appear in almost every product listing and add no useful signal
// for distinguishing one product from another.
const STOP_WORDS = new Set([
  "a", "an", "the", "and", "or", "of", "in", "with", "for",
  "pack", "packet", "bottle", "can", "jar", "box", "bag", "pouch",
]);

// ── Name tokenisation ─────────────────────────────────────────────────────────

/**
 * Break a product name into a list of meaningful lowercase tokens.
 * Punctuation is removed; very short tokens and stop words are dropped.
 *
 * "Amul Gold Full-Cream Milk" → ["amul", "gold", "full", "cream", "milk"]
 */
function tokenize(name) {
  return name
    .toLowerCase()
    .replace(/[^a-z0-9\s]/g, " ")   // punctuation → space
    .split(/\s+/)
    .filter((t) => t.length > 1 && !STOP_WORDS.has(t));
}

/**
 * Jaccard similarity between two arrays of tokens.
 * Returns a value between 0 (nothing in common) and 1 (identical word sets).
 *
 * Jaccard = |A ∩ B| / |A ∪ B|
 */
function jaccard(tokA, tokB) {
  const setA = new Set(tokA);
  const setB = new Set(tokB);
  const intersection = [...setA].filter((t) => setB.has(t)).length;
  const union = new Set([...setA, ...setB]).size;
  return union === 0 ? 0 : intersection / union;
}

// ── Clustering ────────────────────────────────────────────────────────────────

/**
 * Greedily cluster a list of products by name similarity.
 *
 * Each product either joins the most similar existing cluster (if the
 * Jaccard score exceeds MATCH_THRESHOLD) or starts a brand-new cluster.
 *
 * This is single-linkage clustering — fast and good enough for the small
 * product counts (≤ 30) that come back from each platform.
 */
function clusterByName(products) {
  const clusters = [];

  for (const product of products) {
    const tok = tokenize(product.name);
    let bestClusterIdx = -1;
    let bestScore = MATCH_THRESHOLD; // must beat this to join a cluster

    clusters.forEach((cluster, idx) => {
      cluster.forEach((member) => {
        const score = jaccard(tok, tokenize(member.name));
        if (score > bestScore) {
          bestScore = score;
          bestClusterIdx = idx;
        }
      });
    });

    if (bestClusterIdx >= 0) {
      clusters[bestClusterIdx].push(product);
    } else {
      clusters.push([product]); // start a new cluster
    }
  }

  return clusters;
}

// ── Public function ───────────────────────────────────────────────────────────

/**
 * Match all products across platforms into comparison groups.
 *
 * Each group in the returned array represents one "product" and contains
 * the cheapest listing from each platform that carries it:
 *
 *   {
 *     displayName,      // most descriptive name from the cluster
 *     unit,             // normalised unit, e.g. "1 L"
 *     platformData,     // { blinkit: product|null, zepto: product|null, … }
 *     cheapestPlatform, // which platform has the lowest price
 *     cheapestPrice,    // the lowest price across all platforms
 *     maxSaving,        // difference between most expensive and cheapest (₹)
 *     platformCount,    // how many platforms carry this product
 *   }
 *
 * Groups are sorted so multi-platform matches (the interesting comparisons)
 * appear first, then single-platform products.
 *
 * @param {Array}  products  Flat list of product objects from all platforms.
 * @param {Array}  platforms Ordered list of platform keys, e.g. ["blinkit", "zepto"].
 */
export function matchProducts(products, platforms) {
  // Step 1: Group by normalised unit — only compare same-size products.
  const byUnit = {};
  for (const p of products) {
    const unit = normalizeUnit(p.unit) || "unknown";
    if (!byUnit[unit]) byUnit[unit] = [];
    byUnit[unit].push(p);
  }

  const groups = [];

  for (const [unit, unitProducts] of Object.entries(byUnit)) {
    // Step 2: Cluster products within this unit group by name similarity.
    const clusters = clusterByName(unitProducts);

    for (const cluster of clusters) {
      // Step 3: For each platform, keep only the cheapest product in this cluster.
      // (Two Blinkit listings might cluster together — we want the better price.)
      const platformData = Object.fromEntries(
        platforms.map((platform) => [
          platform,
          cluster
            .filter((p) => p.source === platform)
            .sort((a, b) => a.price - b.price)[0] ?? null,
        ])
      );

      // Compute price stats for the "best deal" badge.
      const prices = Object.values(platformData)
        .filter(Boolean)
        .map((p) => p.price);

      const cheapestPrice = prices.length ? Math.min(...prices) : 0;

      const cheapestPlatform =
        Object.entries(platformData)
          .filter(([, p]) => p)
          .sort(([, a], [, b]) => a.price - b.price)[0]?.[0] ?? null;

      // Pick the most descriptive name from the cluster (longest wins).
      const displayName = cluster
        .map((p) => p.name)
        .sort((a, b) => b.length - a.length)[0];

      groups.push({
        displayName,
        unit,
        platformData,
        cheapestPlatform,
        cheapestPrice,
        platformCount: prices.length,
      });
    }
  }

  // Multi-platform groups first (most useful comparisons), then by price.
  return groups.sort(
    (a, b) => b.platformCount - a.platformCount || a.cheapestPrice - b.cheapestPrice
  );
}
