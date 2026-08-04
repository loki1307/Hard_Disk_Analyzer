import os
from datetime import datetime, timezone

with open('diskguardian/models.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Replacements for class names
content = content.replace('class ScanResult(db.Model):', 'class ScanHistory(db.Model):')
content = content.replace('__tablename__ = "scan_results"', '__tablename__ = "scan_history"')

content = content.replace('class SystemSnapshot(db.Model):', 'class SystemLogs(db.Model):')
content = content.replace('__tablename__ = "system_snapshots"', '__tablename__ = "system_logs"')

content = content.replace('class Alert(db.Model):', 'class Notifications(db.Model):')
content = content.replace('__tablename__ = "alerts"', '__tablename__ = "notifications"')

content = content.replace('class LoginEvent(db.Model):', 'class Sessions(db.Model):')
content = content.replace('__tablename__ = "login_events"', '__tablename__ = "sessions"')

# Update relationships in User
content = content.replace('scan_results   = db.relationship("ScanResult"', 'scan_history   = db.relationship("ScanHistory"')
content = content.replace('snapshots      = db.relationship("SystemSnapshot"', 'system_logs    = db.relationship("SystemLogs"')
content = content.replace('alerts         = db.relationship("Alert"', 'notifications  = db.relationship("Notifications"')
content = content.replace('login_events   = db.relationship("LoginEvent"', 'sessions       = db.relationship("Sessions"')

missing_models = """
# ─────────────────────────────────────────────────────────────────────────────
#  Reports
# ─────────────────────────────────────────────────────────────────────────────
class Reports(db.Model):  # type: ignore
    __tablename__ = "reports"
    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    title      = db.Column(db.String(128))
    content    = db.Column(db.Text)
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

# ─────────────────────────────────────────────────────────────────────────────
#  Settings
# ─────────────────────────────────────────────────────────────────────────────
class Settings(db.Model):  # type: ignore
    __tablename__ = "settings"
    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, unique=True)
    preferences= db.Column(db.Text, default="{}")
    
# ─────────────────────────────────────────────────────────────────────────────
#  AIChats
# ─────────────────────────────────────────────────────────────────────────────
class AIChats(db.Model):  # type: ignore
    __tablename__ = "ai_chats"
    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    message    = db.Column(db.Text)
    response   = db.Column(db.Text)
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

# ─────────────────────────────────────────────────────────────────────────────
#  Benchmarks
# ─────────────────────────────────────────────────────────────────────────────
class Benchmarks(db.Model):  # type: ignore
    __tablename__ = "benchmarks"
    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    drive_path = db.Column(db.String(16))
    read_speed = db.Column(db.Float)
    write_speed= db.Column(db.Float)
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
"""

content += missing_models

with open('diskguardian/models.py', 'w', encoding='utf-8') as f:
    f.write(content)
print("Updated diskguardian/models.py")
