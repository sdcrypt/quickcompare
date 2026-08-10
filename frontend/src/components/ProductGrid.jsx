import ProductCard from "./ProductCard";

export default function ProductGrid({ products, query }) {
  return (
    <section className="results-section">
      <p className="results-meta">
        {products.length} result{products.length !== 1 ? "s" : ""} for{" "}
        <strong>"{query}"</strong> on Blinkit
      </p>
      <div className="product-grid">
        {products.map((p) => (
          <ProductCard key={p.id} product={p} />
        ))}
      </div>
    </section>
  );
}
