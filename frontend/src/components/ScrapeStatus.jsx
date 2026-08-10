export default function ScrapeStatus({ message, itemsFound }) {
  return (
    <div className="status-bar">
      <span className="spinner" />
      <span className="status-msg">{message}</span>
      {itemsFound > 0 && (
        <span className="status-count">{itemsFound} items found so far</span>
      )}
    </div>
  );
}
