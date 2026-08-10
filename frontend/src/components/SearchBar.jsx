import { useState } from "react";

export default function SearchBar({ onSearch, disabled }) {
  const [value, setValue] = useState("");

  const handleSubmit = (e) => {
    e.preventDefault();
    const q = value.trim();
    if (q) onSearch(q);
  };

  return (
    <form className="search-form" onSubmit={handleSubmit}>
      <input
        className="search-input"
        type="text"
        placeholder='Search a product, e.g. "amul milk"'
        value={value}
        onChange={(e) => setValue(e.target.value)}
        disabled={disabled}
      />
      <button className="search-btn" type="submit" disabled={disabled || !value.trim()}>
        {disabled ? "Searching…" : "Compare"}
      </button>
    </form>
  );
}
