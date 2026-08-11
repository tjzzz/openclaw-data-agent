"""
AI Humanizer - Application Factory
Creates and configures the Flask application instance.
"""

import os
import sys
import logging
import threading
from datetime import timedelta

from flask import Flask, jsonify
from flask_wtf.csrf import CSRFError


# Configure logging: structured format for production debugging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)


def create_app():
    """Create and configure the Flask application."""
    # 项目根目录加入 Python 路径，config.py 在根目录
    _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if _root not in sys.path:
        sys.path.insert(0, _root)

    from config import PROJ_ROOT, SECRET_KEY, PAYMENT_ADAPTER, HUMANIZER_ADAPTER, AI_DETECTOR_ADAPTER

    app = Flask(__name__,
                root_path=PROJ_ROOT,
                template_folder=os.path.join(PROJ_ROOT, 'templates'),
                static_folder=os.path.join(PROJ_ROOT, 'static'),
                static_url_path='/static')

    # ── Secret key ──
    if not SECRET_KEY:
        raise RuntimeError(
            "SECRET_KEY must be set in config.py. "
            "Generate one with: python -c 'import secrets; print(secrets.token_hex(32))'"
        )
    app.secret_key = SECRET_KEY

    # ── Configuration ──
    app.config['MAX_CONTENT_LENGTH'] = 20 * 1024 * 1024  # 20MB
    app.config['UPLOAD_FOLDER'] = os.path.join(PROJ_ROOT, 'uploads')
    app.config['SOURCE_DOCS_FOLDER'] = os.path.join(PROJ_ROOT, 'instance', 'source_docs')
    app.config['OUTPUT_DOCS_FOLDER'] = os.path.join(PROJ_ROOT, 'instance', 'output_docs')
    app.config['PAYMENT_ADAPTER'] = PAYMENT_ADAPTER
    app.config['HUMANIZER_ADAPTER'] = HUMANIZER_ADAPTER
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=2)
    # Disable SSL strict referrer check (Flask-WTF 1.3+ default), which can
    # falsely reject valid requests behind HTTPS reverse proxies (nginx, CDN).
    app.config['WTF_CSRF_SSL_STRICT'] = False

    # ── Filesystem session ──
    from app.session import FileSystemSessionInterface
    _session_dir = os.path.join(PROJ_ROOT, 'instance', 'flask_session')
    os.makedirs(_session_dir, exist_ok=True)
    app.session_interface = FileSystemSessionInterface(_session_dir)

    # ── Upload folder ──
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(app.config['SOURCE_DOCS_FOLDER'], exist_ok=True)
    os.makedirs(app.config['OUTPUT_DOCS_FOLDER'], exist_ok=True)

    # ── Database ──
    from app.models import init_db
    init_db()

    # ── Adapters ──
    from app.extensions import set_adapters, set_ai_detector
    from app.payment_adapter import create_payment_adapter
    from app.humanizer import create_humanizer
    from app.ai_detector import create_detector

    payment_adapter = create_payment_adapter()
    humanizer_adapter = create_humanizer(
        app.config.get('HUMANIZER_ADAPTER', 'rule_based')
    )
    logging.info("Using %s", type(humanizer_adapter).__name__)
    set_adapters(payment_adapter, humanizer_adapter)

    # ── AI Detector ──
    detect_fn = create_detector(AI_DETECTOR_ADAPTER)
    set_ai_detector(detect_fn)

    # ── Safety check: mock adapter in production ──
    if app.config.get('PAYMENT_ADAPTER') == 'mock' and os.environ.get('FLASK_ENV') == 'production':
        raise RuntimeError(
            "Refusing to start: PAYMENT_ADAPTER=mock is not allowed in production. "
            "Set PAYMENT_ADAPTER=alipay and configure Alipay credentials."
        )
    if app.config.get('PAYMENT_ADAPTER') == 'mock':
        logging.warning("PAYMENT_ADAPTER=mock is enabled. This should only be used for development.")

    # ── Extensions (csrf, limiter) ──
    from app.extensions import csrf, limiter
    csrf.init_app(app)
    limiter.init_app(app)

    # ── Startup: recover stuck processing orders (separate thread, avoid occupying pool worker) ──
    from app.helpers import recover_processing_orders
    _recovery_thread = threading.Thread(target=recover_processing_orders, daemon=True)
    _recovery_thread.start()

    # ── Register all blueprints ──
    from app.routes import main_bp, auth_bp, analysis_bp, rewrite_bp, \
        payment_bp, download_bp, orders_bp, activation_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(analysis_bp)
    app.register_blueprint(rewrite_bp)
    app.register_blueprint(payment_bp)
    app.register_blueprint(download_bp)
    app.register_blueprint(orders_bp)
    app.register_blueprint(activation_bp)

    # ── Teardown: close database connection ──
    from app.helpers import close_db
    app.teardown_appcontext(close_db)

    # ── Security headers ──
    @app.after_request
    def add_security_headers(response):
        """Add security headers to all responses."""
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['X-XSS-Protection'] = '0'  # Deprecated, kept for legacy compat
        return response

    # ── Global error handlers ──
    @app.errorhandler(CSRFError)
    def handle_csrf_error(e):
        logging.warning(f"CSRF validation failed: {e.description}")
        response = jsonify({"error": "安全验证已过期，请重试"})
        response.headers['X-CSRF-Error'] = '1'
        response.headers['Cache-Control'] = 'no-store, private'
        return response, 400

    @app.errorhandler(400)
    def handle_400(e):
        return jsonify({"error": "请求格式错误"}), 400

    @app.errorhandler(401)
    def handle_401(e):
        return jsonify({"error": "需要登录", "login_required": True}), 401

    @app.errorhandler(413)
    def handle_413(e):
        return jsonify({"error": "文件过大，最大支持 20MB"}), 413

    @app.errorhandler(403)
    def handle_403(e):
        return jsonify({"error": "无权访问"}), 403

    @app.errorhandler(404)
    def handle_404(e):
        return jsonify({"error": "请求的资源不存在"}), 404

    @app.errorhandler(405)
    def handle_405(e):
        return jsonify({"error": "请求方法不允许"}), 405

    @app.errorhandler(500)
    def handle_500(e):
        logging.exception("Internal server error")
        return jsonify({"error": "服务器内部错误，请稍后重试"}), 500

    # ── CSRF Exemptions ──
    # All API routes receive CSRF protection via X-CSRFToken header from the
    # frontend (_csrfFetch in common.js). The Alipay webhook is exempted
    # because Alipay's servers cannot send our CSRF token. The public analysis
    # endpoints are also exempted so that non-logged-in users can use the
    # core detection feature without needing a server-side session match.
    _csrf_exempt_routes = [
        'payment.api_webhook_alipay',
        'analysis.api_analyze',
        'analysis.api_preview_rewrite',
        'analysis.api_suggestion_detail',
    ]
    for _route in _csrf_exempt_routes:
        _func = app.view_functions.get(_route)
        if _func:
            csrf.exempt(_func)

    return app
