"""A two-page, vector PDF built from the same analysis as the dashboard."""

import io
from datetime import datetime, timezone
from pathlib import Path

import reportlab
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

FONT_DIR = Path(reportlab.__file__).parent / "fonts"
pdfmetrics.registerFont(TTFont("Dashboard", str(FONT_DIR / "Vera.ttf")))
pdfmetrics.registerFont(TTFont("DashboardBold", str(FONT_DIR / "VeraBd.ttf")))
INK = colors.HexColor("#182c29")
MUTED = colors.HexColor("#667873")
GREEN = colors.HexColor("#167c61")
PALE = colors.HexColor("#edf6f2")
LINE = colors.HexColor("#dce5e0")
WIDTH, HEIGHT = A4


def build_report(data):
    stream = io.BytesIO()
    pdf = canvas.Canvas(stream, pagesize=A4)
    pdf.setTitle("Sales CSV Dashboard & PDF Report")
    pdf.setAuthor("Sales CSV Dashboard")
    currency = data["currency"]

    def label(text, x, y, size=10, bold=False, color=INK, max_width=None):
        font = "DashboardBold" if bold else "Dashboard"
        text = str(text).replace("\n", " ").replace("\r", " ")
        glyphs = pdfmetrics.getFont(font).face.charToGlyph
        text = "".join(char if ord(char) in glyphs else "?" for char in text)
        # Vector text uses an embedded open font. Clip long user-supplied labels.
        if max_width:
            while text and pdfmetrics.stringWidth(text, font, size) > max_width:
                text = text[:-2].rstrip() + "…" if len(text) > 2 else ""
        pdf.setFillColor(color)
        pdf.setFont(font, size)
        pdf.drawString(x, y, text)

    def rule(y):
        pdf.setStrokeColor(LINE)
        pdf.line(40, y, WIDTH - 40, y)

    def money(value):
        return f"{currency} {value:,.2f}"

    def header(page, title, subtitle):
        pdf.setFillColor(GREEN)
        pdf.roundRect(40, HEIGHT - 67, 27, 27, 7, fill=1, stroke=0)
        label("S", 48, HEIGHT - 59, 16, True, colors.white)
        label("SALESBOARD", 77, HEIGHT - 50, 10, True)
        label("Sales CSV Dashboard & PDF Report", 77, HEIGHT - 64, 8, color=MUTED)
        label(f"REPORT  /  {page:02}", WIDTH - 132, HEIGHT - 54, 9, color=MUTED)
        rule(HEIGHT - 84)
        label(title, 40, HEIGHT - 123, 25, True)
        label(subtitle, 40, HEIGHT - 145, 9, color=MUTED, max_width=WIDTH - 80)
        rule(49)
        label("Salesboard  •  Generated from your cleaned CSV", 40, 32, 8, color=MUTED)
        label(f"{page} / 2", WIDTH - 66, 32, 8, color=MUTED)

    interval = data["date_range"]
    selection = f"{interval['start']} - {interval['end']}  |  {data['filters']['region'] or 'All regions'}  |  {currency}"
    header(1, "Sales performance", selection)
    metrics = data["metrics"]
    cards = [
        ("TOTAL REVENUE", money(metrics["revenue"])),
        ("TOTAL ORDERS", f"{metrics['orders']:,}"),
        ("AVG. ORDER VALUE", money(metrics["average_order"])),
        ("UNITS SOLD", f"{metrics['units']:,}"),
    ]
    card_width = (WIDTH - 92) / 2
    for index, (title, value) in enumerate(cards):
        x = 40 + (index % 2) * (card_width + 12)
        y = HEIGHT - 239 - (index // 2) * 79
        pdf.setFillColor(PALE)
        pdf.roundRect(x, y, card_width, 67, 8, fill=1, stroke=0)
        label(title, x + 15, y + 46, 8, color=MUTED)
        label(value, x + 15, y + 18, 17 if len(value) < 20 else 11, True, max_width=card_width - 30)

    label("Revenue over time", 40, 493, 13, True)
    label("Monthly revenue · zero-sales months included", 40, 476, 8, color=MUTED)
    trend = data["trend"]
    ceiling = max((p["revenue"] for p in trend), default=0) or 1
    chart_x, chart_y, chart_w, chart_h = 84, 285, WIDTH - 139, 160
    for tick in range(5):
        y = chart_y + chart_h * tick / 4
        pdf.setStrokeColor(LINE)
        pdf.line(chart_x, y, chart_x + chart_w, y)
        value = ceiling * tick / 4
        label(
            f"{value / 1000:,.0f}k" if value >= 1000 else f"{value:,.0f}", 40, y - 3, 8, color=MUTED
        )
    points = [
        (chart_x + i * chart_w / max(1, len(trend) - 1), chart_y + p["revenue"] / ceiling * chart_h)
        for i, p in enumerate(trend)
    ]
    if points:
        area = pdf.beginPath()
        area.moveTo(points[0][0], chart_y)
        for x, y in points:
            area.lineTo(x, y)
        area.lineTo(points[-1][0], chart_y)
        area.close()
        pdf.setFillColor(PALE)
        pdf.drawPath(area, fill=1, stroke=0)
        path = pdf.beginPath()
        path.moveTo(*points[0])
        for x, y in points[1:]:
            path.lineTo(x, y)
        pdf.setStrokeColor(GREEN)
        pdf.setLineWidth(2)
        pdf.drawPath(path)
        for i in sorted({0, len(trend) // 2, len(trend) - 1}):
            x, y = points[i]
            pdf.setFillColor(GREEN)
            pdf.circle(x, y, 3, fill=1, stroke=0)
            label(trend[i]["month"], x - 16, chart_y - 19, 8, color=MUTED)
    label("Top products", 40, 231, 13, True)
    label("REVENUE", WIDTH - 135, 231, 8, color=MUTED)
    for i, product in enumerate(data["products"]):
        y = 208 - i * 27
        label(f"0{i + 1}", 40, y, 9, color=MUTED)
        label(product["name"], 68, y, 10, max_width=290)
        label(money(product["revenue"]), WIDTH - 163, y, 9, True, max_width=125)
        rule(y - 10)
    pdf.showPage()

    header(2, "Data quality & methodology", "A transparent record of what went into this report.")
    summary = data["summary"]
    y = 651
    for title, value in [
        ("Source file", data["filename"]),
        ("Generated (UTC)", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")),
        (
            "Requested dates",
            f"{data['filters']['start'] or 'Open start'} to {data['filters']['end'] or 'Open end'}",
        ),
        ("Region filter", data["filters"]["region"] or "All regions"),
        ("Sales rows in this report", f"{metrics['rows']:,}"),
    ]:
        label(title, 40, y, 9, color=MUTED)
        label(value, 214, y, 9, max_width=WIDTH - 254)
        y -= 23
    rule(y + 8)
    label("Cleaning summary · entire source file", 40, y - 20, 13, True)
    y -= 49
    quality = [
        ("Rows read", summary["input_rows"]),
        ("Clean rows retained", summary["clean_rows"]),
        ("Duplicate rows removed", summary["duplicate_rows"]),
        ("Missing required values", summary["missing_required"]),
        ("Invalid dates", summary["invalid_date"]),
        ("Invalid numbers", summary["invalid_number"]),
        ("Malformed rows", summary["malformed_rows"]),
        ("Retained rows with normalized formatting", summary["normalized_rows"]),
    ]
    for i, (title, value) in enumerate(quality):
        if i % 2 == 0:
            pdf.setFillColor(PALE)
            pdf.rect(40, y - 8, WIDTH - 80, 24, fill=1, stroke=0)
        label(title, 50, y, 9)
        label(f"{value:,}", WIDTH - 95, y, 10, True)
        y -= 24
    label("How to read these numbers", 40, y - 24, 13, True)
    notes = [
        "Revenue = quantity × unit price. Taxes, discounts and refunds are not modeled.",
        "Orders = distinct order IDs. Each row without an ID counts as one order.",
        "Average order value = revenue ÷ orders in the filtered selection.",
        "Exact duplicate normalized sales rows are removed; different line items are kept.",
        "Dates: YYYY-MM-DD, YYYY/MM/DD or US MM/DD/YYYY. No locale guessing.",
        f"Currency: {currency}. Missing currency defaults to USD. No exchange conversion.",
        f"Missing order IDs: {summary['missing_order_ids']:,}. Missing optional labels use defaults.",
        "Cleaning totals cover the source file. Metrics and charts respect the selected filters.",
    ]
    for i, note in enumerate(notes):
        label(note, 40, y - 48 - i * 18, 8, color=MUTED, max_width=WIDTH - 80)
    pdf.save()
    return stream.getvalue()
