# -*- coding: utf-8 -*-
"""diskguardian/extensions.py — Shared Flask extension instances."""

from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_mail import Mail
from flask_wtf.csrf import CSRFProtect
from flask_migrate import Migrate

db           = SQLAlchemy()
login_manager = LoginManager()
limiter      = Limiter(key_func=get_remote_address, default_limits=["300 per minute"])
mail         = Mail()
csrf         = CSRFProtect()
migrate      = Migrate()

login_manager.login_view       = "auth.login"
login_manager.login_message    = "Please sign in to access Hard Disk Analyzer."
login_manager.login_message_category = "info"
