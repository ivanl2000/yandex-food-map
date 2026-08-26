"""Search logic for Yandex Food orders — range queries on indexed columns."""
import logging
import re
import sqlite3
from collections.abc import Generator
from typing import Any

from config import settings

logger = logging.getLogger("yf.search")

# Columns we select for every query
SELECT_STAR = "SELECT id, phone, name, created_at AS date, city, street, house, place_name, lat, lon, amount_rub FROM orders"


def _cap_first(s: str) -> str:
    """Capitalize the first letter of a string."""
    if not s or not s[0].isalpha():
        return s
    return s[0].upper() + s[1:]


def _range_query(
    cursor: sqlite3.Cursor,
    field: str,
    prefix: str,
    limit: int,
) -> list[dict[str, Any]]:
    """
    B-tree range query: ``field >= prefix AND field < prefix_next``.

    Leverages SQLite indexes instead of ``LIKE`` — fast on 20M+ rows.
    Returns up to *limit* rows as dicts.
    """
    if not prefix:
        return []

    prefix = prefix[:50]
    # Compute the next lexicographic string (safe for ascii-digits)
    nxt = prefix[:-1] + chr(ord(prefix[-1]) + 1) if prefix else "~"

    try:
        rows = cursor.execute(
            f"{SELECT_STAR} WHERE {field} >= ? AND {field} < ? LIMIT ?",
            (prefix, nxt, limit),
        )
        return [dict(r) for r in rows]
    except Exception:
        logger.exception("range query failed on %s=%r", field, prefix)
        return []


def _deduplicate(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Remove duplicate rows by id, preserving order."""
    seen: set[int] = set()
    out: list[dict[str, Any]] = []
    for r in results:
        if r["id"] not in seen:
            seen.add(r["id"])
            out.append(r)
    return out


def search_by_phone(
    cursor: sqlite3.Cursor,
    digits: str,
    limit: int,
) -> list[dict[str, Any]]:
    """Search by phone-number digits (numeric prefix match)."""
    return _range_query(cursor, "phone", digits, limit)


def search_by_name(
    cursor: sqlite3.Cursor,
    query: str,
    limit: int,
) -> list[dict[str, Any]]:
    """Search by customer name (lowercase + capitalized)."""
    results: list[dict[str, Any]] = []
    remaining = limit

    for variant in (query, _cap_first(query)):
        if remaining <= 0:
            break
        chunk = _range_query(cursor, "name", variant, remaining)
        results.extend(chunk)
        remaining -= len(chunk)

    return _deduplicate(results)


def search_by_city(
    cursor: sqlite3.Cursor,
    query: str,
    limit: int,
) -> list[dict[str, Any]]:
    """Search by city (lowercase + capitalized)."""
    results: list[dict[str, Any]] = []
    remaining = limit

    for variant in (query, _cap_first(query)):
        if remaining <= 0:
            break
        chunk = _range_query(cursor, "city", variant, remaining)
        results.extend(chunk)
        remaining -= len(chunk)

    return _deduplicate(results)


def search_by_place(
    cursor: sqlite3.Cursor,
    query: str,
    limit: int,
) -> list[dict[str, Any]]:
    """Search by place/restaurant name (lowercase + capitalized)."""
    results: list[dict[str, Any]] = []
    remaining = limit

    for variant in (query, _cap_first(query)):
        if remaining <= 0:
            break
        chunk = _range_query(cursor, "place_name", variant, remaining)
        results.extend(chunk)
        remaining -= len(chunk)

    return _deduplicate(results)


def search(query: str, limit: int | None = None) -> list[dict[str, Any]]:
    """
    Full-text-search across phones, names, cities and place names.

    Heuristics:
    - If the query looks like a phone number → try phone first, then fall back
    - Otherwise → name → city → place_name
    """
    limit = limit or settings.search_limit

    raw = (query or "").strip()
    if len(raw) < settings.min_query_length:
        return []

    q_lower = raw.lower()[:50]
    q_digits = re.sub(r"[^0-9]", "", q_lower)

    # Heuristic: mostly digits → it's a phone lookup
    is_phone = len(q_digits) >= 7 and (len(q_digits) >= len(q_lower) * 0.5)

    conn = sqlite3.connect(settings.db_path, timeout=5)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    results: list[dict[str, Any]] = []

    try:
        if is_phone or len(q_digits) >= 3:
            results = search_by_phone(cursor, q_digits, limit)
            if is_phone or len(results) >= limit:
                return results[:limit]

        # Name
        remaining = limit - len(results)
        if remaining > 0:
            results.extend(search_by_name(cursor, q_lower, remaining))

        # City
        remaining = limit - len(results)
        if remaining > 0:
            results.extend(search_by_city(cursor, q_lower, remaining))

        # Place name
        remaining = limit - len(results)
        if remaining > 0:
            results.extend(search_by_place(cursor, q_lower, remaining))

    finally:
        conn.close()

    return _deduplicate(results)[:limit]