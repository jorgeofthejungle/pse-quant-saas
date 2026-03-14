# ============================================================
# app.py — Flask App Factory & Entry Point
# PSE Quant SaaS — Dashboard
# ============================================================
# Run with:  py dashboard/app.py
# Open:      http://localhost:8080
# ============================================================

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'db'))
sys.path.insert(0, str(ROOT / 'engine'))
sys.path.insert(0, str(ROOT / 'discord'))
sys.path.insert(0, str(ROOT / 'scraper'))
sys.path.insert(0, str(ROOT / 'alerts'))
sys.path.insert(0, str(ROOT))

from flask import Flask
from dotenv import load_dotenv

load_dotenv(ROOT / '.env')

import database as db


def create_app() -> Flask:
    app = Flask(
        __name__,
        static_folder='static',
        template_folder='templates',
    )
    app.config['SECRET_KEY'] = 'pse-quant-local-dashboard'

    # Ensure DB tables exist (including new members/subscriptions/activity_log)
    db.init_db()

    # Register blueprints
    from dashboard.routes_home     import home_bp
    from dashboard.routes_pipeline import pipeline_bp
    from dashboard.routes_members  import members_bp
    from dashboard.routes_analytics import analytics_bp
    from dashboard.routes_settings import settings_bp
    from dashboard.routes_paymongo import paymongo_bp
    from dashboard.routes_stocks   import stocks_bp

    app.register_blueprint(home_bp)
    app.register_blueprint(pipeline_bp,  url_prefix='/pipeline')
    app.register_blueprint(members_bp,   url_prefix='/members')
    app.register_blueprint(analytics_bp, url_prefix='/analytics')
    app.register_blueprint(settings_bp,  url_prefix='/settings')
    app.register_blueprint(paymongo_bp,  url_prefix='/paymongo')
    app.register_blueprint(stocks_bp)

    return app


if __name__ == '__main__':
    print("=" * 55)
    print("  PSE QUANT SAAS — Dashboard")
    print("  http://localhost:8080")
    print("  Press Ctrl+C to stop")
    print("=" * 55)
    app = create_app()
    app.run(host='127.0.0.1', port=8080, debug=False)
