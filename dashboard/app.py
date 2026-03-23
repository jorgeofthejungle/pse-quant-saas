# ============================================================
# app.py — Flask App Factory & Entry Point
# PSE Quant SaaS — Dashboard
# ============================================================
# Run with:  py dashboard/app.py
# Open:      http://localhost:8080
# ============================================================

import os
import sys
import secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'db'))
sys.path.insert(0, str(ROOT / 'engine'))
sys.path.insert(0, str(ROOT / 'discord'))
sys.path.insert(0, str(ROOT / 'scraper'))
sys.path.insert(0, str(ROOT / 'alerts'))
sys.path.insert(0, str(ROOT))

from flask import Flask, render_template, jsonify, request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from dotenv import load_dotenv

load_dotenv(ROOT / '.env')

import database as db

# ── Secret key: load from .env or generate a stable per-session one ───
# Set FLASK_SECRET_KEY in .env for a persistent key across restarts.
_SECRET_KEY_PATH = Path.home() / 'AppData' / 'Local' / 'pse_quant' / '.flask_secret'


def _get_or_create_secret_key() -> str:
    """Returns a persistent secret key stored in AppData."""
    key = os.getenv('FLASK_SECRET_KEY')
    if key:
        return key
    # Try to read stored key
    try:
        return _SECRET_KEY_PATH.read_text().strip()
    except FileNotFoundError:
        pass
    # Generate and persist a new key
    new_key = secrets.token_hex(32)
    try:
        _SECRET_KEY_PATH.parent.mkdir(parents=True, exist_ok=True)
        _SECRET_KEY_PATH.write_text(new_key)
    except Exception:
        pass
    return new_key


def create_app() -> Flask:
    app = Flask(
        __name__,
        static_folder='static',
        template_folder='templates',
    )
    app.config['SECRET_KEY'] = _get_or_create_secret_key()
    app.config['TEMPLATES_AUTO_RELOAD'] = True

    # ── Rate limiting ─────────────────────────────────────────
    limiter = Limiter(
        get_remote_address,
        app=app,
        default_limits=['200 per minute', '2000 per hour'],
        storage_uri='memory://',
    )
    app.extensions['limiter'] = limiter

    # ── Error handlers ────────────────────────────────────────
    @app.errorhandler(404)
    def not_found(e):
        if request.path.startswith('/api') or request.path.startswith('/pipeline'):
            return jsonify({'error': 'Not found'}), 404
        return render_template('error.html', code=404,
                               message='Page not found.'), 404

    @app.errorhandler(500)
    def server_error(e):
        if request.path.startswith('/api') or request.path.startswith('/pipeline'):
            return jsonify({'error': 'Server error'}), 500
        return render_template('error.html', code=500,
                               message='Something went wrong. Try again shortly.'), 500

    @app.errorhandler(429)
    def rate_limited(e):
        if request.path.startswith('/api') or request.path.startswith('/pipeline'):
            return jsonify({'error': 'Too many requests'}), 429
        return render_template('error.html', code=429,
                               message='Too many requests. Please slow down.'), 429

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
    from dashboard.routes_portal        import portal_bp
    from dashboard.routes_conglomerates import conglomerates_bp
    from dashboard.routes_manual_entry  import manual_entry_bp

    app.register_blueprint(home_bp)
    app.register_blueprint(pipeline_bp,  url_prefix='/pipeline')
    app.register_blueprint(members_bp,   url_prefix='/members')
    app.register_blueprint(analytics_bp, url_prefix='/analytics')
    app.register_blueprint(settings_bp,  url_prefix='/settings')
    app.register_blueprint(paymongo_bp,  url_prefix='/paymongo')
    app.register_blueprint(stocks_bp)
    app.register_blueprint(portal_bp,          url_prefix='/portal')
    app.register_blueprint(conglomerates_bp,   url_prefix='/conglomerates')
    app.register_blueprint(manual_entry_bp,    url_prefix='/manual')

    return app


if __name__ == '__main__':
    print("=" * 55)
    print("  PSE QUANT SAAS — Dashboard")
    print("  http://localhost:8080")
    print("  Press Ctrl+C to stop")
    print("=" * 55)
    app = create_app()
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False)
