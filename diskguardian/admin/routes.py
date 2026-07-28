# -*- coding: utf-8 -*-
"""diskguardian/admin/routes.py — Admin panel routes."""

from functools import wraps
from flask import render_template, redirect, url_for, flash, jsonify, abort
from flask_login import login_required, current_user
from . import admin_bp
from ..extensions import db
from ..models import User, ScanHistory, Notifications, Sessions, SystemLogs


def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            abort(403)
        return f(*args, **kwargs)
    return wrapper


@admin_bp.route("/")
@login_required
@admin_required
def index():
    users       = User.query.order_by(User.created_at.desc()).all()
    total_scans = ScanHistory.query.count()
    total_alerts = Notifications.query.filter_by(read=False).count()
    recent_events = (Sessions.query
                     .order_by(Sessions.timestamp.desc())
                     .limit(20).all())
    stats = {
        "total_users":   User.query.count(),
        "total_scans":   total_scans,
        "active_alerts": total_alerts,
        "google_users":  User.query.filter_by(oauth_provider="google").count(),
        "github_users":  User.query.filter_by(oauth_provider="github").count(),
        "local_users":   User.query.filter(User.password_hash.isnot(None)).count(),
    }
    return render_template("admin/index.html", users=users, stats=stats,
                           recent_events=recent_events)


@admin_bp.route("/users")
@login_required
@admin_required
def users():
    all_users = User.query.order_by(User.created_at.desc()).all()
    return render_template("admin/users.html", users=all_users)


@admin_bp.route("/users/<int:uid>/toggle", methods=["POST"])
@login_required
@admin_required
def toggle_user(uid: int):
    user = db.session.get(User, uid)
    if not user or user.id == current_user.id:
        flash("Cannot modify this user.", "danger")
    else:
        user.is_active_acc = not user.is_active_acc
        db.session.commit()
        flash(f"User {'enabled' if user.is_active_acc else 'disabled'}.", "success")
    return redirect(url_for("admin.users"))


@admin_bp.route("/api/stats")
@login_required
@admin_required
def admin_stats():
    return jsonify({
        "total_users":   User.query.count(),
        "total_scans":   ScanHistory.query.count(),
        "google_users":  User.query.filter_by(oauth_provider="google").count(),
        "github_users":  User.query.filter_by(oauth_provider="github").count(),
        "local_users":   User.query.filter(User.password_hash.isnot(None)).count(),
        "active_alerts": Notifications.query.filter_by(read=False).count(),
        "users": [u.to_dict() for u in User.query.order_by(User.last_login.desc()).all()],
    })
