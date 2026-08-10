"""
Product database table definition.

Each row in this table represents one product that was scraped from a
shopping site (currently Blinkit). When a user searches for "amul milk",
every result that comes back from the scraper gets saved here so the next
person who searches the same thing gets an instant answer from the database
instead of waiting for a fresh scrape.
"""

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String, Text

from app.db.session import Base


class Product(Base):
    """
    Stores a single scraped product.

    Columns:
        id           - Auto-generated unique number for each row.
        name         - The product name as shown on the website, e.g. "Amul Gold Milk".
        price        - The price the customer actually pays (in rupees).
        mrp          - The original printed price before any discount.
        unit         - The pack size, e.g. "1 L" or "500 g".
        category     - Product category if available, e.g. "Dairy".
        image_url    - Link to the product photo.
        source_url   - The page on Blinkit where this product was found.
        search_query - The search term that returned this product, stored in
                       lowercase so lookups are consistent ("Amul Milk" and
                       "amul milk" both map to the same rows).
        source       - Which website this came from. Always "blinkit" for now.
        in_stock     - Whether the item was available at the time of scraping.
        scraped_at   - When this row was saved. Used to decide if the data is
                       fresh enough to show, or if a new scrape is needed.
    """

    __tablename__ = "products"

    id           = Column(Integer, primary_key=True, index=True)
    name         = Column(String, nullable=False)
    price        = Column(Float)                    # selling price in ₹
    mrp          = Column(Float)                    # original / strike-through price
    unit         = Column(String)                   # e.g. "1 L", "500 g"
    category     = Column(String)
    image_url    = Column(Text)
    source_url   = Column(Text)                     # deeplink on Blinkit
    search_query = Column(String, index=True)       # the query that fetched this row
    source       = Column(String, default="blinkit")
    in_stock     = Column(Boolean, default=True)
    scraped_at   = Column(DateTime, default=datetime.utcnow)
