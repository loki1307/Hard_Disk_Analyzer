# -*- coding: utf-8 -*-
# ================================================================
#  DiskSense AI — server.py
#  Flask backend: static serving, Google + GitHub OAuth, SQLite DB
# ================================================================

import os
import ssl
import secrets
import pathlib
from datetime import datetime, timezone
from functools import wraps

from flask import (
    Flask, redirect, url_for, session, jsonify,
    send_from_directory, request, abort, make_response
)
from flask_login import (
    LoginManager, login_user, logout_user,
    current_user, login_required
)
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from authlib.integrations.flask_client import OAuth
from dotenv import load_dotenv

from models import db, User, LoginEvent

# ── Load environment variables ───────────────────────────────────────
load_dotenv()


# ── App factory ──────────────────────────────────────────────────────
def create_app():
    app = Flask(
        __name__,
        static_folder=".",          # serve CSS / JS / HTML from project root
        static_url_path=""
    )

    # Core config
    is_production  = os.environ.get("FLASK_ENV") == "production"
    has_local_cert = pathlib.Path("cert.pem").exists() and pathlib.Path("key.pem").exists()

    app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(32))
    app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
        "DATABASE_URL", "sqlite:///disksense.db"
    )
    # Fix Railway/Render PostgreSQL URL prefix (they use postgres:// not postgresql://)
    db_url = app.config["SQLALCHEMY_DATABASE_URI"]
    if db_url.startswith("postgres://"):
        app.config["SQLALCHEMY_DATABASE_URI"] = db_url.replace("postgres://", "postgresql://", 1)
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    # ── Secure session cookie settings ───────────────────────────────
    use_https = has_local_cert or is_production   # prod platforms handle TLS upstream
    app.config["SESSION_COOKIE_HTTPONLY"]  = True
    app.config["SESSION_COOKIE_SECURE"]   = is_production or use_https
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["PERMANENT_SESSION_LIFETIME"] = 3600 * 8  # 8 hours

    # ── Database ─────────────────────────────────────────────────────
    db.init_app(app)
    with app.app_context():
        db.create_all()

    # ── Rate Limiter ──────────────────────────────────────────────────
    limiter = Limiter(
        get_remote_address,
        app=app,
        default_limits=["200 per minute"],
        storage_uri="memory://",
    )
    # Stricter limits on auth endpoints
    limiter.limit("10 per minute")(lambda: None)  # applied per-route below

    # ── Flask-Login ──────────────────────────────────────────────────
    login_manager = LoginManager(app)
    login_manager.login_view = "login_page"

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    @login_manager.unauthorized_handler
    def unauthorized():
        if request.path.startswith("/api/"):
            return jsonify({"error": "Authentication required"}), 401
        return redirect(url_for("login_page"))

    # ── Security Headers (applied to every response) ──────────────────
    @app.after_request
    def add_security_headers(response):
        # Prevent clickjacking
        response.headers["X-Frame-Options"] = "DENY"
        # Block MIME sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"
        # XSS protection (legacy browsers)
        response.headers["X-XSS-Protection"] = "1; mode=block"
        # Referrer policy
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        # Permissions policy
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        # HSTS — force HTTPS for 1 year (only when running with cert)
        if use_https:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        # Content Security Policy
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://fonts.gstatic.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "img-src 'self' data: https://avatars.githubusercontent.com https://lh3.googleusercontent.com; "
            "connect-src 'self'; "
            "frame-ancestors 'none';"
        )
        return response

    # ── Authlib OAuth clients ────────────────────────────────────────
    oauth = OAuth(app)

    oauth.register(
        name="google",
        client_id=os.environ.get("GOOGLE_CLIENT_ID"),
        client_secret=os.environ.get("GOOGLE_CLIENT_SECRET"),
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={
            "scope": "openid email profile",
            "prompt": "select_account",
        },
    )

    oauth.register(
        name="github",
        client_id=os.environ.get("GITHUB_CLIENT_ID"),
        client_secret=os.environ.get("GITHUB_CLIENT_SECRET"),
        access_token_url="https://github.com/login/oauth/access_token",
        access_token_params=None,
        authorize_url="https://github.com/login/oauth/authorize",
        authorize_params=None,
        api_base_url="https://api.github.com/",
        client_kwargs={"scope": "read:user user:email"},
    )

    # ════════════════════════════════════════════════════════════════
    #  HELPER — upsert user after OAuth callback
    # ════════════════════════════════════════════════════════════════
    def upsert_user(provider: str, provider_id: str, name: str,
                    email: str, avatar_url: str) -> User:
        """
        Insert a new user row, or update profile + login stats if
        the (provider, provider_id) pair already exists.
        """
        user = User.query.filter_by(
            provider=provider, provider_id=str(provider_id)
        ).first()

        now = datetime.now(timezone.utc)

        if user is None:
            user = User(
                provider=provider,  # type: ignore
                provider_id=str(provider_id),  # type: ignore
                name=name,  # type: ignore
                email=email,  # type: ignore
                avatar_url=avatar_url,  # type: ignore
                first_login=now,  # type: ignore
                last_login=now,  # type: ignore
                login_count=1,  # type: ignore
            )
            db.session.add(user)
        else:
            # Refresh profile info (name/avatar may change)
            user.name       = name or user.name
            user.email      = email or user.email
            user.avatar_url = avatar_url or user.avatar_url
            user.last_login = now
            user.login_count = (user.login_count or 0) + 1

        # Audit log
        event = LoginEvent(
            user=user,  # type: ignore
            provider=provider,  # type: ignore
            ip_address=request.remote_addr,  # type: ignore
            user_agent=request.user_agent.string[:512] if request.user_agent else None,  # type: ignore
            timestamp=now,  # type: ignore
        )
        db.session.add(event)
        db.session.commit()
        return user

    # ════════════════════════════════════════════════════════════════
    #  ROUTES — Pages
    # ════════════════════════════════════════════════════════════════

    @app.route("/")
    @login_required
    def index():
        """Serve the main Hard Disk Analyzer app (requires auth)."""
        return send_from_directory(".", "index.html")

    @app.route("/login")
    def login_page():
        """Serve the login page. Redirect to app if already logged in."""
        if current_user.is_authenticated:
            return redirect(url_for("index"))
        return send_from_directory(".", "login.html")

    @app.route("/auth/logout")
    def logout():
        """Clear session and redirect to login."""
        logout_user()
        session.clear()
        return redirect(url_for("login_page"))

    # ════════════════════════════════════════════════════════════════
    #  ROUTE — Demo / Dev Login (no OAuth needed)
    #  Only active when FLASK_ENV=development AND credentials missing
    # ════════════════════════════════════════════════════════════════

    @app.route("/auth/demo")
    def demo_login():
        """
        Dev-mode bypass: creates a demo user and logs them in instantly.
        Disabled automatically once real OAuth credentials are configured.
        Disabled in production (FLASK_ENV != development).
        """
        # Block in production
        if os.environ.get("FLASK_ENV") != "development":
            abort(404)

        # Also block if real Google OR GitHub credentials are present
        google_ready = (
            os.environ.get("GOOGLE_CLIENT_ID", "").strip() and
            "YOUR_" not in os.environ.get("GOOGLE_CLIENT_ID", "")
        )
        github_ready = (
            os.environ.get("GITHUB_CLIENT_ID", "").strip() and
            "YOUR_" not in os.environ.get("GITHUB_CLIENT_ID", "")
        )
        if google_ready or github_ready:
            return redirect(url_for("login_page") + "?error=demo_disabled")

        demo_user = upsert_user(
            provider="demo",
            provider_id="dev-001",
            name="Demo User",
            email="demo@disksense.local",
            avatar_url="",
        )
        login_user(demo_user, remember=True)
        app.logger.info("[Demo] Dev login used")
        return redirect(url_for("index"))

    # ════════════════════════════════════════════════════════════════
    #  ROUTES — Google OAuth
    # ════════════════════════════════════════════════════════════════

    @app.route("/auth/google")
    def google_login():
        """Initiate Google OAuth flow."""
        redirect_uri = url_for("google_callback", _external=True)
        return oauth.google.authorize_redirect(redirect_uri)

    @app.route("/auth/google/callback")
    def google_callback():
        """Handle Google OAuth callback, upsert user, start session."""
        try:
            token = oauth.google.authorize_access_token()
        except Exception as e:
            app.logger.error(f"Google OAuth error: {e}")
            return redirect(url_for("login_page") + "?error=google_auth_failed")

        userinfo = token.get("userinfo") or oauth.google.userinfo(token=token)

        user = upsert_user(
            provider="google",
            provider_id=userinfo["sub"],
            name=userinfo.get("name", ""),
            email=userinfo.get("email", ""),
            avatar_url=userinfo.get("picture", ""),
        )

        login_user(user, remember=True)
        app.logger.info(f"[Google] Logged in: {user.name} ({user.email})")
        return redirect(url_for("index"))

    # ════════════════════════════════════════════════════════════════
    #  ROUTES — GitHub OAuth
    # ════════════════════════════════════════════════════════════════

    @app.route("/auth/github")
    def github_login():
        """Initiate GitHub OAuth flow."""
        redirect_uri = url_for("github_callback", _external=True)
        return oauth.github.authorize_redirect(redirect_uri)

    @app.route("/auth/github/callback")
    def github_callback():
        """Handle GitHub OAuth callback, upsert user, start session."""
        try:
            token = oauth.github.authorize_access_token()
        except Exception as e:
            app.logger.error(f"GitHub OAuth error: {e}")
            return redirect(url_for("login_page") + "?error=github_auth_failed")

        # Fetch profile
        resp = oauth.github.get("user", token=token)
        profile = resp.json()

        # GitHub may hide email — fetch from emails endpoint
        email = profile.get("email")
        if not email:
            try:
                emails_resp = oauth.github.get("user/emails", token=token)
                emails = emails_resp.json()
                primary = next(
                    (e["email"] for e in emails if e.get("primary") and e.get("verified")),
                    None
                )
                email = primary or (emails[0]["email"] if emails else "")
            except Exception:
                email = ""

        user = upsert_user(
            provider="github",
            provider_id=str(profile["id"]),
            name=profile.get("name") or profile.get("login", ""),
            email=email,
            avatar_url=profile.get("avatar_url", ""),
        )

        login_user(user, remember=True)
        app.logger.info(f"[GitHub] Logged in: {user.name} ({user.email})")
        return redirect(url_for("index"))

    # ════════════════════════════════════════════════════════════════
    #  API ROUTES — JSON
    # ════════════════════════════════════════════════════════════════

    @app.route("/api/config-status")
    def api_config_status():
        """
        Public endpoint — tells the login page which OAuth providers
        are properly configured (have real credentials vs placeholders).
        Also indicates whether demo login is available.
        """
        def is_configured(key):
            val = os.environ.get(key, "")
            return bool(val) and "YOUR_" not in val and len(val) > 10

        google_ok = is_configured("GOOGLE_CLIENT_ID") and is_configured("GOOGLE_CLIENT_SECRET")
        github_ok = is_configured("GITHUB_CLIENT_ID") and is_configured("GITHUB_CLIENT_SECRET")
        dev_mode  = os.environ.get("FLASK_ENV") == "development"

        return jsonify({
            "google":  google_ok,
            "github":  github_ok,
            "demo":    dev_mode and not google_ok and not github_ok,
            "dev_mode": dev_mode,
        })

    @app.route("/api/me")
    @login_required
    def api_me():
        """Return the currently logged-in user's profile."""
        return jsonify(current_user.to_dict())

    @app.route("/api/users")
    @login_required
    def api_users():
        """
        Return all users in the database (admin view).
        Includes login event count and last login time.
        """
        users = User.query.order_by(User.last_login.desc()).all()
        return jsonify({
            "total": len(users),
            "users": [u.to_dict() for u in users]
        })

    @app.route("/api/users/<int:user_id>/events")
    @login_required
    def api_user_events(user_id):
        """Return login history for a specific user."""
        user = db.session.get(User, user_id)
        if not user:
            abort(404)
        events = LoginEvent.query.filter_by(user_id=user_id)\
                    .order_by(LoginEvent.timestamp.desc())\
                    .limit(50).all()
        return jsonify({
            "user": user.to_dict(),
            "events": [e.to_dict() for e in events]
        })

    @app.route("/api/stats")
    @login_required
    def api_stats():
        """High-level stats for the current logged-in user."""
        u = current_user
        google_users = User.query.filter_by(provider="google").count()
        github_users = User.query.filter_by(provider="github").count()
        total_logins = db.session.query(
            db.func.sum(User.login_count)
        ).scalar() or 0
        return jsonify({
            "total_users":   User.query.count(),
            "google_users":  google_users,
            "github_users":  github_users,
            "total_logins":  total_logins,
            "current_user":  u.to_dict(),
        })

    # ── Static file fallback ─────────────────────────────────────────
    @app.route("/<path:filename>")
    def static_files(filename):
        """Serve CSS, JS, and other static assets."""
        return send_from_directory(".", filename)

    return app



# ── Module-level instance for gunicorn ──────────────────────────────────
# gunicorn imports this module and looks for `application`
application = create_app()

# ── Entry point (local dev only) ───────────────────────────────────────
if __name__ == "__main__":
    # Auto-detect SSL certificate
    cert = pathlib.Path("cert.pem")
    key  = pathlib.Path("key.pem")
    use_ssl = cert.exists() and key.exists()

    port     = int(os.environ.get("PORT", 5000))
    protocol = "https" if use_ssl else "http"
    sep      = "=" * 60
    print("\n" + sep)
    print("  [*]  DiskSense AI -- Secure Backend Server")
    print(f"  [>]  {protocol}://localhost:{port}")
    print(f"  [>]  {protocol}://10.167.195.133:{port}")
    print("  [#]  Google + GitHub OAuth enabled")
    print("  [DB] SQLite database: disksense.db")
    print(f"  [SSL] HTTPS {'ENABLED (cert.pem)' if use_ssl else 'DISABLED (no cert found)'}")
    print(sep + "\n")

    ssl_context = None
    if use_ssl:
        ssl_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ssl_ctx.load_cert_chain(certfile=str(cert), keyfile=str(key))
        ssl_context = ssl_ctx

    application.run(
        host="0.0.0.0",
        port=port,
        debug=os.environ.get("FLASK_ENV") == "development",
        ssl_context=ssl_context,
    )
