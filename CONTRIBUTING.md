# Contributing

Thanks for helping improve Sales CSV Dashboard & PDF Report.

1. Create a branch in your checkout.
2. Install Python 3.11+ and `python -m pip install -e ".[dev]"` in a virtual environment.
3. Make a focused change. Keep cleaning and metric definitions in `analysis.py`; the dashboard and PDF must share the same result.
4. Add or update tests when changing validation, calculations or exports.
5. Run `python -m pytest -q` and `python -m ruff check .`.
6. For UI changes, run the optional browser smoke test and inspect the upload, loaded dashboard, empty selection and narrow-screen layouts.
7. Describe the behavior change and validation in your pull request.

Keep the interface, error messages and documentation in English. Avoid runtime CDN dependencies and secrets in source files. Do not commit customer CSVs, generated private reports, virtual environments or test output. Use the fictional sample or small synthetic fixtures for reproductions.

For bug reports, include the Python version, operating system, expected result and a minimal **synthetic** CSV. Do not attach confidential sales data. If a report involves a security problem, avoid publishing a working exploit or private data in a public issue; use the repository owner's private reporting channel if enabled.
