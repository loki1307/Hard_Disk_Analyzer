# -*- coding: utf-8 -*-
"""diskguardian/api/__init__.py — JSON API blueprint (CSRF-exempt, auth via session)."""
from flask import Blueprint
from ..extensions import csrf

api_bp = Blueprint("api", __name__)
csrf.exempt(api_bp)   # API uses session auth + JSON, not HTML forms

from . import routes  # noqa: E402, F401

