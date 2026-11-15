"""Deterministic CSV validation and exact-decimal sales calculations."""

import csv
import io
import re
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

MAX_ROWS = 25_000
CENT = Decimal("0.01")
CURRENCIES = {"USD", "EUR", "GBP", "CAD", "AUD"}
ALIASES = {
    "order_date": "date",
    "sale_date": "date",
    "sales_date": "date",
    "product_name": "product",
    "item": "product",
    "qty": "quantity",
    "price": "unit_price",
    "unitprice": "unit_price",
    "order": "order_id",
    "order_number": "order_id",
    "sales_region": "region",
}
REQUIRED = {"date", "product", "quantity", "unit_price"}
OPTIONAL = {"order_id", "region", "category", "currency"}


class DataError(ValueError):
    """An actionable error suitable for the upload form."""


def parse_date(value):
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y"):
        try:
            parsed = datetime.strptime(value, fmt).date()
            if not 1900 <= parsed.year <= 2100:
                break
            return parsed.isoformat()
        except ValueError:
            continue
    raise ValueError("invalid date")


def parse_number(value):
    # Only decimal points and properly grouped thousands are accepted.
    if not re.fullmatch(r"[+]?(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d+)?", value):
        raise ValueError("invalid number")
    try:
        result = Decimal(value.replace(",", ""))
        if not result.is_finite() or result > Decimal("1000000000"):
            raise ValueError("number outside supported range")
        return result
    except InvalidOperation as exc:
        raise ValueError("invalid number") from exc


def clean_csv(payload):
    try:
        text = payload.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise DataError("Save your CSV with UTF-8 encoding, then try again.") from exc
    if not text.strip():
        raise DataError("This CSV is empty. Add a header and at least one sales row.")
    if "\x00" in text:
        raise DataError("This file contains binary data. Upload a UTF-8 CSV.")
    first_line = text.splitlines()[0]
    delimiter = ";" if first_line.count(";") > first_line.count(",") else ","
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=delimiter, strict=True)
    try:
        original_headers = next(reader)
        headers = [re.sub(r"[\s-]+", "_", h.strip().lower()) for h in original_headers]
        headers = [ALIASES.get(h, h) for h in headers]
        if len(headers) > 50:
            raise DataError("Use a CSV with no more than 50 columns.")
        if len(headers) != len(set(headers)) or "" in headers:
            raise DataError("Column names must be unique and non-empty after normalization.")
        missing = sorted(REQUIRED - set(headers))
        if missing:
            raise DataError("Missing required columns: " + ", ".join(missing) + ".")
        summary = {
            "input_rows": 0,
            "clean_rows": 0,
            "removed_rows": 0,
            "normalized_rows": 0,
            "duplicate_rows": 0,
            "missing_required": 0,
            "invalid_date": 0,
            "invalid_number": 0,
            "malformed_rows": 0,
            "missing_optional_rows": 0,
            "ignored_columns": sorted(set(headers) - REQUIRED - OPTIONAL),
            "issues": [],
            "has_order_ids": "order_id" in headers,
        }
        rows, seen, currencies = [], set(), set()
        total_revenue = Decimal(0)

        def reject(reason, line):
            summary[reason] += 1
            if len(summary["issues"]) < 20:
                summary["issues"].append({"line": line, "reason": reason})

        for fields in reader:
            if not fields or all(not v.strip() for v in fields):
                continue
            summary["input_rows"] += 1
            if summary["input_rows"] > MAX_ROWS:
                raise DataError("This file has too many rows. The limit is 25,000 sales rows.")
            line = reader.line_num
            if len(fields) != len(headers) or any(len(v) > 256 for v in fields):
                reject("malformed_rows", line)
                continue
            raw = dict(zip(headers, fields))
            item = {k: v.strip() for k, v in raw.items() if k in REQUIRED | OPTIONAL}
            if any(not item[k] for k in REQUIRED):
                reject("missing_required", line)
                continue
            try:
                parsed_date = parse_date(item["date"])
            except ValueError:
                reject("invalid_date", line)
                continue
            try:
                quantity = parse_number(item["quantity"])
                price = parse_number(item["unit_price"])
                if (
                    quantity <= 0
                    or quantity > 1_000_000
                    or quantity != quantity.to_integral_value()
                ):
                    raise ValueError("quantity must be a positive integer")
                if price < 0 or price != price.quantize(CENT):
                    raise ValueError("price must have at most two decimal places")
            except ValueError:
                reject("invalid_number", line)
                continue
            currency = item.get("currency", "").upper() or "USD"
            if currency not in CURRENCIES:
                raise DataError("Unsupported currency. Use USD, EUR, GBP, CAD or AUD.")
            currencies.add(currency)
            if len(currencies) > 1:
                raise DataError(
                    "Mixed currencies found. Upload one currency at a time; no exchange conversion is applied."
                )
            row = {
                "date": parsed_date,
                "product": item["product"],
                "quantity": int(quantity),
                "unit_price": price.quantize(CENT),
                "order_id": item.get("order_id", ""),
                "region": item.get("region") or "Unknown",
                "category": item.get("category") or "Uncategorized",
                "currency": currency,
            }
            key = tuple(row.values())
            if key in seen:
                reject("duplicate_rows", line)
                continue
            seen.add(key)
            if (
                any(raw[k] != item[k] for k in item)
                or parsed_date != item["date"]
                or "," in item["unit_price"]
                or "," in item["quantity"]
                or item.get("currency", currency) != currency
            ):
                summary["normalized_rows"] += 1
            if not item.get("region") or not item.get("category") or not item.get("order_id"):
                summary["missing_optional_rows"] += 1
            row["revenue"] = (quantity * price).quantize(CENT, rounding=ROUND_HALF_UP)
            total_revenue += row["revenue"]
            if total_revenue > Decimal("1000000000000"):
                raise DataError(
                    "Total revenue exceeds the supported limit of 1 trillion. Split this CSV into smaller reports."
                )
            # A missing ID is one transaction per row; tuple keys avoid collisions with real IDs.
            row["order_key"] = ("id", row["order_id"]) if row["order_id"] else ("row", line)
            rows.append(row)
        summary["clean_rows"] = len(rows)
        summary["removed_rows"] = summary["input_rows"] - len(rows)
        summary["currency"] = next(iter(currencies), "USD")
        summary["missing_order_ids"] = sum(not r["order_id"] for r in rows)
        if not rows:
            raise DataError(
                "No usable sales rows remain. Check dates, required fields, positive whole quantities and non-negative prices (up to two decimals)."
            )
        return rows, summary
    except csv.Error as exc:
        raise DataError(
            "The CSV could not be parsed. Check quoting and column separators."
        ) from exc


def as_money(value):
    return float(value.quantize(CENT, rounding=ROUND_HALF_UP))


def analyze(rows, summary, filters=None):
    filters = filters or {}
    start, end = filters.get("start", ""), filters.get("end", "")
    region = filters.get("region", "")
    for value in (start, end):
        if value:
            try:
                if date.fromisoformat(value).isoformat() != value:
                    raise ValueError
            except ValueError as exc:
                raise DataError("Filter dates must use YYYY-MM-DD.") from exc
    if start and end and start > end:
        raise DataError("The start date must be on or before the end date.")
    regions = sorted({r["region"] for r in rows})
    if region and region not in regions:
        raise DataError("Choose a region present in this CSV.")
    selected = [
        r
        for r in rows
        if (not start or r["date"] >= start)
        and (not end or r["date"] <= end)
        and (not region or r["region"] == region)
    ]
    revenue = sum((r["revenue"] for r in selected), Decimal(0))
    orders = len({r["order_key"] for r in selected})
    monthly = defaultdict(lambda: Decimal(0))
    products = defaultdict(lambda: {"revenue": Decimal(0), "units": 0})
    region_totals = defaultdict(lambda: Decimal(0))
    for row in selected:
        monthly[row["date"][:7]] += row["revenue"]
        products[row["product"]]["revenue"] += row["revenue"]
        products[row["product"]]["units"] += row["quantity"]
        region_totals[row["region"]] += row["revenue"]
    # Include empty months between observed dates so the trend does not conceal gaps.
    if monthly:
        month, last = min(monthly), max(monthly)
        while month < last:
            monthly[month] += Decimal(0)
            year, number = map(int, month.split("-"))
            month = f"{year + (number == 12):04d}-{number % 12 + 1:02d}"
    trend = [{"month": m, "revenue": as_money(v)} for m, v in sorted(monthly.items())]
    top_products = [
        {"name": k, "revenue": as_money(v["revenue"]), "units": v["units"]}
        for k, v in sorted(products.items(), key=lambda i: (-i[1]["revenue"], i[0]))[:5]
    ]
    breakdown = [
        {"name": k, "revenue": as_money(v)}
        for k, v in sorted(region_totals.items(), key=lambda i: (-i[1], i[0]))
    ]
    preview = [
        {k: as_money(v) if isinstance(v, Decimal) else v for k, v in r.items() if k != "order_key"}
        for r in sorted(selected, key=lambda r: r["date"], reverse=True)[:50]
    ]
    return {
        "summary": summary,
        "currency": summary["currency"],
        "metrics": {
            "revenue": as_money(revenue),
            "orders": orders,
            "units": sum(r["quantity"] for r in selected),
            "average_order": as_money(revenue / orders) if orders else 0,
            "rows": len(selected),
        },
        "trend": trend,
        "products": top_products,
        "regions": breakdown,
        "preview": preview,
        "available_regions": regions,
        "filters": {"start": start, "end": end, "region": region},
        "date_range": {
            "start": min((r["date"] for r in selected), default=None),
            "end": max((r["date"] for r in selected), default=None),
        },
        "full_range": {"start": min(r["date"] for r in rows), "end": max(r["date"] for r in rows)},
    }
