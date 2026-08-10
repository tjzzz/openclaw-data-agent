"""
Rewrite routes — execute text humanization and save order record.
"""

import logging
from flask import Blueprint, request, jsonify, session
from app.extensions import limiter
from app.helpers import generate_order_id, get_db, login_required, rewrite_and_analyze
from config import PRICE_PER_1000_WORDS

rewrite_bp = Blueprint('rewrite', __name__)


@rewrite_bp.route('/api/rewrite', methods=['POST'])
@limiter.limit("30 per minute")
@login_required
def api_rewrite():
    """
    Rewrite text to reduce AI detection score.
    Executes the humanization immediately and saves the order record.
    Requires login.

    Payment:
    1. 检查用户词数余额（word_balance），足够则扣余额改写
    2. 余额不足 → 返回 402 要求支付
    """
    from app.models import Order, User, BalanceTransaction

    data = request.get_json(silent=True) or {}
    text = data.get('text') or session.get('last_text', '')
    # mode 语义为"改写粒度"：low/median/high（默认 median，聚合段数可配）
    mode = data.get('mode')
    if mode not in ('low', 'median', 'high'):
        mode = 'median'

    if not text:
        return jsonify({"error": "没有可改写的文本，请先分析"}), 400

    word_count = len(text.split())
    user_id = session.get('user_id')
    order_id = generate_order_id()
    payment_status = None
    balance_deducted = 0

    # ── 检查词数余额，足够则扣余额改写 ──
    conn = get_db()
    balance = User.get_balance(conn, user_id)
    if balance < word_count:
        shortfall = word_count - balance
        return jsonify({
            "error": f"余额不足（当前 {balance} 词，需 {word_count} 词），还差 {shortfall} 词",
            "balance": balance,
            "word_count": word_count,
            "shortfall": shortfall,
            "need_payment": True
        }), 402

    # 余额扣减与消费流水必须在同一事务中提交。
    try:
        balance_remaining = User.deduct_balance(conn, user_id, word_count)
        if balance_remaining is not None:
            BalanceTransaction.create(
                conn, user_id, 'rewrite_consumption', -word_count,
                balance_remaining, order_id=order_id, description='改写任务扣费'
            )
            conn.commit()
    except Exception:
        conn.rollback()
        logging.exception(f"[BALANCE] Failed to charge user {user_id}")
        return jsonify({"error": "余额扣费失败，请稍后重试"}), 500

    if balance_remaining is None:
        conn.rollback()
        balance = User.get_balance(conn, user_id)
        shortfall = word_count - balance
        return jsonify({
            "error": f"余额不足（当前 {balance} 词，需 {word_count} 词），还差 {shortfall} 词",
            "balance": balance,
            "word_count": word_count,
            "shortfall": shortfall,
            "need_payment": True
        }), 402
    balance_deducted = word_count
    payment_status = 'balance'
    logging.info(f"[BALANCE] User {user_id} used balance: deducted {word_count} words, remaining: {balance_remaining}")

    price = round(PRICE_PER_1000_WORDS * (word_count / 1000), 2)

    try:
        # 传入段落结构（若存在），实现结构保护：标题/表格/参考文献/短段不改写
        paragraphs = session.get('last_paragraphs')
        result = rewrite_and_analyze(text, mode=mode, paragraphs=paragraphs)
        humanized = result["humanized"]
        rewritten_structured = result["rewritten_paragraphs"]
        original_analysis = result["original_analysis"]
        rewritten_analysis = result["rewritten_analysis"]

        # Build paragraph comparison for frontend display
        original_paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]
        rewritten_paragraphs = [p.strip() for p in humanized.split('\n\n') if p.strip()]

        paragraph_comparison = []
        for i, (orig_p, new_p) in enumerate(zip(original_paragraphs, rewritten_paragraphs)):
            if len(orig_p) >= 100 and len(new_p) >= 100:
                paragraph_comparison.append({
                    "index": i,
                    "original_preview": orig_p[:150] + "..." if len(orig_p) > 150 else orig_p,
                    "rewritten_preview": new_p[:150] + "..." if len(new_p) > 150 else new_p,
                    "original_score": round(original_analysis['ai_score'], 1),
                    "rewritten_score": round(rewritten_analysis['ai_score'], 1),
                    "reduction": round(original_analysis['ai_score'] - rewritten_analysis['ai_score'], 1)
                })

        # Save order record
        original_format = session.get('last_original_format', 'txt')
        original_filename = session.get('last_original_filename', None)
        try:
            conn = get_db()
            Order.create_balance_order(
                conn,
                user_id=user_id,
                order_id=order_id,
                original_text=text,
                rewritten_text=humanized,
                original_format=original_format,
                original_filename=original_filename,
                word_count=word_count,
                price=price,
                mode=mode,
                original_score=original_analysis.get('ai_score', 0),
                rewritten_score=rewritten_analysis.get('ai_score', 0),
                rewritten_paragraphs=rewritten_structured
            )
        except Exception:
            logging.exception("Failed to save order record, but rewrite result was returned")

        # Store in session for unauthenticated download fallback
        session['last_rewritten'] = {
            'original': text,
            'rewritten': humanized,
            'original_score': original_analysis.get('ai_score', 0),
            'rewritten_score': rewritten_analysis.get('ai_score', 0),
            'order_id': order_id
        }

        response_data = {
            "success": True,
            "order_id": order_id,
            "payment_status": payment_status,
            "original": {
                "text": text,
                "ai_score": round(original_analysis['ai_score'], 1),
                "risk_level": original_analysis['risk_level']
            },
            "rewritten": {
                "text": humanized,
                "ai_score": round(rewritten_analysis['ai_score'], 1),
                "risk_level": rewritten_analysis['risk_level']
            },
            "improvement": round(original_analysis['ai_score'] - rewritten_analysis['ai_score'], 1),
            "paragraph_comparison": paragraph_comparison,
            "original_format": original_format,
            "original_filename": original_filename
        }

        if payment_status == 'balance':
            response_data["balance_remaining"] = User.get_balance(get_db(), user_id)

        return jsonify(response_data)

    except Exception:
        if payment_status == 'balance' and balance_deducted:
            try:
                conn = get_db()
                User.add_balance(conn, user_id, balance_deducted)
                balance_after = User.get_balance(conn, user_id)
                BalanceTransaction.create(
                    conn, user_id, 'rewrite_refund', balance_deducted,
                    balance_after, order_id=order_id, description='改写失败退回词数'
                )
                conn.commit()
                logging.warning(f"[BALANCE] Refunded {balance_deducted} words to user {user_id} after rewrite failure")
            except Exception:
                conn.rollback()
                logging.exception(f"[BALANCE] Failed to refund {balance_deducted} words to user {user_id}")
        logging.exception("Rewrite failed")
        return jsonify({"error": "改写出错，请稍后重试"}), 500
