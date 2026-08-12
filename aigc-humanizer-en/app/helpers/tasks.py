"""Background task helpers: payment processing & async rewrite orchestration."""

import json
import logging
import hashlib
import threading
import time
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


# ── 原文检测结果缓存（D 方案）──
# 缓存 /api/analyze 的原文检测，供 /api/rewrite 复用，省去重复的 sapling 调用。
# 按文本 md5 寻址；单进程 Flask 足够，多 worker 场景未来换 Redis。
_ORIGINAL_ANALYSIS_CACHE = {}
_ORIGINAL_ANALYSIS_CACHE_LOCK = threading.Lock()
_ORIGINAL_ANALYSIS_CACHE_MAX = 256


def cache_original_analysis(text, analysis):
    """缓存原文检测结果，返回其文本哈希。"""
    h = hashlib.md5(text.encode('utf-8')).hexdigest()
    with _ORIGINAL_ANALYSIS_CACHE_LOCK:
        _ORIGINAL_ANALYSIS_CACHE[h] = analysis
        if len(_ORIGINAL_ANALYSIS_CACHE) > _ORIGINAL_ANALYSIS_CACHE_MAX:
            _ORIGINAL_ANALYSIS_CACHE.pop(next(iter(_ORIGINAL_ANALYSIS_CACHE)), None)
    return h


def get_cached_original_analysis(text):
    """按文本取缓存的原文检测；未命中返回 None。"""
    if not text:
        return None
    h = hashlib.md5(text.encode('utf-8')).hexdigest()
    with _ORIGINAL_ANALYSIS_CACHE_LOCK:
        return _ORIGINAL_ANALYSIS_CACHE.get(h)


# ── 改写进度注册表 ────────────────────────────
# 按 order_id 记录改写/检测的真实进度，供前端轮询展示。
# SQLite 是跨 worker 的事实来源；内存只保留短期缓存。
_REWRITE_PROGRESS = {}
_REWRITE_PROGRESS_LOCK = threading.Lock()
_REWRITE_PROGRESS_TTL_SECONDS = 3600
_DELIVERY_RETRY_LOCK = threading.Lock()
_DELIVERY_RETRY_TIMERS = {}
_DELIVERED_ORDERS = set()


def _prune_rewrite_progress(now=None):
    now = now or time.monotonic()
    expired = [key for key, value in _REWRITE_PROGRESS.items()
               if now - value[1] > _REWRITE_PROGRESS_TTL_SECONDS]
    for key in expired:
        _REWRITE_PROGRESS.pop(key, None)


def set_rewrite_progress(order_id, stage, block=None, total_blocks=None, message=""):
    """更新某订单的改写进度。"""
    updated_at = datetime.now(timezone.utc).isoformat()
    progress = {
        "stage": stage,
        "block": block,
        "total_blocks": total_blocks,
        "message": message,
        "updated_at": updated_at,
    }
    with _REWRITE_PROGRESS_LOCK:
        _prune_rewrite_progress()
        _REWRITE_PROGRESS[str(order_id)] = (progress, time.monotonic())

    try:
        from app.models import get_connection, Order
        conn = get_connection()
        try:
            Order.update_progress(conn, order_id, stage, block, total_blocks,
                                  message, updated_at)
        finally:
            conn.close()
    except Exception:
        logging.exception(f"Failed to persist rewrite progress for {order_id}")


def get_rewrite_progress(order_id):
    """从共享数据库读取进度，失败时回退到当前进程缓存。"""
    try:
        from app.models import get_connection, Order
        conn = get_connection()
        try:
            progress = Order.get_progress(conn, order_id)
            if progress:
                return progress
        finally:
            conn.close()
    except Exception:
        logging.exception(f"Failed to read persisted rewrite progress for {order_id}")

    with _REWRITE_PROGRESS_LOCK:
        _prune_rewrite_progress()
        cached = _REWRITE_PROGRESS.get(str(order_id))
        return dict(cached[0]) if cached else None


def clear_rewrite_progress(order_id):
    """改写结束后清除进度（避免内存泄漏）。"""
    with _REWRITE_PROGRESS_LOCK:
        _REWRITE_PROGRESS.pop(str(order_id), None)


def submit_rewrite_task(order_id, text, mode, paragraphs=None, attempt=1):
    """可靠提交改写任务；提交失败时保留 processing 状态并延迟重试。"""
    from app.extensions import rewrite_executor
    from app.models import Order, get_connection

    conn = get_connection()
    try:
        order = Order.get_by_order_id(conn, order_id)
    finally:
        conn.close()
    if not order or order.get('status') != 'processing':
        logging.info(
            "Skip rewrite delivery for order=%s status=%s",
            order_id, order.get('status') if order else 'missing',
        )
        with _DELIVERY_RETRY_LOCK:
            _DELIVERY_RETRY_TIMERS.pop(str(order_id), None)
        return False

    order_key = str(order_id)
    with _DELIVERY_RETRY_LOCK:
        if order_key in _DELIVERED_ORDERS:
            logging.info("Rewrite task already submitted in this process: %s", order_id)
            return True
        _DELIVERED_ORDERS.add(order_key)

    try:
        rewrite_executor.submit(_run_delivered_rewrite, order_id, text, mode, paragraphs)
        with _DELIVERY_RETRY_LOCK:
            _DELIVERY_RETRY_TIMERS.pop(order_key, None)
        logging.info("Rewrite task submitted: order=%s attempt=%d", order_id, attempt)
        return True
    except Exception:
        with _DELIVERY_RETRY_LOCK:
            _DELIVERED_ORDERS.discard(order_key)
        logging.exception(
            "Rewrite task submission failed: order=%s attempt=%d", order_id, attempt
        )
        set_rewrite_progress(order_id, "queued", message="任务排队中，正在自动重试")
        if attempt == 5:
            logging.error(
                "Rewrite task still queued after %d submission attempts: %s",
                attempt, order_id,
            )

        delay = min(2 ** attempt, 60)
        timer = threading.Timer(
            delay, submit_rewrite_task,
            args=(order_id, text, mode, paragraphs, attempt + 1),
        )
        timer.daemon = True
        with _DELIVERY_RETRY_LOCK:
            existing = _DELIVERY_RETRY_TIMERS.get(order_key)
            if existing and existing.is_alive():
                return False
            _DELIVERY_RETRY_TIMERS[order_key] = timer
        timer.start()
        return False


def _run_delivered_rewrite(order_id, text, mode, paragraphs):
    try:
        do_background_rewrite(order_id, text, mode, paragraphs)
    finally:
        with _DELIVERY_RETRY_LOCK:
            _DELIVERED_ORDERS.discard(str(order_id))


def rewrite_and_analyze(text, mode=None, paragraphs=None, original_analysis=None,
                        progress_cb=None):
    """执行改写与 AI 检测，返回结构化结果。余额同步与付费异步共用。

    Args:
        text: 待改写的原文。
        mode: 改写粒度（low/median/high），None 时取默认（median）。
        paragraphs: 可选段落结构（list[dict]），用于结构保护。
        original_analysis: 可选，预计算的原文检测结果（由 /api/analyze 缓存复用）；
            None 时重新检测，用于省去重复 sapling 调用。

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

    # 进度：原文检测
    if original_analysis is None and progress_cb:
        progress_cb(stage="detect", message="正在检测原文 AI 率")

    humanized, rewritten_paragraphs = humanizer_adapter.humanize_structured(
        text, mode=mode, paragraphs=paragraphs, progress_cb=progress_cb
    )
    # 进度：改写后检测
    if progress_cb:
        progress_cb(stage="detect_again", message="正在检测改写后 AI 率")
    if original_analysis is None:
        original_analysis = analyze_text(text, stage="rewrite_detect_original")
    rewritten_analysis = analyze_text(humanized, stage="rewrite_detect_rewritten")
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
    def _progress_cb(stage, block=None, total_blocks=None, message=""):
        set_rewrite_progress(order_id, stage, block=block,
                             total_blocks=total_blocks, message=message)

    try:
        from app.models import get_connection, Order

        set_rewrite_progress(order_id, "detect", message="正在检测原文 AI 率")
        # 复用 /api/analyze 缓存的原文检测（文本一致即命中），避免后台重复检测原文
        original_analysis = get_cached_original_analysis(text)
        result = rewrite_and_analyze(text, mode=mode, paragraphs=paragraphs,
                                     original_analysis=original_analysis,
                                     progress_cb=_progress_cb)
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
        # 改写完成：保留 done 标记供前端一次性拉取结果（不 clear，避免前端失去完成信号）
        set_rewrite_progress(order_id, "done", message="改写完成")

        # Text results are visible immediately. Format-preserving Word output
        # is generated independently so it never delays the comparison page.
        if rewritten_paragraphs and any(
                item.get('source_format') == 'docx'
                for item in rewritten_paragraphs):
            from app.extensions import document_executor
            from app.helpers.docx_renderer import generate_order_docx
            document_executor.submit(generate_order_docx, order_id)
    except Exception:
        logging.exception(f"Background rewrite failed for {order_id}")
        set_rewrite_progress(order_id, "failed", message="改写失败")
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


def process_payment_success(order_id, trade_no, paid_amount=None):
    """
    Internal function to handle successful payment.
    Marks order as paid and triggers rewrite via thread pool.
    Idempotent: skips if order is already in processing/completed/failed state.
    """
    from app.models import Order, User, BalanceTransaction, get_connection

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
        if current_payment_status == 'paid':
            tx_conn.rollback()
            stored_trade_no = order.get('alipay_trade_no')
            stored_amount = order.get('alipay_amount')
            same_trade = bool(trade_no and stored_trade_no == trade_no)
            same_amount = (
                paid_amount is not None and stored_amount is not None and
                abs(round(float(paid_amount) * 100) -
                    round(float(stored_amount) * 100)) <= 1
            )
            if same_trade and same_amount:
                logging.info("Duplicate payment confirmation accepted for %s", order_id)
                return True
            logging.warning(
                "Conflicting payment confirmation rejected for %s", order_id
            )
            return False
        if current_payment_status not in ('pending', 'expired'):
            tx_conn.rollback()
            logging.warning(
                "Payment confirmation rejected for order %s in status=%s",
                order_id, current_payment_status,
            )
            return False

        if not trade_no:
            tx_conn.rollback()
            logging.warning("Payment confirmation missing trade_no for order %s", order_id)
            return False
        if paid_amount is None:
            tx_conn.rollback()
            logging.warning("Payment confirmation missing amount for order %s", order_id)
            return False

        if paid_amount is not None:
            expected_cents = round(float(order.get('price') or 0) * 100)
            paid_cents = round(float(paid_amount) * 100)
            if abs(paid_cents - expected_cents) > 1:
                tx_conn.rollback()
                logging.warning(
                    "Payment amount mismatch for order %s: expected=%s paid=%s",
                    order_id, order.get('price'), paid_amount,
                )
                return False

        if trade_no:
            duplicate = tx_conn.execute(
                "SELECT order_id FROM orders WHERE alipay_trade_no = ? AND order_id != ?",
                (trade_no, order_id),
            ).fetchone()
            if duplicate:
                tx_conn.rollback()
                logging.warning(
                    "Payment trade_no %s already belongs to order %s",
                    trade_no, duplicate['order_id'],
                )
                return False

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
                       alipay_trade_no = ?, alipay_amount = ?, paid_at = ?, balance_after = ?
                   WHERE order_id = ? AND payment_status IN ('pending', 'expired')""",
                (trade_no, paid_amount, datetime.now(timezone.utc).isoformat(),
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
                   alipay_trade_no = ?, alipay_amount = ?, paid_at = ?, balance_after = ?
               WHERE order_id = ? AND payment_status IN ('pending', 'expired')""",
            (trade_no, paid_amount, datetime.now(timezone.utc).isoformat(),
             balance_after, order_id)
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
    submit_rewrite_task(order_id, text, mode, paragraphs)
    recover_awaiting_balance_orders(user_id)
    return True


def recover_awaiting_balance_orders(user_id):
    """Charge and resume paid orders once the user's balance is sufficient."""
    from app.models import User, BalanceTransaction, get_connection

    recovered = []
    conn = get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        rows = conn.execute(
            """SELECT * FROM orders
               WHERE user_id = ? AND payment_status = 'paid'
                 AND status = 'awaiting_balance'
               ORDER BY created_at ASC""",
            (user_id,),
        ).fetchall()

        for row in rows:
            order = dict(row)
            word_count = int(order.get('word_count') or 0)
            balance_after = User.deduct_balance(conn, user_id, word_count)
            if balance_after is None:
                break

            BalanceTransaction.create(
                conn, user_id, 'rewrite_consumption', -word_count,
                balance_after, order_id=order['order_id'],
                description='补足余额后改写任务扣费',
            )
            updated = conn.execute(
                """UPDATE orders
                   SET status = 'processing', balance_after = ?
                   WHERE order_id = ? AND payment_status = 'paid'
                     AND status = 'awaiting_balance'""",
                (balance_after, order['order_id']),
            )
            if updated.rowcount != 1:
                raise RuntimeError(
                    f"Failed to claim awaiting-balance order {order['order_id']}"
                )
            recovered.append(order)

        conn.commit()
    except Exception:
        conn.rollback()
        logging.exception(
            "Failed to recover awaiting-balance orders for user %s", user_id
        )
        return []
    finally:
        conn.close()

    for order in recovered:
        mode = order.get('mode') or 'median'
        if mode not in ('low', 'median', 'high'):
            mode = 'low' if mode in ('paragraph', 'academic') else 'median'
        submit_rewrite_task(
            order['order_id'],
            order['original_text'],
            mode,
            _load_paragraphs(order),
        )
        logging.info("Recovered awaiting-balance order %s", order['order_id'])

    return [order['order_id'] for order in recovered]


def recover_processing_orders():
    """
    Scan for orders stuck in 'processing' status and re-trigger rewrite.
    This handles the case where the server restarted while a rewrite was running.
    Runs in its own thread (called from create_app).
    """
    try:
        from app.models import get_connection
        conn = get_connection()
        try:
            cursor = conn.execute("SELECT * FROM orders WHERE status = 'processing'")
            stuck_orders = [dict(row) for row in cursor.fetchall()]
            awaiting_user_ids = [
                row['user_id'] for row in conn.execute(
                    """SELECT DISTINCT user_id FROM orders
                       WHERE payment_status = 'paid'
                         AND status = 'awaiting_balance'"""
                ).fetchall()
            ]
        finally:
            conn.close()

        for order in stuck_orders:
            order_id = order['order_id']
            mode = order.get('mode', 'paragraph')
            text = order.get('original_text', '')
            if not text:
                continue
            paragraphs = _load_paragraphs(order)
            logging.warning(f"Recovering stuck processing order: {order_id}")
            submit_rewrite_task(order_id, text, mode, paragraphs)

        for user_id in awaiting_user_ids:
            recover_awaiting_balance_orders(user_id)
    except Exception:
        logging.exception("Failed to recover processing orders on startup")
