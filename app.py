# -*- coding: utf-8 -*-
"""app.py — Render-compatible entry point.
Render defaults to 'gunicorn app:app', so this file satisfies that expectation.
"""
import os
from dotenv import load_dotenv

load_dotenv()

from diskguardian import create_app

app = application = create_app(os.environ.get("FLASK_ENV", "production"))
