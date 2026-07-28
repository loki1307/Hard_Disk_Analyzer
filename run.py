# -*- coding: utf-8 -*-
"""run.py — Entry point for AI Disk Guardian Pro.
Usage:
  python run.py            → Development server
  gunicorn diskguardian:application   → Production (Railway/Render)
"""

import os
import ssl
import pathlib
from dotenv import load_dotenv

load_dotenv()

from diskguardian import create_app

# Module-level instance for gunicorn: `gunicorn run:application`
application = create_app(os.environ.get("FLASK_ENV", "development"))

if __name__ == "__main__":
    cert = pathlib.Path("cert.pem")
    key  = pathlib.Path("key.pem")
    use_ssl = cert.exists() and key.exists()

    port     = int(os.environ.get("PORT", 5001))   # 5001 to not conflict with old server.py
    protocol = "https" if use_ssl else "http"
    sep      = "=" * 62

    print(f"\n{sep}")
    print("  Hard Disk Analyzer v2.0.0")
    print(f"  {protocol}://localhost:{port}")
    print(f"  {protocol}://10.167.195.133:{port}")
    print(f"  SSL: {'ENABLED' if use_ssl else 'DISABLED'}")
    print(f"  ENV: {os.environ.get('FLASK_ENV', 'development')}")
    print(sep + "\n")

    ssl_ctx = None
    if use_ssl:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(certfile=str(cert), keyfile=str(key))
        ssl_ctx = ctx

    application.run(
        host="0.0.0.0",
        port=port,
        debug=os.environ.get("FLASK_ENV") == "development",
        ssl_context=ssl_ctx,
        use_reloader=False,
    )
