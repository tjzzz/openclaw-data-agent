"""
Orders routes — list orders, get order detail, re-humanize.
"""

import logging
from datetime import datetime, timezone
from flask import Blueprint, request, jsonify, session
from app.extensions import limiter
from app.helpers import get_db, login_required, _load_paragraphs

orders_bp = Blueprint('orders', __name__)


@orders_bp.route('/api/orders')
@limiter.limit("30 per minute")
def api_orders():
    """Get user's order list with pagination. Requires login."""
    from app.models import Order

    user_id = session.get('user_id')
    if not user_id:
        return jsonify({"error": "未登录"}), 401

    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 10, type=int), 50)

    conn = get_db()
    orders, total = Order.get_by_user_id(
        conn, user_id, page=page, per_page=per_page, history_only=True
    )

    _safe_keys = ['id', 'order_id', 'user_id', 'original_format', 'original_filename',
                  'word_count', 'price', 'mode', 'original_score', 'rewritten_score',
                  'status', 'payment_status',
                  'recharge_words', 'balance_words_used', 'balance_after',
                  'paid_at', 'created_at', 'expires_at']
    orders_safe = [
        {k: o[k] for k in _safe_keys if k in o}
        for o in orders
    ]

    total_pages = max(1, (total + per_page - 1) // per_page)

    return jsonify({
        "orders": orders_safe,
        "total": total,
        "page": page,
        "pages": total_pages
    })


@orders_bp.route('/api/orders/<order_id>')
def api_order_detail(order_id):
    """Get details for a specific order. Requires login."""
    from app.models import Order

    user_id = session.get('user_id')
    if not user_id:
        return jsonify({"error": "未登录"}), 401

    conn = get_db()
    order = Order.get_by_order_id(conn, order_id)
    if not order:
        return jsonify({"error": "订单不存在"}), 404

    if order['user_id'] != user_id:
        return jsonify({"error": "无权访问该订单"}), 403

    _safe = {k: v for k, v in order.items() if k not in ('original_text', 'rewritten_text')}
    return jsonify({"order": _safe})


@orders_bp.route('/api/orders/<order_id>/rehumanize', methods=['POST'])
def api_rehumanize(order_id):
    """
    Re-humanize an existing order (free within 7 days).
    Requires login and non-expired order.
    """
    from app.extensions import humanizer_adapter as humanizer
    from app.extensions import ai_detector as run_analysis
    from app.models import Order

    user_id = session.get('user_id')
    if not user_id:
        return jsonify({"error": "未登录"}), 401

    data = request.get_json(silent=True) or {}
    # mode 语义为"改写粒度"：low/median/high，默认 median（聚合段数可配）
    mode = data.get('mode')
    if mode not in ('low', 'median', 'high'):
        mode = 'median'

    conn = get_db()
    order = Order.get_by_order_id(conn, order_id)
    if not order:
        return jsonify({"error": "订单不存在"}), 404

    if order['user_id'] != user_id:
        return jsonify({"error": "无权操作该订单"}), 403

    if order.get('payment_status') not in ('paid', 'balance'):
        return jsonify({"error": "仅已消费词数的订单可免费再次改写"}), 403

    expires_at = order['expires_at']
    try:
        expires_dt = datetime.fromisoformat(expires_at)
        # Ensure timezone-aware comparison (expires_at is stored as UTC)
        if expires_dt.tzinfo is None:
            from datetime import timezone as tz
            expires_dt = expires_dt.replace(tzinfo=tz.utc)
    except (ValueError, TypeError):
        return jsonify({"error": "订单日期异常"}), 400

    if datetime.now(timezone.utc) > expires_dt:
        return jsonify({"error": "订单已过期（超过 7 天），请重新购买"}), 410

    try:
        base_text = order['rewritten_text'] or order['original_text']
        paragraphs = _load_paragraphs(order)
        humanized, rewritten_paragraphs = humanizer.humanize_structured(
            base_text, mode=mode, paragraphs=paragraphs
        )
        rewritten_analysis = run_analysis(humanized)

        Order.update_rewrite(
            conn, order_id, humanized, rewritten_analysis.get('ai_score', 0),
            rewritten_paragraphs=rewritten_paragraphs
        )

        original_score = order.get('original_score', 0)

        return jsonify({
            "success": True,
            "order_id": order_id,
            "original": {
                "text": order['original_text'],
                "ai_score": round(original_score, 1)
            },
            "rewritten": {
                "text": humanized,
                "ai_score": round(rewritten_analysis['ai_score'], 1),
                "risk_level": rewritten_analysis['risk_level']
            },
            "improvement": round(original_score - rewritten_analysis['ai_score'], 1)
        })
    except Exception:
        logging.exception("Re-humanize failed")
        return jsonify({"error": "改写出错，请稍后重试"}), 500
