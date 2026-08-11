"""Order list and detail routes."""

from flask import Blueprint, jsonify, request, session
from app.extensions import limiter
from app.helpers import get_db

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
                  'paid_at', 'created_at']
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
