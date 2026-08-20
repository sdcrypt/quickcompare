/**
 * constants.js — shared display config used across multiple components.
 *
 * Add a new entry here whenever a new platform scraper is added.
 * Every component that shows platform names or colours imports from here
 * so there is one place to update.
 */

export const PLATFORM_META = {
  blinkit:   { label: "Blinkit",          emoji: "🟢", accent: "#0f9e6e" },
  zepto:     { label: "Zepto",            emoji: "🟣", accent: "#7c3aed" },
  instamart: { label: "Swiggy Instamart", emoji: "🟠", accent: "#f97316" },
};
