/**
 * utils.js — shared helper functions used across the frontend.
 */

/**
 * Normalise a raw unit string into a clean, consistent display label.
 *
 * Different platforms (and even different products on the same platform)
 * write the same unit in different ways:
 *   "1 L", "1l", "1 Ltr", "1litre", "1000 ml"  →  "1 L"
 *   "500 ml", "500ml", "500 mL"                  →  "500 ml"
 *   "200 g", "200g", "200 gm", "200 gms"         →  "200 g"
 *   "1 kg", "1kg", "1 KG"                        →  "1 kg"
 *
 * This ensures that filter chips group identical sizes together even
 * when the two platforms spell them differently.
 *
 * Returns the original string unchanged if it can't be parsed.
 */
export function normalizeUnit(raw) {
  if (!raw) return "";

  // Step 1: Strip trailing noise words that scrapers sometimes append.
  // e.g. "1 Ltr Pack" → "1 Ltr",  "500 ml Bottle" → "500 ml"
  // This mirrors the same strip done in the backend worker before saving,
  // and serves as a safety net for any data saved before that fix was applied.
  let s = raw.trim().replace(
    /\s+(pack|bottle|jar|can|bag|box|pouch|sachet|strip|carton|tin|tub|cup|each|set|roll|rolls|combo)\s*$/i,
    ""
  ).trim();

  // Step 2: Lowercase + remove all spaces so "1 Ltr" becomes "1ltr"
  const noSpace = s.toLowerCase().replace(/\s+/g, "");

  // Step 3: Must be digits (with optional decimal) followed by unit letters
  const match = noSpace.match(/^([\d.]+)([a-z]+)$/);
  if (!match) return raw.trim();

  const num      = match[1];   // e.g. "500"
  const unitPart = match[2];   // e.g. "ml"

  // Map every known variant to one canonical abbreviation
  const UNIT_MAP = {
    // Litres
    l: "L", ltr: "L", ltrs: "L",
    liter: "L", liters: "L",
    litre: "L", litres: "L",
    // Millilitres
    ml: "ml", millilitre: "ml", millilitres: "ml",
    milliliter: "ml", milliliters: "ml",
    // Grams
    g: "g", gm: "g", gms: "g",
    gram: "g", grams: "g",
    // Kilograms
    kg: "kg", kgs: "kg",
    kilogram: "kg", kilograms: "kg",
    // Pieces
    pc: "pc", pcs: "pc",
    piece: "pc", pieces: "pc",
    // Packets / sachets
    pkt: "pkt", pack: "pkt", packet: "pkt", packets: "pkt",
    sachet: "sachet", sachets: "sachet",
  };

  const canonical = UNIT_MAP[unitPart];
  // If the unit isn't in the map at all, return the original so we don't lose data
  if (!canonical) return raw.trim();

  const numVal = parseFloat(num);

  // Auto-upgrade large quantities to the next unit for cleaner display:
  // 1000 ml → 1 L,  2000 ml → 2 L,  1000 g → 1 kg
  if (canonical === "ml" && numVal >= 1000) return `${numVal / 1000} L`;
  if (canonical === "g"  && numVal >= 1000) return `${numVal / 1000} kg`;

  // Remove trailing zeroes: "1.0 L" → "1 L"
  return `${parseFloat(num).toString()} ${canonical}`;
}

/**
 * Convert a normalised unit string to millilitres (or milligrams for weights)
 * so units can be sorted in ascending quantity order.
 *
 * Examples: "200 ml" → 200,  "1 L" → 1000,  "500 g" → 500,  "1 kg" → 1000
 * Returns Infinity for anything that can't be parsed (pushes it to the end).
 */
export function unitToBaseValue(unit) {
  if (!unit) return Infinity;
  const match = unit.match(/^([\d.]+)\s*([a-zA-Z]+)$/);
  if (!match) return Infinity;

  const num = parseFloat(match[1]);
  const u   = match[2].toLowerCase();

  if (u === "l")   return num * 1000;   // convert litres → ml equivalent
  if (u === "kg")  return num * 1000;   // convert kg → g equivalent
  return num;                            // ml and g stay as-is
}
