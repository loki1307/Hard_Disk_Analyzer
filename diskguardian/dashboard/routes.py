# -*- coding: utf-8 -*-
"""diskguardian/dashboard/routes.py — Page routes for the main UI."""

from flask import render_template, redirect, url_for
from flask_login import login_required, current_user

from . import dashboard_bp
from ..models import ScanResult, Alert


@dashboard_bp.route("/")
@login_required
def index():
    """Main dashboard page."""
    recent_scans = (ScanResult.query
                    .filter_by(user_id=current_user.id)
                    .order_by(ScanResult.timestamp.desc())
                    .limit(5).all())
    unread_alerts = (Alert.query
                     .filter_by(user_id=current_user.id, read=False)
                     .order_by(Alert.created_at.desc())
                     .limit(10).all())
    return render_template("dashboard/index.html",
                           recent_scans=recent_scans,
                           unread_alerts=unread_alerts)


@dashboard_bp.route("/smart")
@login_required
def smart():
    """SMART data and drive health page."""
    return render_template("dashboard/smart.html")


@dashboard_bp.route("/benchmark")
@login_required
def benchmark():
    """Disk speed benchmark page."""
    return render_template("dashboard/benchmark.html")


@dashboard_bp.route("/cleanup")
@login_required
def cleanup():
    """Disk Cleanup Advisor page."""
    return render_template("dashboard/cleanup.html")


@dashboard_bp.route("/optimization")
@login_required
def optimization():
    """System Optimization Center page."""
    return render_template("dashboard/optimization.html")


@dashboard_bp.route("/partition")
@login_required
def partition():
    """Partition Safety Analyzer page."""
    return render_template("dashboard/partition.html")


@dashboard_bp.route("/history")
@login_required
def history():
    """Historical analytics page."""
    scans = (ScanResult.query
             .filter_by(user_id=current_user.id)
             .order_by(ScanResult.timestamp.desc())
             .limit(50).all())
    scans_json = [s.to_dict() for s in scans]
    return render_template("dashboard/history.html", scans=scans, scans_json=scans_json)



@dashboard_bp.route("/ai")
@login_required
def ai_chat():
    """AI assistant chat page."""
    return render_template("dashboard/ai_chat.html")


@dashboard_bp.route("/settings")
@login_required
def settings():
    """User settings page."""
    return render_template("dashboard/settings.html")


@dashboard_bp.route("/technician")
@login_required
def technician():
    """Technician / expert mode page."""
    return render_template("dashboard/technician.html")
