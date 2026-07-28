# -*- coding: utf-8 -*-
"""diskguardian/config.py — Configuration classes for AI Disk Guardian Pro."""

import os
import secrets
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


class BaseConfig:
    SECRET_KEY                   = os.environ.get("SECRET_KEY", secrets.token_hex(32))
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SESSION_COOKIE_HTTPONLY      = True
    SESSION_COOKIE_SAMESITE      = "Lax"
    PERMANENT_SESSION_LIFETIME   = 3600 * 8

    # Flask-Mail
    MAIL_SERVER   = os.environ.get("MAIL_SERVER",   "smtp.gmail.com")
    MAIL_PORT     = int(os.environ.get("MAIL_PORT", 587))
    MAIL_USE_TLS  = True
    MAIL_USERNAME = os.environ.get("MAIL_USERNAME", "")
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD", "")
    MAIL_DEFAULT_SENDER = os.environ.get("MAIL_DEFAULT_SENDER", "noreply@diskguardian.local")

    # OAuth
    GOOGLE_CLIENT_ID     = os.environ.get("GOOGLE_CLIENT_ID", "")
    GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
    GITHUB_CLIENT_ID     = os.environ.get("GITHUB_CLIENT_ID", "")
    GITHUB_CLIENT_SECRET = os.environ.get("GITHUB_CLIENT_SECRET", "")

    # App
    APP_NAME    = "Hard Disk Analyzer"
    APP_VERSION = "2.0.0"
    ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@harddiskanalyzer.local")


class DevelopmentConfig(BaseConfig):
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL",
        f"sqlite:///{BASE_DIR / 'diskguardian.db'}"
    )
    SESSION_COOKIE_SECURE = False
    WTF_CSRF_ENABLED      = True


class ProductionConfig(BaseConfig):
    DEBUG = False
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", "")
    SESSION_COOKIE_SECURE   = True
    WTF_CSRF_ENABLED        = True

    # Fix Railway/Render postgres:// prefix
    @classmethod
    def init_app(cls, app):
        url = app.config.get("SQLALCHEMY_DATABASE_URI", "")
        if url.startswith("postgres://"):
            app.config["SQLALCHEMY_DATABASE_URI"] = url.replace("postgres://", "postgresql://", 1)


class TestingConfig(BaseConfig):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    WTF_CSRF_ENABLED        = False


_configs = {
    "development": DevelopmentConfig,
    "production":  ProductionConfig,
    "testing":     TestingConfig,
}


def get_config(name: str):
    return _configs.get(name, DevelopmentConfig)
