"""Sales CSV Dashboard & PDF Report."""

import io
from pathlib import Path

from flask import Flask, Request, jsonify, render_template, request, send_file
from werkzeug.exceptions import RequestEntityTooLarge
from werkzeug.utils import secure_filename

from .analysis import DataError, analyze, clean_csv
from .report import build_report


class MemoryOnlyRequest(Request):
    """Keep bounded file uploads out of Werkzeug's default temporary-file spool."""

    def _get_file_stream(
        self, total_content_length, content_type, filename=None, content_length=None
    ):
        return io.BytesIO()


def create_app(test_config=None):
    app = Flask(__name__)
    app.request_class = MemoryOnlyRequest
    app.config.update(MAX_CONTENT_LENGTH=5 * 1024 * 1024, MAX_FORM_PARTS=20)
    if test_config:
        app.config.update(test_config)

    @app.after_request
    def headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "img-src 'self' data:; connect-src 'self'; object-src 'none'; "
            "base-uri 'self'; frame-ancestors 'none'; form-action 'self'"
        )
        if request.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/sample.csv")
    def sample():
        return send_file(
            Path(app.root_path) / "data" / "sample_sales.csv",
            as_attachment=True,
            download_name="sample_sales.csv",
        )

    def get_analysis():
        upload = request.files.get("file")
        if not upload or not upload.filename:
            raise DataError("Choose a CSV file to get started.")
        if not upload.filename.lower().endswith(".csv"):
            raise DataError("Please upload a .csv file.")
        rows, summary = clean_csv(upload.read())
        result = analyze(rows, summary, request.form)
        result["filename"] = secure_filename(upload.filename)[:120] or "sales.csv"
        return result

    @app.post("/api/analyze")
    def analyze_upload():
        return jsonify(get_analysis())

    @app.post("/api/report")
    def report():
        result = get_analysis()
        if not result["metrics"]["rows"]:
            raise DataError("No sales match these filters. Reset the filters before exporting.")
        return send_file(
            io.BytesIO(build_report(result)),
            mimetype="application/pdf",
            as_attachment=True,
            download_name="sales-report.pdf",
        )

    @app.errorhandler(DataError)
    def invalid_data(error):
        return jsonify(error=str(error)), 400

    @app.errorhandler(RequestEntityTooLarge)
    def too_large(error):
        return jsonify(error="This upload is too large. Keep your CSV below 5 MB."), 413

    return app
