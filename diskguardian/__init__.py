# -*- coding: utf-8 -*-
"""diskguardian/__init__.py — Application factory for AI Disk Guardian Pro."""

import os
import logging
from pathlib import Path
from flask import Flask, render_template
from .extensions import db, login_manager, limiter, mail, csrf, migrate
from .config import get_config, BASE_DIR

# Canonical DB path — always use this, never the old instance/disksense.db
DB_PATH = BASE_DIR / "diskguardian.db"


def _nuke_and_rebuild(app):
    """
    If the SQLite DB file has the old schema (missing columns), delete the file
    entirely and let SQLAlchemy recreate it fresh. This is safer than drop_all
    because it avoids any connection caching or lock issues.
    """
    uri = app.config.get("SQLALCHEMY_DATABASE_URI", "")
    if not uri.startswith("sqlite"):
        return  # Only run for SQLite (dev). PostgreSQL handles migrations differently.

    # Extract the filesystem path from the URI
    db_file = None
    if uri.startswith("sqlite:////"):           # Absolute Unix path
        db_file = Path(uri[10:])
    elif uri.startswith("sqlite:///") and ":\\" in uri:  # Absolute Windows path
        db_file = Path(uri[10:])
    elif uri.startswith("sqlite:///"):          # Relative path — inside instance/
        db_file = Path(app.instance_path) / uri[10:]
    else:
        db_file = DB_PATH

    if db_file and db_file.exists() and db_file.stat().st_size == 0:
        # Empty/corrupt file — just delete it
        db_file.unlink(missing_ok=True)
        return

    if db_file and db_file.exists():
        try:
            import sqlite3
            conn = sqlite3.connect(str(db_file))
            cur  = conn.cursor()
            cur.execute("PRAGMA table_info(users)")
            existing = {row[1] for row in cur.fetchall()}
            conn.close()
            required = {"username", "oauth_provider", "oauth_id", "role",
                        "email_verified", "is_active_acc", "last_scan", "settings"}
            if existing and not required.issubset(existing):
                print(f"[DiskGuardian] ⚠️  Old schema detected in {db_file}. Deleting and rebuilding.")
                db_file.unlink(missing_ok=True)
        except Exception as e:
            print(f"[DiskGuardian] Schema check error: {e}")

    # Also nuke the old instance/disksense.db if it exists
    old_db = BASE_DIR / "instance" / "disksense.db"
    if old_db.exists():
        try:
            old_db.unlink(missing_ok=True)
            print("[DiskGuardian] Removed legacy instance/disksense.db")
        except OSError:
            print("[DiskGuardian] Could not remove legacy instance/disksense.db (file in use)")


def create_app(config_name: str | None = None) -> Flask:
    """Create and configure the Flask application."""
    app = Flask(__name__, template_folder="templates", static_folder="static")

    # Load configuration
    config_name = config_name or os.environ.get("FLASK_ENV", "development")
    app.config.from_object(get_config(config_name))

    # Force the DB to our canonical path — override any env DATABASE_URL for SQLite
    uri = app.config.get("SQLALCHEMY_DATABASE_URI", "")
    if not uri or uri.startswith("sqlite"):
        app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{DB_PATH}"
    elif uri.startswith("postgres://"):
        app.config["SQLALCHEMY_DATABASE_URI"] = uri.replace("postgres://", "postgresql://", 1)

    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    limiter.init_app(app)
    mail.init_app(app)
    csrf.init_app(app)

    with app.app_context():
        if os.environ.get("FLASK_ENV") != "production":
            _nuke_and_rebuild(app)
        db.create_all()

    # Register blueprints
    from .auth import auth_bp
    from .dashboard import dashboard_bp
    from .api import api_bp
    from .admin import admin_bp
    
    from .services.monitor_service import start_monitor
    start_monitor(app)

    app.register_blueprint(auth_bp,      url_prefix="/auth")
    app.register_blueprint(dashboard_bp, url_prefix="/")
    app.register_blueprint(api_bp,       url_prefix="/api")
    app.register_blueprint(admin_bp,     url_prefix="/admin")

    # ── Error handlers ────────────────────────────────────────────────────────
    @app.errorhandler(403)
    def err_403(e):
        return render_template("errors/403.html"), 403

    @app.errorhandler(404)
    def err_404(e):
        return render_template("errors/404.html"), 404

    @app.errorhandler(500)
    def err_500(e):
        logging.exception("Internal Server Error")
        return render_template("errors/500.html"), 500

    @app.errorhandler(429)
    def err_429(e):
        return render_template("errors/429.html"), 429

    # Favicon — suppress 404 log noise
    from flask import send_from_directory
    @app.route("/favicon.ico")
    def favicon():
        static_dir = app.static_folder or ""
        if static_dir and (Path(static_dir) / "favicon.ico").exists():
            return send_from_directory(static_dir, "favicon.ico")
        return "", 204

    # Security headers
    @app.after_request
    def security_headers(response):
        response.headers["X-Frame-Options"]        = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-XSS-Protection"]       = "1; mode=block"
        response.headers["Referrer-Policy"]         = "strict-origin-when-cross-origin"
        return response

    return app
