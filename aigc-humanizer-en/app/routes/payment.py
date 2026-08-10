"""
Payment routes — create payment order, check payment status,
Alipay webhook handler, and test mock payment.
"""

import logging
from flask import Blueprint, request, jsonify, session
from app.extensions import limiter
from app.helpers import (
    generate_order_id, get_db, login_required, process_payment_success
)
from config import PRICE_PER_1000_WORDS

payment_bp = Blueprint('payment', __name__)


@payment_bp.route('/api/payment-config', methods=['GET'])
def api_payment_config():
    """
    Get payment configuration info (adapter type).
    """
    from flask import current_app
    import config
    
    adapter_type = current_app.config.get('PAYMENT_ADAPTER', 'mock')
    
    return jsonify({
        "adapter_type": adapter_type,
        "is_mock": adapter_type == 'mock',
        "recharge_packages": getattr(
            config, 'RECHARGE_PACKAGE_WORDS', [2000, 5000, 10000]
        )
    })


@payment_bp.route('/api/create-payment', methods=['POST'])
@limiter.limit("30 per minute")
@login_required
def api_create_payment():
    """
    Create an auto-recharge order and return a QR code for scanning.

    Cash only buys word balance. After payment succeeds, the recharge is
    credited and the linked rewrite task is charged automatically.
    """
    from app.extensions import payment_adapter as adapter
    from app.models import Order, User

    data = request.get_json(silent=True) or {}
    text = data.get('text') or session.get('last_text', '')
    # mode 语义为"改写粒度"：low/median/high，默认 median（聚合段数可配）
    mode = data.get('mode')
    if mode not in ('low', 'median', 'high'):
        mode = 'median'

    if not text:
        return jsonify({"error": "没有可改写的文本，请先分析"}), 400

    word_count = len(text.split())
    user_id = session.get('user_id')
    conn = get_db()
    balance = User.get_balance(conn, user_id)
    shortfall = max(word_count - balance, 0)

    if shortfall == 0:
        return jsonify({
            "error": "当前余额充足，无需充值",
            "balance_sufficient": True,
            "balance": balance,
            "word_count": word_count
        }), 409

    requested_recharge = data.get('recharge_words') or shortfall
    try:
        recharge_words = int(requested_recharge)
    except (TypeError, ValueError):
        return jsonify({"error": "充值词数不正确"}), 400

    if recharge_words < shortfall:
        return jsonify({
            "error": f"至少需要充值 {shortfall} 词才能完成本次任务",
            "balance": balance,
            "shortfall": shortfall
        }), 400
    if recharge_words > 100000:
        return jsonify({"error": "单次充值词数不能超过 100000"}), 400

    price = round(PRICE_PER_1000_WORDS * (recharge_words / 1000), 2)

    order_id = generate_order_id()

    original_format = session.get('last_original_format', 'txt')
    original_filename = session.get('last_original_filename', None)
    try:
        # 保存段落结构（含 style/is_heading/is_reference），供异步改写做结构保护
        paragraphs = session.get('last_paragraphs')
        Order.create_payment_record(
            conn, user_id, order_id, text, original_format, original_filename,
            word_count, price, mode, recharge_words, min(balance, word_count),
            paragraphs=paragraphs
        )
        logging.info(
            f"[PAYMENT] Recharge order created: {order_id}, user={user_id}, "
            f"task_words={word_count}, recharge_words={recharge_words}, price={price}"
        )
    except Exception:
        logging.exception("Failed to create payment order")
        return jsonify({"error": "创建订单失败，请稍后重试"}), 500

    # ★ 优先使用 create_prepay_form()（qr_pay_mode=4 + iframe）
    #   降级到 create_prepay_order()（qr_pay_mode=1 + qrcode.js）
    subject = f"Huma词数充值 - {recharge_words}词"
    if hasattr(adapter, 'create_prepay_form'):
        logging.info(f"[PAYMENT] Calling adapter.create_prepay_form for {order_id}")
        result = adapter.create_prepay_form(order_id, price, subject)
        # ★ P2: create_prepay_form 失败时自动降级到 create_prepay_order
        if result.get('error') and hasattr(adapter, 'create_prepay_order'):
            logging.warning(
                f"create_prepay_form failed ({result.get('error')}), "
                f"falling back to create_prepay_order for {order_id}"
            )
            result = adapter.create_prepay_order(order_id, price, subject)
    else:
        logging.info(f"[PAYMENT] Calling adapter.create_prepay_order for {order_id}")
        result = adapter.create_prepay_order(order_id, price, subject)

    form_html = result.get('form_html')
    qr_code = result.get('qr_code')
    logging.info(
        f"[PAYMENT] Adapter result for {order_id}: "
        f"has_error={bool(result.get('error'))}, "
        f"has_form_html={bool(form_html)}, "
        f"has_qr_code={bool(qr_code)}"
    )

    if result.get('error'):
        logging.error(
            f"Payment adapter create_prepay failed: "
            f"error={result.get('error')}, "
            f"code={result.get('code')}, "
            f"sub_code={result.get('sub_code')}, "
            f"order_id={result.get('order_id')}"
        )
        return jsonify({"error": "支付创建失败，请稍后重试"}), 500

    if qr_code:
        Order.save_qr_code(conn, order_id, qr_code)

    return jsonify({
        "success": True,
        "order": {
            "order_id": order_id,
            "word_count": word_count,
            "balance": balance,
            "shortfall": shortfall,
            "recharge_words": recharge_words,
            "balance_words_used": min(balance, word_count),
            "balance_after": balance + recharge_words - word_count,
            "price": price,
            "form_html": form_html,
            "qr_code": qr_code,
            "mode": mode,
            "expires_in": result.get('expires_in', 600)
        }
    })


@payment_bp.route('/api/payment-status/<order_id>')
@limiter.limit("20 per minute")
@login_required
def api_payment_status(order_id):
    """Check payment status for an order (used by frontend polling)."""
    from app.extensions import payment_adapter as adapter
    from app.models import Order, User

    user_id = session.get('user_id')
    conn = get_db()

    Order.expire_old_orders(conn)

    order = Order.get_by_order_id(conn, order_id)
    logging.info(f"[POLL] order_id={order_id}, user={user_id}, found={order is not None}")
    if not order:
        return jsonify({"error": "订单不存在"}), 404

    if order['user_id'] != user_id:
        return jsonify({"error": "无权访问该订单"}), 403

    payment_status = order.get('payment_status', 'pending')
    status = order.get('status', 'pending')

    if payment_status == 'pending':
        try:
            query_result = adapter.query_payment(order_id)
            logging.info(
                f"Payment query for {order_id}: "
                f"trade_status={query_result.get('trade_status')}, "
                f"status={query_result.get('status')}"
            )
            if query_result.get('status') == 'paid':
                trade_no = query_result.get('trade_no') or f"QUERY_{order_id}"
                process_payment_success(order_id, trade_no)
                # Refresh order from DB to get updated status
                order = Order.get_by_order_id(conn, order_id)
                payment_status = order.get('payment_status', 'paid')
                status = order.get('status', 'processing')
        except Exception:
            logging.warning("Payment query failed, returning current status", exc_info=True)

    current_balance = User.get_balance(conn, user_id)
    response = {
        "order_id": order_id,
        "payment_status": payment_status,
        "status": status,
        "price": order.get('price'),
        "word_count": order.get('word_count'),
        "recharge_words": order.get('recharge_words', 0),
        "balance_words_used": order.get('balance_words_used', 0),
        "balance_after": current_balance,
        "current_balance": current_balance
    }

    if status == 'awaiting_balance':
        response['message'] = '充值已到账，但账户余额仍不足，请补足后继续任务'

    if status == 'completed' and order.get('rewritten_text'):
        from app.helpers import derive_risk_level
        original_score = order.get('original_score', 0) or 0
        rewritten_score = order.get('rewritten_score', 0) or 0
        response.update({
            "success": True,
            "original": {
                "text": order['original_text'],
                "ai_score": round(original_score, 1),
                "risk_level": derive_risk_level(original_score)
            },
            "rewritten": {
                "text": order['rewritten_text'],
                "ai_score": round(rewritten_score, 1),
                "risk_level": derive_risk_level(rewritten_score) if order['rewritten_text'] else 'unknown'
            },
            "improvement": round((order.get('original_score', 0) or 0) - (order.get('rewritten_score', 0) or 0), 1),
            "original_format": order.get('original_format', 'txt'),
            "original_filename": order.get('original_filename')
        })

    return jsonify(response)


@payment_bp.route('/api/webhook/alipay', methods=['POST'])
def api_webhook_alipay():
    """
    Alipay async notification webhook.
    Called by Alipay servers after payment is completed.
    """
    from app.extensions import payment_adapter as adapter
    from app.models import Order

    params = request.form.to_dict()
    sign = params.pop('sign', None)
    sign_type = params.pop('sign_type', None)

    is_valid, order_id, trade_no, amount = adapter.verify_notification(params, sign)

    if not is_valid:
        return "fail", 200

    conn = get_db()
    order = Order.get_by_order_id(conn, order_id)
    if not order:
        return "fail", 200

    if order.get('payment_status') != 'pending':
        return "success", 200

    if amount and abs(round(amount * 100) - round((order.get('price') or 0) * 100)) > 1:
        return "fail", 200

    if trade_no:
        existing = conn.execute(
            "SELECT order_id FROM orders WHERE alipay_trade_no = ? AND order_id != ?",
            (trade_no, order_id)
        ).fetchone()
        if existing:
            logging.warning(f"Duplicate trade_no {trade_no} attempted for order {order_id}, already used by {existing['order_id']}")
            return "fail", 200

    try:
        process_payment_success(order_id, trade_no)
    except Exception:
        logging.exception(f"Payment processing failed for order {order_id}")
        return "fail", 200

    return "success", 200


@payment_bp.route('/api/test/mock-payment/<order_id>', methods=['POST'])
@limiter.limit("3 per minute")
def api_test_mock_payment(order_id):
    """
    Simulate a successful payment for testing purposes.
    Only available when PAYMENT_ADAPTER=mock.
    """
    from flask import current_app
    from app.models import Order

    if current_app.config.get('PAYMENT_ADAPTER') != 'mock':
        return jsonify({"error": "仅在 mock 模式下可用"}), 403

    conn = get_db()
    order = Order.get_by_order_id(conn, order_id)
    if not order:
        return jsonify({"error": "订单不存在"}), 404

    if order.get('payment_status') != 'pending':
        return jsonify({"error": "订单已处理，无法再次模拟支付"}), 400

    trade_no = f"MOCK_TRADE_{order_id}"
    try:
        process_payment_success(order_id, trade_no)
        return jsonify({"success": True, "message": "支付模拟成功，正在后台改写...", "order_id": order_id})
    except Exception:
        logging.exception("Mock payment processing failed")
        return jsonify({"error": "支付处理失败，请稍后重试"}), 500
