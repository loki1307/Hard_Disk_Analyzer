import os

with open('diskguardian/__init__.py', 'r', encoding='utf-8') as f:
    content = f.read()

# We need to add Migrate to extensions
# First check if migrate is already in extensions.py
with open('diskguardian/extensions.py', 'r', encoding='utf-8') as f:
    ext_content = f.read()
if 'Migrate(' not in ext_content:
    with open('diskguardian/extensions.py', 'w', encoding='utf-8') as f:
        f.write(ext_content.replace('from flask_sqlalchemy import SQLAlchemy', 'from flask_sqlalchemy import SQLAlchemy\nfrom flask_migrate import Migrate'))
        f.write('\n\nmigrate = Migrate()\n')

# Now rewrite diskguardian/__init__.py
new_init = """# -*- coding: utf-8 -*-
\"\"\"diskguardian/__init__.py — Application factory for AI Disk Guardian Pro.\"\"\"

import os
import logging
import traceback
from pathlib import Path
from flask import Flask, render_template, request, session
from sqlalchemy.exc import SQLAlchemyError, OperationalError
from sqlalchemy import inspect
from werkzeug.security import generate_password_hash

from .extensions import db, login_manager, limiter, mail, csrf, migrate
from .config import get_config, BASE_DIR

DB_PATH = BASE_DIR / "diskguardian.db"

def init_db(app):
    \"\"\"Robust database initialization\"\"\"
    from .models import User
    
    with app.app_context():
        try:
            # Check connection by trying to inspect the database
            inspector = inspect(db.engine)
            existing_tables = inspector.get_table_names()
            
            # Create all missing tables without crashing
            db.create_all()
            
            # Create admin account if missing
            admin_email = app.config.get("ADMIN_EMAIL", "admin@harddiskanalyzer.local")
            admin = User.query.filter_by(email=admin_email).first()
            if not admin:
                admin = User(
                    username="Admin",
                    email=admin_email,
                    role="admin",
                    email_verified=True
                )
                admin.set_password("admin_password") # Needs to be changed by the admin
                db.session.add(admin)
                db.session.commit()
                app.logger.info(f"Created default admin account: {admin_email}")
                
        except OperationalError as e:
            app.logger.error(f"OperationalError during DB init: {e}")
            db.session.rollback()
        except SQLAlchemyError as e:
            app.logger.error(f"SQLAlchemyError during DB init: {e}")
            db.session.rollback()
        except Exception as e:
            app.logger.error(f"Unexpected error during DB init: {e}")
            db.session.rollback()


def create_app(config_name: str | None = None) -> Flask:
    app = Flask(__name__, template_folder="templates", static_folder="static")

    # Load configuration
    config_name = config_name or os.environ.get("FLASK_ENV", "development")
    app.config.from_object(get_config(config_name))

    uri = app.config.get("SQLALCHEMY_DATABASE_URI", "")
    if not uri or (uri.startswith("sqlite") and not os.environ.get("DATABASE_URL")):
        app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{DB_PATH}"

    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    limiter.init_app(app)
    mail.init_app(app)
    csrf.init_app(app)

    # Initialize DB safely
    init_db(app)

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

    # ── Global Error handlers ────────────────────────────────────────────────
    @app.errorhandler(403)
    def err_403(e):
        return render_template("errors/403.html"), 403

    @app.errorhandler(404)
    def err_404(e):
        return render_template("errors/404.html"), 404

    @app.errorhandler(500)
    def err_500(e):
        app.logger.error(f"500 Internal Server Error: {e}\\n{traceback.format_exc()}")
        return render_template("errors/500.html"), 500

    @app.errorhandler(SQLAlchemyError)
    def handle_db_error(e):
        app.logger.error(f"Database Error: {e}\\n{traceback.format_exc()}")
        return render_template("errors/500.html"), 500

    @app.errorhandler(Exception)
    def handle_exception(e):
        app.logger.error(f"Unhandled Exception: {e}\\n{traceback.format_exc()}")
        return render_template("errors/500.html"), 500

    @app.errorhandler(429)
    def err_429(e):
        return render_template("errors/429.html"), 429

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
        
        # Enforce HTTPS in production
        if os.environ.get("FLASK_ENV") == "production":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
            
        return response

    return app
"""

with open('diskguardian/__init__.py', 'w', encoding='utf-8') as f:
    f.write(new_init)

print("Updated diskguardian/__init__.py and diskguardian/extensions.py")
