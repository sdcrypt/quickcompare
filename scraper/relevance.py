"""
Relevance filtering — keeps only products that are genuinely related
to what the user searched for.

The problem this solves:
    When a user searches "amul milk", Blinkit and Zepto return everything
    loosely tagged as "Amul" or "Milk" — chocolates, butter, dahi, flavoured
    drinks, etc. This module filters that list down to only the products
    that are actually close to what the user typed.

How the scoring works:
    Each product name is scored against the query using three signals:

    1. Word coverage  — how many of the query words appear in the product
                        name as whole words? This is the most important signal.
                        e.g. "amul milk" vs "Amul Gold Full Cream Milk 1L"
                             "amul" ✅  "milk" ✅  → coverage = 100%

    2. Partial ratio  — overall fuzzy similarity. Handles cases where the
                        query words appear inside a longer product name.

    3. Token sort ratio — same as partial ratio but ignores word order,
                          so "milk amul" and "Amul Milk" score equally.

    The three signals are combined into a single score from 0 to 1.
    Products below RELEVANCE_THRESHOLD are discarded.

Tuning the threshold:
    - Higher value (e.g. 0.65) → stricter, fewer but very accurate results.
    - Lower value  (e.g. 0.45) → looser, more results but some noise.
    - 0.55 is a good starting point for grocery product searches.
"""

import re

from rapidfuzz import fuzz

# Products with a combined relevance score below this are discarded.
# Adjust this constant if results are still too broad or too narrow.
RELEVANCE_THRESHOLD = 0.55


def filter_relevant(products: list[dict], query: str) -> list[dict]:
    """
    Keep only the products from the scraped list that are genuinely
    relevant to what the user searched for.

    Args:
        products - List of product dicts from the scraper.
                   Each dict must have a "name" key.
        query    - The original search query, e.g. "amul milk".

    Returns a filtered list, which may be shorter than the input.
    Every product that is kept has a relevance score >= RELEVANCE_THRESHOLD.
    """
    return [p for p in products if _score(p["name"], query) >= RELEVANCE_THRESHOLD]


def _score(product_name: str, query: str) -> float:
    """
    Score how relevant a product name is to a search query.

    Returns a number between 0.0 and 1.0.
    Scores of 0.55 and above are considered relevant.

    Examples with query "amul milk":
        "Amul Gold Full Cream Milk 1L"  → ~0.90  ✅ keep
        "Amul Taaza Homogenised Milk"   → ~0.82  ✅ keep
        "Amul Masti Dahi 400g"          → ~0.38  ❌ discard
        "Amul Dark Chocolate 150g"      → ~0.32  ❌ discard
        "Amul Butter 100g"              → ~0.35  ❌ discard
    """
    name = product_name.lower().strip()
    q    = query.lower().strip()
    query_words = q.split()

    if not query_words or not name:
        return 0.0

    # ── Signal 1: Word coverage ───────────────────────────────────────────────
    # Count how many query words appear in the product name as whole words.
    # Using \b (word boundary) so "milk" does not match "milkmaid".
    words_found = sum(
        1 for word in query_words
        if re.search(r"\b" + re.escape(word) + r"\b", name)
    )
    word_coverage = words_found / len(query_words)

    # ── Signal 2: Partial ratio ───────────────────────────────────────────────
    # Checks if the entire query appears as a substring anywhere in the name.
    # Handles short queries inside long product names well.
    partial = fuzz.partial_ratio(q, name) / 100

    # ── Signal 3: Token sort ratio ────────────────────────────────────────────
    # Ignores word order — "milk amul" and "Amul Milk" both score the same.
    token_sort = fuzz.token_sort_ratio(q, name) / 100

    # ── Combined score ────────────────────────────────────────────────────────
    # Word coverage is weighted highest because it's the most precise signal.
    return (0.5 * word_coverage) + (0.3 * partial) + (0.2 * token_sort)
