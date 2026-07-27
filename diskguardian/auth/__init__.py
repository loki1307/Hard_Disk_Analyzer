# -*- coding: utf-8 -*-
"""diskguardian/auth/__init__.py"""
from flask import Blueprint
auth_bp = Blueprint("auth", __name__, template_folder="../templates/auth")
from . import routes  # noqa: E402, F401
