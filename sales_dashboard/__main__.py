"""Cross-platform local entry point, served by Waitress."""

import os

from waitress import serve

from . import create_app


def main():
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8000"))
    print(f"Sales CSV Dashboard & PDF Report: http://{host}:{port}", flush=True)
    serve(
        create_app(),
        host=host,
        port=port,
        threads=4,
        max_request_body_size=5 * 1024 * 1024,
        inbuf_overflow=6 * 1024 * 1024,
    )


if __name__ == "__main__":
    main()
