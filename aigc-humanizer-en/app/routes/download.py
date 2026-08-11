"""
Download route — download rewritten text in various formats.
"""

import json
import logging
import os
from datetime import datetime, timedelta, timezone

from flask import Blueprint, request, jsonify, session, current_app, send_file
from app.helpers import get_db, generate_file_response

logger = logging.getLogger(__name__)

download_bp = Blueprint('download', __name__)


def _document_generation_is_stale(order, timeout_minutes=5):
    """Treat legacy or timed-out queued/generating rows as recoverable."""
    updated_at = (
        order.get('document_updated_at') or
        order.get('progress_updated_at') or
        order.get('created_at')
    )
    if not updated_at:
        return True
    try:
        updated = datetime.fromisoformat(updated_at)
        if updated.tzinfo is None:
            updated = updated.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return True
    return datetime.now(timezone.utc) - updated > timedelta(minutes=timeout_minutes)


@download_bp.route('/api/download/<order_id>')
def api_download(order_id):
    """
    Download rewritten text in the specified format.
    Requires login (or the order must belong to the current user's session).
    Query params: ?format=docx|pdf|txt|md (default: original_format)
    """
    from app.models import Order

    user_id = session.get('user_id')
    conn = get_db()

    order = Order.get_by_order_id(conn, order_id)
    if not order:
        logger.warning("Download requested for non-existent order: %s (user_id=%s)", order_id, user_id)
        return jsonify({"error": "订单不存在"}), 404

    if user_id and order['user_id'] != user_id:
        logger.warning("Download denied: user %s attempted to access order %s owned by %s",
                        user_id, order_id, order['user_id'])
        return jsonify({"error": "无权访问该订单"}), 403

    if not user_id:
        last = session.get('last_rewritten', {})
        if last.get('order_id') != order_id:
            logger.warning("Download denied: unauthenticated session without matching last_rewritten (order=%s)", order_id)
            return jsonify({"error": "请登录后下载"}), 401

    req_format = request.args.get('format', order.get('original_format', 'txt'))
    if req_format not in ['docx', 'pdf', 'txt', 'md']:
        logger.info("Unsupported download format '%s' for order %s, falling back to '%s'",
                     req_format, order_id, order.get('original_format', 'txt'))
        req_format = order.get('original_format', 'txt')

    rewritten_text = order['rewritten_text']
    filename = order.get('original_filename', 'humanized')

    # DOCX sources are rewritten into a preserved copy after text completion.
    source_file_key = order.get('source_file_key')
    source_path = None
    if source_file_key:
        source_path = os.path.join(
            current_app.config['SOURCE_DOCS_FOLDER'],
            os.path.basename(source_file_key),
        )
    has_source_copy = bool(source_path and os.path.isfile(source_path))

    if (req_format == 'docx' and order.get('original_format') == 'docx' and
            source_file_key):
        document_status = order.get('document_status') or 'pending'
        output_key = order.get('output_file_key')
        if document_status == 'ready' and output_key:
            output_path = os.path.join(
                current_app.config['OUTPUT_DOCS_FOLDER'], os.path.basename(output_key)
            )
            if os.path.isfile(output_path):
                base_name = os.path.splitext(filename or 'humanized')[0]
                return send_file(
                    output_path,
                    mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                    as_attachment=True,
                    download_name=f'{base_name}_humanized.docx'
                )
            document_status = 'failed'

        if has_source_copy:
            if (document_status in ('pending', 'generating') and
                    _document_generation_is_stale(order)):
                logger.warning(
                    "Restarting stale Word generation for order %s (status=%s)",
                    order_id, document_status,
                )
                document_status = 'failed'

            if document_status == 'failed':
                from app.extensions import document_executor
                from app.helpers.docx_renderer import generate_order_docx
                conn.execute(
                    "UPDATE orders SET document_status = 'pending', document_updated_at = ? "
                    "WHERE order_id = ?",
                    (datetime.now(timezone.utc).isoformat(), order_id)
                )
                conn.commit()
                document_executor.submit(generate_order_docx, order_id)

            return jsonify({
                "status": "generating",
                "message": "Word 文档正在生成，请稍候",
                "retry_after": 1
            }), 202

        logger.warning(
            "Source DOCX missing for order %s; generating fallback from database",
            order_id,
        )

    # 读取改写后的结构化段落（含标题级别），供 docx 重建格式
    rewritten_paragraphs = None
    raw_paras = order.get('rewritten_paragraphs')
    if raw_paras:
        try:
            parsed = json.loads(raw_paras)
            if isinstance(parsed, list):
                rewritten_paragraphs = parsed
        except (ValueError, TypeError):
            logger.warning("Failed to parse rewritten_paragraphs for order %s", order_id)

    try:
        logger.info("Download order=%s, user=%s, format=%s, filename=%s (words=%s, structured=%s)",
                    order_id, user_id, req_format, filename,
                    len(rewritten_text.split()) if rewritten_text else 0,
                    bool(rewritten_paragraphs))
        return generate_file_response(
            rewritten_text, req_format, filename, paragraphs=rewritten_paragraphs
        )
    except Exception:
        logger.exception("Failed to generate download file for order %s (format=%s)", order_id, req_format)
        return jsonify({"error": "文件生成失败，请稍后重试"}), 500
