# ================================================================
#  DiskSense AI — models.py
#  SQLAlchemy database models
# ================================================================

from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime, timezone

db = SQLAlchemy()


class User(UserMixin, db.Model):  # type: ignore
    """
    Stores every unique user who has authenticated via Google or GitHub OAuth.
    A user is uniquely identified by (provider, provider_id).
    The same person logging in via both Google AND GitHub will create two
    separate rows — intentional, keeps providers separate.
    """
    __tablename__ = "users"

    # Primary key
    id = db.Column(db.Integer, primary_key=True)

    # OAuth provider: 'google' | 'github'
    provider = db.Column(db.String(20), nullable=False)

    # Unique user ID returned by the provider (never changes)
    provider_id = db.Column(db.String(128), nullable=False)

    # Profile info (may update on each login)
    name       = db.Column(db.String(200))
    email      = db.Column(db.String(254))
    avatar_url = db.Column(db.String(512))

    # Timestamps & stats
    first_login  = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    last_login   = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                             onupdate=lambda: datetime.now(timezone.utc))
    login_count  = db.Column(db.Integer, default=1, nullable=False)

    # Ensure one row per provider+account
    __table_args__ = (
        db.UniqueConstraint("provider", "provider_id", name="uq_provider_account"),
    )

    def to_dict(self):
        """Serialise to a JSON-safe dict (used by /api/me and /api/users)."""
        return {
            "id":           self.id,
            "provider":     self.provider,
            "name":         self.name,
            "email":        self.email,
            "avatar_url":   self.avatar_url,
            "first_login":  self.first_login.isoformat() if self.first_login else None,
            "last_login":   self.last_login.isoformat()  if self.last_login  else None,
            "login_count":  self.login_count,
        }

    def __repr__(self):
        return f"<User {self.id} {self.provider}:{self.name}>"


class LoginEvent(db.Model):  # type: ignore
    """
    Audit log — one row per login attempt (for analytics / admin panel).
    """
    __tablename__ = "login_events"

    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    provider   = db.Column(db.String(20), nullable=False)
    ip_address = db.Column(db.String(45))          # IPv4 or IPv6
    user_agent = db.Column(db.String(512))
    timestamp  = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    user = db.relationship("User", backref=db.backref("login_events", lazy=True))

    def to_dict(self):
        return {
            "id":         self.id,
            "user_id":    self.user_id,
            "provider":   self.provider,
            "ip_address": self.ip_address,
            "timestamp":  self.timestamp.isoformat() if self.timestamp else None,
        }

    def __repr__(self):
        return f"<LoginEvent {self.id} user={self.user_id} {self.provider}>"
