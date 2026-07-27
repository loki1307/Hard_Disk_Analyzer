# -*- coding: utf-8 -*-
"""diskguardian/api/routes.py — JSON API endpoints."""

import threading
from datetime import datetime, timezone
from flask import jsonify, request, send_file, abort
from flask_login import login_required, current_user
import io

from . import api_bp
from ..extensions import db, limiter
from ..models import ScanResult, SystemSnapshot, Alert
from ..services import system_service as sys_svc
from ..services import smart_service   as smart_svc
from ..services import ai_service      as ai_svc
from ..services import benchmark_service as bench_svc
from ..services import report_service  as report_svc
from ..services import cleanup_service as cleanup_svc
from ..services import optimization_service as opt_svc
from ..services import partition_service as part_svc


# ─────────────────────────────────────────────────────────────────────────────
#  Live System Metrics  (polled every 1 second by frontend)
# ─────────────────────────────────────────────────────────────────────────────
@api_bp.route("/system")
@login_required
def api_system():
    return jsonify(sys_svc.get_full_snapshot())


@api_bp.route("/cleanup")
@login_required
def api_cleanup():
    return jsonify(cleanup_svc.analyze_cleanup())


@api_bp.route("/optimization")
@login_required
def api_optimization():
    return jsonify(opt_svc.analyze_optimization())


@api_bp.route("/partition")
@login_required
def api_partition():
    drive = request.args.get("drive", "C:")
    return jsonify(part_svc.analyze_partition_safety(drive))


@api_bp.route("/disks")
@login_required
def api_disks():
    return jsonify(sys_svc.get_disk_list())


# ─────────────────────────────────────────────────────────────────────────────
#  SMART Data
# ─────────────────────────────────────────────────────────────────────────────
@api_bp.route("/smart")
@login_required
def api_smart():
    drive = request.args.get("drive", "C:")
    data  = smart_svc.get_smart_data(drive)
    return jsonify(data)


@api_bp.route("/smart/all")
@login_required
def api_smart_all():
    return jsonify(smart_svc.get_all_drives_smart())


# ─────────────────────────────────────────────────────────────────────────────
#  Scan + Health Score
# ─────────────────────────────────────────────────────────────────────────────
@api_bp.route("/scan", methods=["POST"])
@login_required
@limiter.limit("5 per minute")
def api_scan():
    drive  = request.json.get("drive", "C:") if request.json else "C:"
    smart  = smart_svc.get_smart_data(drive)
    system = sys_svc.get_full_snapshot()
    health = ai_svc.calculate_health_score(smart, system)
    risk   = ai_svc.predict_risk(smart)

    # Save scan result
    result = ScanResult(
        user_id      = current_user.id,  # type: ignore
        drive_path   = drive,  # type: ignore
        drive_model  = smart.get("model"),  # type: ignore
        drive_serial = smart.get("serial"),  # type: ignore
        drive_type   = smart.get("drive_type", "HDD"),  # type: ignore
        drive_firmware = smart.get("firmware"),  # type: ignore
        health_score = health["score"],  # type: ignore
        risk_level   = risk["risk_level"],  # type: ignore
        temperature  = smart.get("temperature"),  # type: ignore
        power_on_hours = smart.get("power_on_hours"),  # type: ignore
    )
    result.set_smart(smart)
    result._ai_summary = health.get("grade", "")

    # Save snapshot
    snap = SystemSnapshot(
        user_id     = current_user.id,  # type: ignore
        cpu_percent = system["cpu"]["percent"],  # type: ignore
        ram_percent = system["ram"]["percent"],  # type: ignore
        disk_read_mb  = system["disk_io"]["read_mbps"],  # type: ignore
        disk_write_mb = system["disk_io"]["write_mbps"],  # type: ignore
        temperature   = smart.get("temperature"),  # type: ignore
    )

    # Generate alerts
    alerts = []
    if smart.get("temperature", 0) > 55:
        alerts.append(Alert(user_id=current_user.id, type="temperature",  # type: ignore
                            message=f"Drive temperature critical: {smart['temperature']}°C",  # type: ignore
                            severity="critical"))  # type: ignore
    if smart.get("reallocated_sectors", 0) > 0:
        alerts.append(Alert(user_id=current_user.id, type="smart",  # type: ignore
                            message=f"{smart['reallocated_sectors']} reallocated sector(s) — physical damage detected.",  # type: ignore
                            severity="critical"))  # type: ignore
    if health["score"] < 60:
        alerts.append(Alert(user_id=current_user.id, type="health",  # type: ignore
                            message=f"Drive health critical: {health['score']}/100",  # type: ignore
                            severity="critical"))  # type: ignore

    current_user.last_scan = datetime.now(timezone.utc)
    db.session.add(result)
    db.session.add(snap)
    for a in alerts:
        db.session.add(a)
    db.session.commit()

    checklist = ai_svc.generate_maintenance_checklist(smart, system)
    return jsonify({
        "scan_id":   result.id,
        "smart":     smart,
        "health":    health,
        "risk":      risk,
        "checklist": checklist,
        "alerts":    [a.to_dict() for a in alerts],
    })


# ─────────────────────────────────────────────────────────────────────────────
#  Benchmark
# ─────────────────────────────────────────────────────────────────────────────
@api_bp.route("/benchmark", methods=["POST"])
@login_required
@limiter.limit("2 per minute")
def api_benchmark():
    drive   = (request.json or {}).get("drive", "C:")
    size_mb = min(int((request.json or {}).get("size_mb", 50)), 200)
    result  = bench_svc.run_benchmark(drive, size_mb)

    # Update last scan result with benchmark data
    last = (ScanResult.query
            .filter_by(user_id=current_user.id)
            .order_by(ScanResult.timestamp.desc())
            .first())
    if last:
        last.set_benchmark(result)
        db.session.commit()

    return jsonify(result)


# ─────────────────────────────────────────────────────────────────────────────
#  AI Chat
# ─────────────────────────────────────────────────────────────────────────────
@api_bp.route("/ai/chat", methods=["POST"])
@login_required
@limiter.limit("30 per minute")
def api_ai_chat():
    data     = request.json or {}
    question = data.get("question", "").strip()
    drive    = data.get("drive", "C:")

    if not question:
        return jsonify({"error": "Empty question"}), 400

    smart  = smart_svc.get_smart_data(drive)
    health = ai_svc.calculate_health_score(smart)
    
    # Fetch additional context for advanced queries
    sys_data = sys_svc.get_full_snapshot()
    cln_data = cleanup_svc.analyze_cleanup()
    opt_data = opt_svc.analyze_optimization()
    
    answer = ai_svc.ai_chat(question, smart, health, system=sys_data, cleanup=cln_data, opt=opt_data)
    return jsonify({"answer": answer, "health_score": health["score"]})


# ─────────────────────────────────────────────────────────────────────────────
#  Reports / Export
# ─────────────────────────────────────────────────────────────────────────────
@api_bp.route("/report/<int:scan_id>/<fmt>")
@login_required
def api_report(scan_id: int, fmt: str):
    scan = ScanResult.query.filter_by(id=scan_id, user_id=current_user.id).first_or_404()
    smart  = scan.get_smart()
    health = ai_svc.calculate_health_score(smart)
    risk   = ai_svc.predict_risk(smart)
    bench  = scan.get_benchmark()
    user_dict = current_user.to_dict()
    scan_dict = scan.to_dict()

    if fmt == "pdf":
        try:
            pdf = report_svc.generate_pdf(scan_dict, user_dict, health, risk, bench or None)
            return send_file(io.BytesIO(pdf), mimetype="application/pdf",
                             as_attachment=True, download_name=f"report_{scan_id}.pdf")
        except RuntimeError as e:
            return jsonify({"error": str(e), "hint": "Install reportlab: pip install reportlab"}), 503
    elif fmt == "csv":
        csv_bytes = report_svc.generate_csv(scan_dict, health)
        return send_file(io.BytesIO(csv_bytes), mimetype="text/csv",
                         as_attachment=True, download_name=f"report_{scan_id}.csv")
    elif fmt == "excel":
        try:
            xlsx = report_svc.generate_excel(scan_dict, health)
            return send_file(io.BytesIO(xlsx),
                             mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             as_attachment=True, download_name=f"report_{scan_id}.xlsx")
        except RuntimeError as e:
            return jsonify({"error": str(e), "hint": "Install openpyxl: pip install openpyxl"}), 503
    elif fmt == "json":
        j = report_svc.generate_json(scan_dict, health, risk)
        return send_file(io.BytesIO(j), mimetype="application/json",
                         as_attachment=True, download_name=f"report_{scan_id}.json")
    abort(404)



# ─────────────────────────────────────────────────────────────────────────────
#  Alerts
# ─────────────────────────────────────────────────────────────────────────────
@api_bp.route("/alerts")
@login_required
def api_alerts():
    alerts = (Alert.query
              .filter_by(user_id=current_user.id)
              .order_by(Alert.created_at.desc())
              .limit(20).all())
    return jsonify([a.to_dict() for a in alerts])


@api_bp.route("/alerts/<int:alert_id>/read", methods=["POST"])
@login_required
def api_alert_read(alert_id: int):
    alert = Alert.query.filter_by(id=alert_id, user_id=current_user.id).first_or_404()
    alert.read = True
    db.session.commit()
    return jsonify({"ok": True})


# ─────────────────────────────────────────────────────────────────────────────
#  User / Me
# ─────────────────────────────────────────────────────────────────────────────
@api_bp.route("/me")
@login_required
def api_me():
    return jsonify(current_user.to_dict())


@api_bp.route("/history")
@login_required
def api_history():
    scans = (ScanResult.query
             .filter_by(user_id=current_user.id)
             .order_by(ScanResult.timestamp.desc())
             .limit(30).all())
    return jsonify([s.to_dict() for s in scans])


@api_bp.route("/history/clear", methods=["POST"])
@login_required
def api_history_clear():
    """Delete all scan history and snapshots for the current user."""
    ScanResult.query.filter_by(user_id=current_user.id).delete()
    SystemSnapshot.query.filter_by(user_id=current_user.id).delete()
    db.session.commit()
    return jsonify({"ok": True, "message": "Scan history cleared."})

@api_bp.route("/snapshots")
@login_required
def api_snapshots():
    snaps = (SystemSnapshot.query
             .filter_by(user_id=current_user.id)
             .order_by(SystemSnapshot.timestamp.desc())
             .limit(60).all())
    return jsonify([{
        "t":    s.timestamp.isoformat(),
        "cpu":  s.cpu_percent,
        "ram":  s.ram_percent,
        "disk_read":  s.disk_read_mb,
        "disk_write": s.disk_write_mb,
        "temp": s.temperature,
    } for s in reversed(snaps)])


@api_bp.route("/me/settings", methods=["POST"])
@login_required
def api_save_settings():
    """Save user preferences to the database."""
    data = request.json or {}
    allowed = {"theme", "auto_refresh", "refresh_interval",
               "notifications_enabled", "email_alerts",
               "auto_scan", "scan_interval_hours", "language"}
    s = current_user.settings
    for key in allowed:
        if key in data:
            s[key] = data[key]
    current_user.settings = s
    db.session.commit()
    return jsonify({"ok": True, "settings": current_user.settings})


@api_bp.route("/me/settings", methods=["GET"])
@login_required
def api_get_settings():
    """Return user settings."""
    return jsonify(current_user.settings)


@api_bp.route("/alerts/<int:alert_id>/dismiss", methods=["POST"])
@login_required
def api_alert_dismiss(alert_id: int):
    """Dismiss (mark read) an alert."""
    alert = Alert.query.filter_by(id=alert_id, user_id=current_user.id).first_or_404()
    alert.read = True
    db.session.commit()
    return jsonify({"ok": True})


@api_bp.route("/alerts/dismiss-all", methods=["POST"])
@login_required
def api_alerts_dismiss_all():
    """Mark all user alerts as read."""
    Alert.query.filter_by(user_id=current_user.id, read=False).update({"read": True})
    db.session.commit()
    return jsonify({"ok": True})


@api_bp.route("/system/info")
@login_required
def api_system_info():
    """Extended system info including OS, hostname, boot time."""
    import platform
    import datetime
    try:
        import psutil
        boot = datetime.datetime.fromtimestamp(psutil.boot_time())
        uptime_s = (datetime.datetime.now() - boot).seconds
        uptime_h = uptime_s // 3600
        uptime_m = (uptime_s % 3600) // 60
        uptime = f"{uptime_h}h {uptime_m}m"
    except Exception:
        uptime = "N/A"

    return jsonify({
        "os":       platform.system() + " " + platform.release(),
        "hostname": platform.node(),
        "python":   platform.python_version(),
        "uptime":   uptime,
        "machine":  platform.machine(),
        "processor": platform.processor() or "Unknown",
    })

