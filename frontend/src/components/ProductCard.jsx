export default function ProductCard({ product }) {
  const { name, price, mrp, unit, image_url, source_url } = product;

  const discount =
    mrp && mrp > price ? Math.round(((mrp - price) / mrp) * 100) : 0;

  return (
    <a
      className="product-card"
      href={source_url || "#"}
      target="_blank"
      rel="noopener noreferrer"
    >
      <div className="card-img-wrap">
        {image_url ? (
          <img src={image_url} alt={name} loading="lazy" />
        ) : (
          <div className="card-img-placeholder">🛒</div>
        )}
        {discount > 0 && (
          <span className="discount-badge">{discount}% off</span>
        )}
      </div>

      <div className="card-body">
        <p className="card-name">{name}</p>
        {unit && <p className="card-unit">{unit}</p>}
        <div className="card-pricing">
          <span className="card-price">₹{price}</span>
          {discount > 0 && <span className="card-mrp">₹{mrp}</span>}
        </div>
      </div>
    </a>
  );
}
