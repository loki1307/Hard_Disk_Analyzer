# -*- coding: utf-8 -*-
"""diskguardian/auth/routes.py — Authentication routes."""

import secrets
from datetime import datetime, timezone, timedelta
from flask import render_template, redirect, url_for, flash, request, session, current_app
from flask_login import login_user, logout_user, login_required, current_user
from authlib.integrations.flask_client import OAuth

from . import auth_bp
from ..extensions import db, limiter
from ..models import User, Sessions, PasswordResetToken

oauth = OAuth()
_oauth_configured = False


def _get_oauth():
    global oauth, _oauth_configured
    if not _oauth_configured:
        oauth.init_app(current_app)
        cfg = current_app.config
        if cfg.get("GOOGLE_CLIENT_ID"):
            oauth.register(
                name="google",
                client_id=cfg["GOOGLE_CLIENT_ID"],
                client_secret=cfg["GOOGLE_CLIENT_SECRET"],
                server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
                client_kwargs={"scope": "openid email profile", "prompt": "select_account"},
            )
        if cfg.get("GITHUB_CLIENT_ID"):
            oauth.register(
                name="github",
                client_id=cfg["GITHUB_CLIENT_ID"],
                client_secret=cfg["GITHUB_CLIENT_SECRET"],
                access_token_url="https://github.com/login/oauth/access_token",
                authorize_url="https://github.com/login/oauth/authorize",
                api_base_url="https://api.github.com/",
                client_kwargs={"scope": "read:user user:email"},
            )
        _oauth_configured = True
    return oauth


def _record_login(user: User, provider: str = "local"):
    user.last_login = datetime.now(timezone.utc)
    event = Sessions(
        user_id=user.id,  # type: ignore
        provider=provider,  # type: ignore
        ip_address=request.remote_addr,  # type: ignore
        user_agent=request.headers.get("User-Agent", "")[:256],  # type: ignore
    )
    db.session.add(event)
    db.session.commit()


def _upsert_oauth_user(provider: str, provider_id: str, name: str,
                        email: str, avatar_url: str) -> User:
    user = User.query.filter_by(oauth_provider=provider, oauth_id=str(provider_id)).first()
    if not user:
        # Check if email already registered locally
        user = User.query.filter_by(email=email).first()
        if user:
            user.oauth_provider = provider
            user.oauth_id       = str(provider_id)
            user.avatar_url     = avatar_url or user.avatar_url
        else:
            user = User(
                email=email,  # type: ignore
                username=name.replace(" ", "_").lower()[:64] if name else None,  # type: ignore
                oauth_provider=provider,  # type: ignore
                oauth_id=str(provider_id),  # type: ignore
                avatar_url=avatar_url,  # type: ignore
                email_verified=True,  # type: ignore
            )
            db.session.add(user)
    else:
        user.avatar_url = avatar_url or user.avatar_url
    db.session.commit()
    return user


# ─────────────────────────────────────────────────────────────────────────────
#  Local Auth
# ─────────────────────────────────────────────────────────────────────────────
@auth_bp.route("/login", methods=["GET", "POST"])
@limiter.limit("20 per minute")
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))
    error = None
    if request.method == "POST":
        email    = request.form.get("email",    "").strip().lower()
        password = request.form.get("password", "")
        remember = bool(request.form.get("remember"))
        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password):
            if not user.is_active_acc:
                error = "Your account has been disabled. Contact an administrator."
            else:
                login_user(user, remember=remember)
                _record_login(user, "local")
                return redirect(request.args.get("next") or url_for("dashboard.index"))
        else:
            error = "Invalid email or password."
    return render_template("auth/login.html", error=error,
                           google_enabled=bool(current_app.config.get("GOOGLE_CLIENT_ID") and
                                               "YOUR_" not in (current_app.config.get("GOOGLE_CLIENT_ID") or "")),
                           github_enabled=bool(current_app.config.get("GITHUB_CLIENT_ID") and
                                               "YOUR_" not in (current_app.config.get("GITHUB_CLIENT_ID") or "")))


@auth_bp.route("/register", methods=["GET", "POST"])
@limiter.limit("10 per minute")
def register():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))
    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email    = request.form.get("email",    "").strip().lower()
        password = request.form.get("password", "")
        confirm  = request.form.get("confirm",  "")

        if not username or not email or not password:
            error = "All fields are required."
        elif password != confirm:
            error = "Passwords do not match."
        elif len(password) < 8:
            error = "Password must be at least 8 characters."
        elif User.query.filter_by(email=email).first():
            error = "Email already registered."
        elif User.query.filter_by(username=username).first():
            error = "Username already taken."
        else:
            user = User(username=username, email=email, email_verified=True)  # type: ignore
            user.set_password(password)
            # First user is admin
            if User.query.count() == 0:
                user.role = "admin"
            db.session.add(user)
            db.session.commit()
            login_user(user)
            _record_login(user, "local")
            flash("Welcome to Hard Disk Analyzer!", "success")
            return redirect(url_for("dashboard.index"))
    return render_template("auth/register.html", error=error)


@auth_bp.route("/logout", methods=["GET", "POST"])
@login_required
def logout():
    from flask import make_response
    logout_user()
    session.clear()
    flash("You've been signed out.", "info")
    response = make_response(redirect(url_for("auth.login")))
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response



@auth_bp.route("/forgot-password", methods=["GET", "POST"])
@limiter.limit("5 per minute")
def forgot_password():
    message = None
    token_url = None
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        user  = User.query.filter_by(email=email).first()
        if user:
            token = secrets.token_urlsafe(48)
            expires = datetime.now(timezone.utc) + timedelta(hours=1)
            prt = PasswordResetToken(user_id=user.id, token=token, expires_at=expires)  # type: ignore
            db.session.add(prt)
            db.session.commit()
            token_url = url_for("auth.reset_password", token=token, _external=True)
        message = "If that email is registered, a reset link has been generated below."
    return render_template("auth/forgot_password.html", message=message, token_url=token_url)


@auth_bp.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token: str):
    prt = PasswordResetToken.query.filter_by(token=token, used=False).first()
    if not prt or prt.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        flash("Reset link is invalid or expired.", "danger")
        return redirect(url_for("auth.login"))
    error = None
    if request.method == "POST":
        pw  = request.form.get("password", "")
        pw2 = request.form.get("confirm",  "")
        if pw != pw2:
            error = "Passwords do not match."
        elif len(pw) < 8:
            error = "Password must be at least 8 characters."
        else:
            user = db.session.get(User, prt.user_id)
            if user:
                user.set_password(pw)
                prt.used = True
                db.session.commit()
                flash("Password updated! Please sign in.", "success")
            else:
                flash("User not found.", "danger")
            return redirect(url_for("auth.login"))
    return render_template("auth/reset_password.html", token=token, error=error)


# ─────────────────────────────────────────────────────────────────────────────
#  Google OAuth
# ─────────────────────────────────────────────────────────────────────────────
@auth_bp.route("/google")
@limiter.limit("10 per minute")
def google_login():
    o = _get_oauth()
    if not hasattr(o, "google") or not getattr(o, "google"):
        flash("Google Login is not configured.", "warning")
        return redirect(url_for("auth.login"))
    ru = url_for("auth.google_callback", _external=True)
    return o.google.authorize_redirect(ru)


@auth_bp.route("/google/callback")
def google_callback():
    try:
        o     = _get_oauth()
        token = o.google.authorize_access_token()
        info  = token.get("userinfo") or o.google.userinfo(token=token)
        user  = _upsert_oauth_user("google", info["sub"],
                                    info.get("name", ""), info.get("email", ""),
                                    info.get("picture", ""))
        login_user(user, remember=True)
        _record_login(user, "google")
        return redirect(url_for("dashboard.index"))
    except Exception as e:
        flash(f"Google sign-in failed: {e}", "danger")
        return redirect(url_for("auth.login"))


# ─────────────────────────────────────────────────────────────────────────────
#  GitHub OAuth
# ─────────────────────────────────────────────────────────────────────────────
@auth_bp.route("/github")
@limiter.limit("10 per minute")
def github_login():
    o  = _get_oauth()
    if not hasattr(o, "github") or not getattr(o, "github"):
        flash("GitHub Login is not configured.", "warning")
        return redirect(url_for("auth.login"))
    ru = url_for("auth.github_callback", _external=True)
    return o.github.authorize_redirect(ru)


@auth_bp.route("/github/callback")
def github_callback():
    try:
        o       = _get_oauth()
        o.github.authorize_access_token()
        profile = o.github.get("user").json()
        emails  = o.github.get("user/emails").json()
        email   = next((e["email"] for e in emails if e["primary"]), profile.get("email", ""))
        user    = _upsert_oauth_user("github", str(profile["id"]),
                                      profile.get("name") or profile.get("login", ""),
                                      email, profile.get("avatar_url", ""))
        if not user.is_active_acc:
            flash("Your account has been disabled.", "danger")
            return redirect(url_for("auth.login"))
        login_user(user, remember=True)
        _record_login(user, "github")
        return redirect(url_for("dashboard.index"))
    except Exception as e:
        flash(f"GitHub sign-in failed: {e}", "danger")
        return redirect(url_for("auth.login"))


# ─────────────────────────────────────────────────────────────────────────────
#  Change Password (for local accounts, from Settings page)
# ─────────────────────────────────────────────────────────────────────────────
@auth_bp.route("/change-password", methods=["POST"])
@login_required
def change_password():
    if current_user.oauth_provider:
        flash("OAuth accounts cannot change passwords here.", "warning")
        return redirect(url_for("dashboard.settings"))

    current = request.form.get("current", "")
    new_pw  = request.form.get("password", "")
    confirm = request.form.get("confirm", "")

    if not current_user.check_password(current):
        flash("Current password is incorrect.", "danger")
    elif new_pw != confirm:
        flash("New passwords do not match.", "danger")
    elif len(new_pw) < 8:
        flash("Password must be at least 8 characters.", "danger")
    else:
        current_user.set_password(new_pw)
        db.session.commit()
        flash("Password updated successfully!", "success")

    return redirect(url_for("dashboard.settings"))

