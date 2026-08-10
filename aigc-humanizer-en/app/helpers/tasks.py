"""Background task helpers: payment processing & async rewrite orchestration."""

import json
import logging
from datetime import datetime, timezone


def _load_paragraphs(order):
    """从订单记录反序列化段落结构（orders.paragraphs 为 JSON 字符串）。"""
    raw = order.get('paragraphs')
    if not raw:
        return None
    try:
        paras = json.loads(raw)
        return paras if isinstance(paras, list) else None
    except (ValueError, TypeError):
        logging.warning(f"Failed to parse paragraphs for order {order.get('order_id')}")
        return None


def rewrite_and_analyze(text, mode=None, paragraphs=None):
    """执行改写与 AI 检测，返回结构化结果。余额同步与付费异步共用。

    Args:
        text: 待改写的原文。
        mode: 改写粒度（low/median/high），None 时取默认（median）。
        paragraphs: 可选段落结构（list[dict]），用于结构保护。

    Returns:
        dict:
            {
                "humanized": str,                 # 改写后文本
                "rewritten_paragraphs": list|None,# 改写后结构化段落（含标题级别）
                "original_analysis": dict,        # 原文检测结果
                "rewritten_analysis": dict,       # 改写后检测结果
            }

    Raises:
        改写或检测失败时向上抛异常，由调用方决定错误处理（余额回滚/标记失败）。
    """
    from app.extensions import humanizer_adapter, ai_detector as analyze_text

    humanized, rewritten_paragraphs = humanizer_adapter.humanize_structured(
        text, mode=mode, paragraphs=paragraphs
    )
    original_analysis = analyze_text(text)
    rewritten_analysis = analyze_text(humanized)
    return {
        "humanized": humanized,
        "rewritten_paragraphs": rewritten_paragraphs,
        "original_analysis": original_analysis,
        "rewritten_analysis": rewritten_analysis,
    }


def do_background_rewrite(order_id, text, mode, paragraphs=None):
    """
    Execute the actual humanization rewrite for a paid order.
    Runs in a background thread. Creates its own DB connection.

    paragraphs: 可选的段落结构（list[dict]，来自订单存储），用于结构保护。
    """
    try:
        from app.models import get_connection, Order

        result = rewrite_and_analyze(text, mode=mode, paragraphs=paragraphs)
        humanized = result["humanized"]
        rewritten_paragraphs = result["rewritten_paragraphs"]
        rewritten_analysis = result["rewritten_analysis"]
        original_analysis = result["original_analysis"]

        conn = get_connection()
        try:
            Order.update_result(
                conn, order_id, humanized,
                rewritten_analysis.get('ai_score', 0),
                original_analysis.get('ai_score', 0),
                rewritten_paragraphs=rewritten_paragraphs
            )
        finally:
            conn.close()
    except Exception:
        logging.exception(f"Background rewrite failed for {order_id}")
        try:
            from app.models import get_connection, Order, User, BalanceTransaction
            conn = get_connection()
            try:
                order = Order.get_by_order_id(conn, order_id)
                if order and order.get('payment_status') in ('paid', 'balance'):
                    existing_refund = conn.execute(
                        """SELECT id FROM balance_transactions
                           WHERE order_id = ? AND transaction_type = 'rewrite_refund'""",
                        (order_id,)
                    ).fetchone()
                    if not existing_refund:
                        User.add_balance(conn, order['user_id'], order['word_count'])
                        balance_after = User.get_balance(conn, order['user_id'])
                        BalanceTransaction.create(
                            conn, order['user_id'], 'rewrite_refund', order['word_count'],
                            balance_after, order_id=order_id, description='改写失败退回词数'
                        )
                        conn.execute(
                            "UPDATE orders SET balance_after = ? WHERE order_id = ?",
                            (balance_after, order_id)
                        )
                Order.mark_failed(conn, order_id)
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()
        except Exception:
            logging.exception(f"Failed to mark order {order_id} as failed")


def process_payment_success(order_id, trade_no):
    """
    Internal function to handle successful payment.
    Marks order as paid and triggers rewrite via thread pool.
    Idempotent: skips if order is already in processing/completed/failed state.
    """
    from app.models import Order, User, BalanceTransaction, get_connection
    from app.extensions import rewrite_executor

    # Use a dedicated connection so this function always owns its transaction.
    # The caller connection may have performed reads or writes before invoking us.
    tx_conn = get_connection()
    try:
        tx_conn.execute("BEGIN IMMEDIATE")
        order = Order.get_by_order_id(tx_conn, order_id)
        if not order:
            tx_conn.rollback()
            logging.error(f"Order {order_id} not found during payment processing")
            return False

        current_payment_status = order.get('payment_status', 'pending')
        if current_payment_status != 'pending':
            tx_conn.rollback()
            logging.info(
                f"Order {order_id} already in payment_status={current_payment_status}, "
                f"skipping duplicate processing"
            )
            return current_payment_status == 'paid'

        user_id = order['user_id']
        recharge_words = int(order.get('recharge_words') or order['word_count'])

        # Payment always buys word balance first.
        User.add_balance(tx_conn, user_id, recharge_words)
        balance_after_recharge = User.get_balance(tx_conn, user_id)
        BalanceTransaction.create(
            tx_conn, user_id, 'payment_recharge', recharge_words,
            balance_after_recharge, order_id=order_id,
            reference_id=trade_no, description='支付宝充值'
        )

        # Then charge the rewrite from the unified balance wallet.
        cursor = tx_conn.execute(
            """UPDATE users SET word_balance = word_balance - ?
               WHERE id = ? AND word_balance >= ?""",
            (order['word_count'], user_id, order['word_count'])
        )
        if cursor.rowcount == 0:
            tx_conn.execute(
                """UPDATE orders
                   SET payment_status = 'paid', status = 'awaiting_balance',
                       alipay_trade_no = ?, paid_at = ?, balance_after = ?
                   WHERE order_id = ? AND payment_status = 'pending'""",
                (trade_no, datetime.now(timezone.utc).isoformat(),
                 balance_after_recharge, order_id)
            )
            tx_conn.commit()
            logging.warning(
                f"Order {order_id} recharge succeeded but balance is still insufficient"
            )
            return False

        balance_after = User.get_balance(tx_conn, user_id)
        BalanceTransaction.create(
            tx_conn, user_id, 'rewrite_consumption', -order['word_count'],
            balance_after, order_id=order_id, description='改写任务扣费'
        )
        tx_conn.execute(
            """UPDATE orders
               SET payment_status = 'paid', status = 'processing',
                   alipay_trade_no = ?, paid_at = ?, balance_after = ?
               WHERE order_id = ? AND payment_status = 'pending'""",
            (trade_no, datetime.now(timezone.utc).isoformat(), balance_after, order_id)
        )
        tx_conn.commit()
    except Exception:
        tx_conn.rollback()
        raise
    finally:
        tx_conn.close()

    # Read mode from DB（旧订单可能存 paragraph/academic，兼容为 low；缺省取默认 median）
    mode = order.get('mode') or 'median'
    if mode not in ('low', 'median', 'high'):
        mode = 'low' if mode in ('paragraph', 'academic') else 'median'
    text = order['original_text']
    paragraphs = _load_paragraphs(order)

    # Submit rewrite to thread pool (don't block the webhook response)
    rewrite_executor.submit(do_background_rewrite, order_id, text, mode, paragraphs)
    return True


def recover_processing_orders():
    """
    Scan for orders stuck in 'processing' status and re-trigger rewrite.
    This handles the case where the server restarted while a rewrite was running.
    Runs in its own thread (called from create_app).
    """
    try:
        from app.models import get_connection
        from app.extensions import rewrite_executor

        conn = get_connection()
        try:
            cursor = conn.execute("SELECT * FROM orders WHERE status = 'processing'")
            stuck_orders = [dict(row) for row in cursor.fetchall()]
            for order in stuck_orders:
                order_id = order['order_id']
                mode = order.get('mode', 'paragraph')
                text = order.get('original_text', '')
                if not text:
                    continue
                paragraphs = _load_paragraphs(order)
                logging.warning(f"Recovering stuck processing order: {order_id}")
                rewrite_executor.submit(do_background_rewrite, order_id, text, mode, paragraphs)
        finally:
            conn.close()
    except Exception:
        logging.exception("Failed to recover processing orders on startup")
