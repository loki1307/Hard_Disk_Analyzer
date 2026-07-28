# -*- coding: utf-8 -*-
"""diskguardian/services/monitor_service.py — Background automated drive monitoring."""

import threading
import time
import logging
from datetime import datetime, timezone
from ..extensions import db
from ..models import User, ScanResult, SystemSnapshot, Alert
from . import smart_service as smart_svc
from . import system_service as sys_svc
from . import ai_service as ai_svc

log = logging.getLogger(__name__)

# Control flag to gracefully stop the thread
_STOP_EVENT = threading.Event()
_MONITOR_THREAD = None

def _monitor_loop(app):
    """
    Background loop that wakes up periodically (e.g., every 30 minutes),
    checks SMART data for users who have auto-scan enabled,
    and logs the data / creates alerts if conditions degrade.
    """
    INTERVAL_SECONDS = 30 * 60  # 30 minutes
    
    with app.app_context():
        log.info("DiskSense Background Monitor started.")
        while not _STOP_EVENT.is_set():
            try:
                # We do a basic pass for all admin users or all users who opted in.
                # Since this is a local app, often there's only 1 primary user.
                users = User.query.filter_by(is_active_acc=True).all()
                for user in users:
                    # Skip if user disabled auto scan (assuming settings are populated)
                    if user.settings.get("auto_scan", True) is False:
                        continue
                    
                    system_data = sys_svc.get_full_snapshot()
                    drives = sys_svc.get_disk_list()
                    
                    for d in drives:
                        drive_path = d.get("device", "C:")
                        smart = smart_svc.get_smart_data(drive_path)
                        health = ai_svc.calculate_health_score(smart, system_data)
                        risk = ai_svc.predict_risk(smart)
                        
                        # Generate Alerts
                        alerts_to_add = []
                        temp = smart.get("temperature", 0)
                        
                        # High Temp Alert
                        if temp > 55:
                            msg = f"Automatic Monitor: {drive_path} temperature critical ({temp}°C)"
                            # Only alert if we haven't alerted for this in the last hour
                            recent = Alert.query.filter_by(user_id=user.id, type="temperature", read=False).first()
                            if not recent:
                                alerts_to_add.append(Alert(user_id=user.id, type="temperature", message=msg, severity="critical"))  # type: ignore
                        
                        # Health Degradation Alert
                        if health["score"] < 60:
                            recent = Alert.query.filter_by(user_id=user.id, type="health", read=False).first()
                            if not recent:
                                msg = f"Automatic Monitor: {drive_path} health is poor ({health['score']}/100)"
                                alerts_to_add.append(Alert(user_id=user.id, type="health", message=msg, severity="critical"))  # type: ignore
                                
                        if alerts_to_add:
                            for a in alerts_to_add:
                                db.session.add(a)
                            db.session.commit()
                            
            except Exception as e:
                log.error(f"Error in monitor loop: {e}")
                
            # Sleep in chunks to allow quick termination
            for _ in range(INTERVAL_SECONDS):
                if _STOP_EVENT.is_set():
                    break
                time.sleep(1)

def start_monitor(app):
    """Start the background monitor thread."""
    global _MONITOR_THREAD
    if _MONITOR_THREAD is None or not _MONITOR_THREAD.is_alive():
        _STOP_EVENT.clear()
        _MONITOR_THREAD = threading.Thread(target=_monitor_loop, args=(app,), daemon=True)
        _MONITOR_THREAD.start()

def stop_monitor():
    """Stop the background monitor thread."""
    _STOP_EVENT.set()
    if _MONITOR_THREAD:
        _MONITOR_THREAD.join(timeout=2)
