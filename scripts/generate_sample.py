"""Rebuild the deterministic, fictional sample; no external data is used."""

import calendar
import csv
import random
from pathlib import Path

random.seed(42)
root = Path(__file__).resolve().parents[1]
target = root / "sales_dashboard" / "data" / "sample_sales.csv"
target.parent.mkdir(parents=True, exist_ok=True)
products = [
    ("Studio Headphones", "129.00", "Audio"),
    ("Wireless Speaker", "89.00", "Audio"),
    ("Mechanical Keyboard", "109.00", "Accessories"),
    ("USB-C Dock", "79.00", "Accessories"),
    ("Laptop Stand", "49.00", "Workspace"),
    ("Desk Mat", "29.00", "Workspace"),
]
rows = []
for month, count in enumerate([62, 78, 72, 103, 119, 142], 1):
    for _ in range(count):
        name, price, category = random.choices(products, [27, 23, 19, 15, 10, 6])[0]
        day = random.randint(1, calendar.monthrange(2026, month)[1])
        region = random.choices(
            ["North America", "Europe", "Asia Pacific", "Other"], [44, 29, 21, 6]
        )[0]
        rows.append(
            [
                f"SO-{10001 + len(rows)}",
                f"2026-{month:02d}-{day:02d}",
                name,
                str(random.randint(1, 5)),
                price,
                region,
                category,
                "USD",
            ]
        )
# Realistic quality problems, with deterministic, documented expected totals.
for i in range(18):
    rows[i][2] = " " + rows[i][2] + " "
for i in range(18, 30):
    year, month, day = rows[i][1].split("-")
    rows[i][1] = f"{month}/{day}/{year}"
rows.extend([r.copy() for r in rows[40:52]])
for i in range(4):
    row = rows[80 + i].copy()
    row[0], row[1] = f"INVALID-DATE-{i}", "2026-02-30"
    rows.append(row)
for i in range(3):
    row = rows[90 + i].copy()
    row[0], row[3] = f"INVALID-QTY-{i}", "-2"
    rows.append(row)
row = rows[100].copy()
row[0], row[2] = "MISSING-PRODUCT", ""
rows.append(row)
with target.open("w", newline="", encoding="utf-8") as stream:
    writer = csv.writer(stream)
    writer.writerow(
        ["order_id", "date", "product", "quantity", "unit_price", "region", "category", "currency"]
    )
    writer.writerows(rows)
print(f"Wrote {len(rows)} sample rows to {target.name}")
