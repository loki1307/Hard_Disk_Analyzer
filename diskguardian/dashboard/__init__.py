# -*- coding: utf-8 -*-
"""diskguardian/dashboard/__init__.py"""
from flask import Blueprint
dashboard_bp = Blueprint("dashboard", __name__, template_folder="../templates/dashboard")
from . import routes  # noqa: E402, F401
