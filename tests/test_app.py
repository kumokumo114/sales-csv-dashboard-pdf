import csv
import io
from pathlib import Path

import pytest
from flask import request
from pypdf import PdfReader

from sales_dashboard import create_app
from sales_dashboard.analysis import DataError, analyze, clean_csv


def csv_bytes(rows, headers=None, delimiter=","):
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, delimiter=delimiter)
    writer.writerow(headers or ["date", "product", "quantity", "unit_price", "order_id", "region"])
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


@pytest.fixture
def sample():
    return (Path(__file__).parents[1] / "sales_dashboard/data/sample_sales.csv").read_bytes()


@pytest.fixture
def client():
    return create_app({"TESTING": True}).test_client()


def upload(client, data, route="/api/analyze", **fields):
    return client.post(route, data={"file": (io.BytesIO(data), "sales.csv"), **fields})


def test_sample_cleaning_and_reconciliation(sample):
    rows, summary = clean_csv(sample)
    assert summary["input_rows"] == 596
    assert summary["clean_rows"] == 576
    assert summary["duplicate_rows"] == 12
    assert summary["invalid_date"] == 4
    assert summary["invalid_number"] == 3
    assert summary["missing_required"] == 1
    assert summary["normalized_rows"] == 30
    assert summary["clean_rows"] + summary["removed_rows"] == summary["input_rows"]
    data = analyze(rows, summary)
    assert data["metrics"]["orders"] == 576
    assert len(data["trend"]) == 6
    assert round(sum(p["revenue"] for p in data["trend"]), 2) == data["metrics"]["revenue"]
    assert sum(p["revenue"] for p in data["regions"]) == data["metrics"]["revenue"]


def test_decimal_money_distinct_orders_and_zero_months():
    payload = csv_bytes(
        [
            ["2026-01-01", "A", 3, "0.10", "ONE", "Europe"],
            ["2026-01-01", "B", 1, "0.20", "ONE", "Europe"],
            ["2026-03-01", "A", 2, "1.23", "TWO", "Europe"],
        ]
    )
    result = analyze(*clean_csv(payload))
    assert result["metrics"] == {
        "revenue": 2.96,
        "orders": 2,
        "units": 6,
        "average_order": 1.48,
        "rows": 3,
    }
    assert result["trend"][1] == {"month": "2026-02", "revenue": 0.0}


def test_headers_aliases_bom_and_semicolon():
    payload = csv_bytes(
        [["01/03/2026", "  Desk  ", "2", "1,200.50"]],
        [" Order Date ", "Product Name", "Qty", "Unit Price"],
        ";",
    )
    rows, summary = clean_csv(b"\xef\xbb\xbf" + payload)
    assert rows[0]["date"] == "2026-01-03"
    assert str(rows[0]["revenue"]) == "2401.00"
    assert rows[0]["region"] == "Unknown"
    assert summary["normalized_rows"] == 1
    assert summary["missing_order_ids"] == 1


@pytest.mark.parametrize(
    "payload,match",
    [
        (b"", "empty"),
        (b"\xff\xfe", "UTF-8"),
        (b"abc\x00def", "binary"),
        (b"date,quantity\n2026-01-01,1", "Missing required"),
        (b"date,Date,product,quantity,unit_price\n", "unique"),
        (b"date,product,quantity,unit_price\n", "No usable"),
        (b'date,product,quantity,unit_price\n2026-01-01,"open,1,1', "parsed"),
    ],
)
def test_invalid_file_messages(payload, match):
    with pytest.raises(DataError, match=match):
        clean_csv(payload)


@pytest.mark.parametrize(
    "quantity,price",
    [
        ("-1", "1"),
        ("1.5", "1"),
        ("0", "1"),
        ("1", "NaN"),
        ("1", "Infinity"),
        ("1", "1,23"),
        ("1", "$12"),
        ("1", "-2"),
        ("1", "0.001"),
        ("1000001", "1"),
        ("1", "1e3"),
    ],
)
def test_invalid_numbers_are_excluded(quantity, price):
    payload = csv_bytes(
        [
            ["2026-01-01", "A", quantity, price, "bad", "EU"],
            ["2026-01-01", "B", "1", "1.00", "ok", "EU"],
        ]
    )
    rows, summary = clean_csv(payload)
    assert len(rows) == 1
    assert summary["invalid_number"] == 1


def test_deduplication_after_normalization_and_ids():
    payload = csv_bytes(
        [
            ["2026-01-01", " A ", 1, "1.00", "1", "EU"],
            ["01/01/2026", "A", 1, "1", "1", "EU"],
            ["2026-01-01", "A", 1, "1.00", "2", "EU"],
        ]
    )
    rows, summary = clean_csv(payload)
    assert len(rows) == 2
    assert summary["duplicate_rows"] == 1
    assert analyze(rows, summary)["metrics"]["orders"] == 2


def test_missing_ids_do_not_collide_with_real_ids():
    payload = csv_bytes(
        [["2026-01-01", "A", 1, "1", "row-3", "EU"], ["2026-01-01", "B", 1, "1", "", "EU"]]
    )
    assert analyze(*clean_csv(payload))["metrics"]["orders"] == 2


def test_free_product_valid():
    payload = csv_bytes([["2026-01-01", "Gift", 1, "0", "1", "EU"]])
    assert analyze(*clean_csv(payload))["metrics"]["revenue"] == 0


@pytest.mark.parametrize("currencies", [["USD", "EUR"], ["JPY", "JPY"], ["", "EUR"]])
def test_mixed_or_unsupported_currencies_fail(currencies):
    payload = csv_bytes(
        [["2026-01-01", "A", 1, "1", c] for c in currencies],
        ["date", "product", "quantity", "unit_price", "currency"],
    )
    with pytest.raises(DataError, match="currenc"):
        clean_csv(payload)


def test_currency_normalized():
    payload = csv_bytes(
        [["2026-01-01", "A", 1, "1", "eur"]],
        ["date", "product", "quantity", "unit_price", "currency"],
    )
    assert analyze(*clean_csv(payload))["currency"] == "EUR"


def test_malformed_and_long_fields_excluded():
    payload = csv_bytes(
        [
            ["2026-01-01", "A", 1, "1", "ok", "EU"],
            ["2026-01-01", "B", 1, "1"],
            ["2026-01-01", "X" * 257, 1, "1", "long", "EU"],
        ]
    )
    rows, summary = clean_csv(payload)
    assert len(rows) == 1
    assert summary["malformed_rows"] == 2


def test_filtered_metrics_keep_source_summary(client, sample):
    response = upload(client, sample, start="2026-03-01", end="2026-03-31", region="Europe")
    assert response.status_code == 200
    data = response.json
    assert data["summary"]["clean_rows"] == 576
    assert 0 < data["metrics"]["rows"] < 72
    assert all(
        row["region"] == "Europe" and row["date"].startswith("2026-03") for row in data["preview"]
    )


@pytest.mark.parametrize(
    "filters",
    [{"start": "bad"}, {"start": "2026-03-01", "end": "2026-01-01"}, {"region": "Unknown region"}],
)
def test_invalid_filters(client, sample, filters):
    response = upload(client, sample, **filters)
    assert response.status_code == 400
    assert response.json["error"]


def test_empty_selection_disables_report(client, sample):
    response = upload(client, sample, start="2027-01-01")
    assert response.status_code == 200
    assert response.json["metrics"]["rows"] == 0
    assert response.json["preview"] == []
    response = upload(client, sample, "/api/report", start="2027-01-01")
    assert response.status_code == 400


def test_pdf_has_two_pages_matching_metrics_and_filters(client, sample):
    filters = {"start": "2026-03-01", "end": "2026-03-31", "region": "Europe"}
    data = upload(client, sample, **filters).json
    response = upload(client, sample, "/api/report", **filters)
    assert response.status_code == 200
    assert response.mimetype == "application/pdf"
    assert "attachment; filename=sales-report.pdf" == response.headers["Content-Disposition"]
    assert response.data.startswith(b"%PDF-")
    pdf = PdfReader(io.BytesIO(response.data))
    assert len(pdf.pages) == 2
    text = "\n".join(page.extract_text() for page in pdf.pages)
    assert f"USD {data['metrics']['revenue']:,.2f}" in text
    assert "Europe" in text and "2026-03-01" in text
    assert "Data quality & methodology" in text
    assert "576" in text


def test_pdf_accepts_long_non_ascii_labels(client):
    payload = csv_bytes([["2026-01-01", "Café " + "A" * 200, 1, "2.00", "1", "Région"]])
    response = upload(client, payload, "/api/report")
    assert response.status_code == 200
    assert len(PdfReader(io.BytesIO(response.data)).pages) == 2


def test_routes_and_security_headers(client):
    assert client.get("/").status_code == 200
    assert client.get("/health").json == {"status": "ok"}
    assert client.get("/sample.csv").data.startswith(b"order_id,")
    assert client.get("/").headers["X-Content-Type-Options"] == "nosniff"
    assert "default-src 'self'" in client.get("/").headers["Content-Security-Policy"]
    assert client.post("/api/analyze").status_code == 400
    assert client.post("/api/analyze").headers["Cache-Control"] == "no-store"


def test_size_and_extension_limits(client):
    client.application.config["MAX_CONTENT_LENGTH"] = 100
    assert upload(client, b"a" * 101).status_code == 413
    client.application.config["MAX_CONTENT_LENGTH"] = 10000
    response = client.post("/api/analyze", data={"file": (io.BytesIO(b"hi"), "sales.xlsx")})
    assert response.status_code == 400


def test_row_limit(monkeypatch):
    monkeypatch.setattr("sales_dashboard.analysis.MAX_ROWS", 1)
    with pytest.raises(DataError, match="too many"):
        clean_csv(
            csv_bytes([["2026-01-01", "A", 1, 1, "1", "EU"], ["2026-01-02", "B", 1, 1, "2", "EU"]])
        )


def test_precision_bound():
    with pytest.raises(DataError, match="1 trillion"):
        clean_csv(csv_bytes([["2026-01-01", "A", 1_000_000, 1_000_000_000, "1", "EU"]]))


def test_script_like_product_is_data(client):
    payload = csv_bytes([["2026-01-01", '<script>alert("x")</script>', 1, 1, "1", "EU"]])
    response = upload(client, payload)
    assert response.status_code == 200
    assert response.json["preview"][0]["product"] == '<script>alert("x")</script>'


def test_uploads_over_werkzeug_spool_threshold_remain_in_memory():
    app = create_app({"TESTING": True})
    with app.test_request_context(
        "/api/analyze", method="POST", data={"file": (io.BytesIO(b"x" * 600_000), "large.csv")}
    ):
        assert isinstance(request.files["file"].stream, io.BytesIO)
