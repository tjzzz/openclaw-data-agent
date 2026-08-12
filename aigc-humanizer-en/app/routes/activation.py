"""
Activation/recharge code routes — redeem codes, check word balance.
Users redeem codes purchased from various channels for word credit.
"""

import logging
from flask import Blueprint, request, jsonify, session
from app.extensions import limiter
from app.helpers import get_db, login_required, recover_awaiting_balance_orders
from app.models import ActivationCode, User

activation_bp = Blueprint('activation', __name__)


@activation_bp.route('/api/redeem-code', methods=['POST'])
@limiter.limit("10 per minute")
@login_required
def api_redeem_code():
    """
    Redeem an activation code.
    Request body: { "code": "XXXX-XXXX-XXXX" }
    Returns: { "success": true, "balance": 2000, "message": "..." }
    """
    data = request.get_json(silent=True) or {}
    code = (data.get('code', '') or '').strip().upper()

    if not code:
        return jsonify({"error": "请输入兑换码"}), 400
    if len(code) < 8:
        return jsonify({"error": "兑换码格式不正确"}), 400

    user_id = session.get('user_id')
    conn = get_db()

    success, message = ActivationCode.redeem(conn, code, user_id)
    if not success:
        return jsonify({"error": message}), 400

    balance = User.get_balance(conn, user_id)
    logging.info(f"[ACTIVATION] User {user_id} redeemed code {code}, new balance={balance}")
    recovered_orders = recover_awaiting_balance_orders(user_id)
    balance = User.get_balance(conn, user_id)

    return jsonify({
        "success": True,
        "balance": balance,
        "message": message,
        "recovered_order_ids": recovered_orders,
    })


@activation_bp.route('/api/user/balance', methods=['GET'])
@login_required
def api_user_balance():
    """Get current user's word balance."""
    user_id = session.get('user_id')
    conn = get_db()
    balance = User.get_balance(conn, user_id)
    return jsonify({
        "success": True,
        "balance": balance
    })
