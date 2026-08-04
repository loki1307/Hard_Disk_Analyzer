# -*- coding: utf-8 -*-
"""app.py — Render-compatible entry point.
Render defaults to 'gunicorn app:app', so this file satisfies that expectation.
"""
import os
from dotenv import load_dotenv

load_dotenv()

from diskguardian import create_app

app = create_app(os.environ.get("FLASK_ENV", "production"))

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=False)
