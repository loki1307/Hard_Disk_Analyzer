# -*- coding: utf-8 -*-
"""diskguardian/models.py — All SQLAlchemy database models."""

import json
from datetime import datetime, timezone
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from .extensions import db, login_manager


# ─────────────────────────────────────────────────────────────────────────────
#  User
# ─────────────────────────────────────────────────────────────────────────────
class User(UserMixin, db.Model):  # type: ignore
    __tablename__ = "users"

    id             = db.Column(db.Integer,  primary_key=True)
    username       = db.Column(db.String(64),  unique=True,  nullable=True)
    email          = db.Column(db.String(120), unique=True,  nullable=False)
    password_hash  = db.Column(db.String(256), nullable=True)   # None for OAuth-only users

    # OAuth
    oauth_provider = db.Column(db.String(20),  nullable=True)  # 'google'|'github'|'demo'
    oauth_id       = db.Column(db.String(128), nullable=True)
    avatar_url     = db.Column(db.String(512), nullable=True)

    # Profile
    role           = db.Column(db.String(16),  default="user")  # 'user'|'admin'|'technician'
    email_verified = db.Column(db.Boolean,     default=False)
    is_active_acc  = db.Column(db.Boolean,     default=True)

    # Timestamps
    created_at     = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    last_login     = db.Column(db.DateTime(timezone=True), nullable=True)
    last_scan      = db.Column(db.DateTime(timezone=True), nullable=True)

    # Settings (JSON string)
    _settings      = db.Column("settings", db.Text, default="{}")

    # Relationships
    scan_results   = db.relationship("ScanResult",     backref="user", lazy="dynamic", cascade="all, delete-orphan")
    snapshots      = db.relationship("SystemSnapshot", backref="user", lazy="dynamic", cascade="all, delete-orphan")
    alerts         = db.relationship("Alert",          backref="user", lazy="dynamic", cascade="all, delete-orphan")
    backup_records = db.relationship("BackupRecord",   backref="user", uselist=False,  cascade="all, delete-orphan")
    login_events   = db.relationship("LoginEvent",     backref="user", lazy="dynamic", cascade="all, delete-orphan")

    # ── Password helpers ──────────────────────────────────────────────────────
    def set_password(self, password: str):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        if not self.password_hash:
            return False
        return check_password_hash(self.password_hash, password)

    # ── Settings helpers ──────────────────────────────────────────────────────
    @property
    def settings(self) -> dict:
        try:
            return json.loads(self._settings or "{}")
        except (ValueError, TypeError):
            return {}

    @settings.setter
    def settings(self, value: dict):
        self._settings = json.dumps(value)

    def get_setting(self, key: str, default=None):
        return self.settings.get(key, default)

    def set_setting(self, key: str, value):
        s = self.settings
        s[key] = value
        self.settings = s

    # ── Auth helpers ──────────────────────────────────────────────────────────
    @property
    def is_admin(self) -> bool:
        return self.role in ("admin", "technician")

    @property
    def display_name(self) -> str:
        return self.username or self.email.split("@")[0]

    def to_dict(self) -> dict:
        return {
            "id":           self.id,
            "username":     self.display_name,
            "email":        self.email,
            "avatar_url":   self.avatar_url or "",
            "role":         self.role,
            "provider":     self.oauth_provider or "local",
            "created_at":   self.created_at.isoformat() if self.created_at else None,
            "last_login":   self.last_login.isoformat()  if self.last_login  else None,
            "last_scan":    self.last_scan.isoformat()   if self.last_scan   else None,
        }


@login_manager.user_loader
def load_user(user_id: str):
    return db.session.get(User, int(user_id))


# ─────────────────────────────────────────────────────────────────────────────
#  Scan Result
# ─────────────────────────────────────────────────────────────────────────────
class ScanResult(db.Model):  # type: ignore
    __tablename__ = "scan_results"

    id              = db.Column(db.Integer, primary_key=True)
    user_id         = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    timestamp       = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Drive info
    drive_path      = db.Column(db.String(16),  nullable=False)   # e.g. "C:"
    drive_model     = db.Column(db.String(128), nullable=True)
    drive_serial    = db.Column(db.String(64),  nullable=True)
    drive_type      = db.Column(db.String(8),   default="HDD")    # HDD|SSD|NVMe
    drive_firmware  = db.Column(db.String(32),  nullable=True)
    capacity_bytes  = db.Column(db.BigInteger,  nullable=True)

    # Health scores
    health_score    = db.Column(db.Float,  default=100.0)
    risk_level      = db.Column(db.String(8), default="low")      # low|medium|high|critical
    temperature     = db.Column(db.Integer, nullable=True)         # Celsius
    power_on_hours  = db.Column(db.Integer, nullable=True)

    # SMART + benchmark data (stored as JSON)
    _smart_data     = db.Column("smart_data",     db.Text, default="{}")
    _benchmark_data = db.Column("benchmark_data", db.Text, default="{}")
    _ai_summary     = db.Column("ai_summary",     db.Text, default="")

    def get_smart(self) -> dict:
        try: return json.loads(self._smart_data or "{}")
        except: return {}

    def set_smart(self, d: dict): self._smart_data = json.dumps(d)

    def get_benchmark(self) -> dict:
        try: return json.loads(self._benchmark_data or "{}")
        except: return {}

    def set_benchmark(self, d: dict): self._benchmark_data = json.dumps(d)

    def to_dict(self) -> dict:
        return {
            "id":           self.id,
            "timestamp":    self.timestamp.isoformat() if self.timestamp else None,
            "drive":        self.drive_path,
            "model":        self.drive_model,
            "type":         self.drive_type,
            "health_score": self.health_score,
            "risk_level":   self.risk_level,
            "temperature":  self.temperature,
            "power_hours":  self.power_on_hours,
            "smart":        self.get_smart(),
            "benchmark":    self.get_benchmark(),
            "ai_summary":   self._ai_summary or "",
        }


# ─────────────────────────────────────────────────────────────────────────────
#  System Snapshot (1 per minute for historical charts)
# ─────────────────────────────────────────────────────────────────────────────
class SystemSnapshot(db.Model):  # type: ignore
    __tablename__ = "system_snapshots"

    id             = db.Column(db.Integer, primary_key=True)
    user_id        = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    timestamp      = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)

    cpu_percent    = db.Column(db.Float, default=0.0)
    ram_percent    = db.Column(db.Float, default=0.0)
    disk_read_mb   = db.Column(db.Float, default=0.0)   # MB/s
    disk_write_mb  = db.Column(db.Float, default=0.0)
    net_sent_mb    = db.Column(db.Float, default=0.0)
    net_recv_mb    = db.Column(db.Float, default=0.0)
    gpu_percent    = db.Column(db.Float, nullable=True)
    temperature    = db.Column(db.Float, nullable=True)  # overall system


# ─────────────────────────────────────────────────────────────────────────────
#  Alert
# ─────────────────────────────────────────────────────────────────────────────
class Alert(db.Model):  # type: ignore
    __tablename__ = "alerts"

    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    type       = db.Column(db.String(32),  nullable=False)  # 'temperature'|'health'|'storage'|'smart'
    message    = db.Column(db.String(512), nullable=False)
    severity   = db.Column(db.String(8),   default="info")  # info|warning|critical
    read       = db.Column(db.Boolean,     default=False)
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "id":         self.id,
            "type":       self.type,
            "message":    self.message,
            "severity":   self.severity,
            "read":       self.read,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# ─────────────────────────────────────────────────────────────────────────────
#  Backup Record
# ─────────────────────────────────────────────────────────────────────────────
class BackupRecord(db.Model):  # type: ignore
    __tablename__ = "backup_records"

    id                  = db.Column(db.Integer, primary_key=True)
    user_id             = db.Column(db.Integer, db.ForeignKey("users.id"), unique=True, nullable=False)
    last_backup         = db.Column(db.DateTime(timezone=True), nullable=True)
    reminder_days       = db.Column(db.Integer, default=7)
    backup_location     = db.Column(db.String(256), nullable=True)


# ─────────────────────────────────────────────────────────────────────────────
#  Login Event (audit log)
# ─────────────────────────────────────────────────────────────────────────────
class LoginEvent(db.Model):  # type: ignore
    __tablename__ = "login_events"

    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    provider   = db.Column(db.String(20), default="local")
    ip_address = db.Column(db.String(45), nullable=True)
    user_agent = db.Column(db.String(256), nullable=True)
    timestamp  = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


# ─────────────────────────────────────────────────────────────────────────────
#  Password Reset Token
# ─────────────────────────────────────────────────────────────────────────────
class PasswordResetToken(db.Model):  # type: ignore
    __tablename__ = "password_reset_tokens"

    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    token      = db.Column(db.String(128), unique=True, nullable=False)
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False)
    used       = db.Column(db.Boolean, default=False)
