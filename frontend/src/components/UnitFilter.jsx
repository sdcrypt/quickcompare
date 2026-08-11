/**
 * UnitFilter — shows a row of size/unit chips so the user can narrow
 * results down to a specific pack size for a fair price comparison.
 *
 * Example chips rendered for "amul milk" results:
 *   [ All sizes ]  [ 200 ml ]  [ 500 ml ]  [ 1 L ]  [ 2 L ]
 *
 * Clicking a chip filters ALL platform columns to show only that size.
 * Clicking the active chip (or "All sizes") resets the filter.
 *
 * Props:
 *   units    - Sorted array of unique normalised unit strings to show as chips.
 *   selected - The currently active unit string, or null for "all".
 *   onSelect - Callback(unit | null) called when the user clicks a chip.
 */
export default function UnitFilter({ units, selected, onSelect }) {
  // Don't render anything if there's only one size — no point filtering
  if (!units || units.length <= 1) return null;

  return (
    <div className="unit-filter">
      <span className="unit-filter-label">Filter by size:</span>

      <div className="unit-chips">
        {/* "All sizes" resets the filter */}
        <button
          className={`unit-chip ${!selected ? "unit-chip--active" : ""}`}
          onClick={() => onSelect(null)}
        >
          All sizes
        </button>

        {units.map((unit) => (
          <button
            key={unit}
            className={`unit-chip ${selected === unit ? "unit-chip--active" : ""}`}
            onClick={() =>
              // Clicking the already-active chip deselects it
              onSelect(selected === unit ? null : unit)
            }
          >
            {unit}
          </button>
        ))}
      </div>
    </div>
  );
}
