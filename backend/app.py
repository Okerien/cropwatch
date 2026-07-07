"""CropWatch backend — Flask application factory.

Run locally:   python app.py         (dev server, demo mode if no NASA creds)
Production:     gunicorn app:app
"""
from __future__ import annotations

import logging

from flask import Flask, jsonify
from flask_cors import CORS

from config import config
from cropwatch.errors import CropWatchError
from cropwatch.routes import bp as api_bp

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(name)s  %(message)s",
)
log = logging.getLogger("cropwatch")


def create_app() -> Flask:
    app = Flask(__name__)
    app.config["JSON_SORT_KEYS"] = False

    # CORS: open for the API so the Vercel frontend (and API consumers in
    # Feature 19) can call it. Tightened per-endpoint in later phases.
    CORS(app, resources={r"/*": {"origins": "*"}})

    app.register_blueprint(api_bp)
    _register_error_handlers(app)

    banner = "DEMO (synthetic data)" if config.DEMO_MODE_DEFAULT else "LIVE (NASA AppEEARS)"
    log.info("CropWatch backend starting — mode: %s", banner)
    return app


def _register_error_handlers(app: Flask) -> None:
    @app.errorhandler(CropWatchError)
    def handle_known(err: CropWatchError):
        return jsonify(err.to_dict()), err.status_code

    @app.errorhandler(404)
    def handle_404(_):
        return jsonify({"error": {"code": "not_found",
                                  "message": "No such endpoint."}}), 404

    @app.errorhandler(405)
    def handle_405(_):
        return jsonify({"error": {"code": "method_not_allowed",
                                  "message": "Method not allowed for this endpoint."}}), 405

    @app.errorhandler(Exception)
    def handle_unexpected(err: Exception):
        log.exception("Unhandled error: %s", err)
        return jsonify({"error": {"code": "internal",
                                  "message": "An unexpected error occurred."}}), 500


app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(__import__("os").getenv("PORT", 5000)),
            debug=config.DEBUG)
