"""Generate a format-preserving DOCX by writing text into a source copy."""

import json
import logging
import os
from copy import deepcopy
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def _safe_file_path(folder, file_key):
    if not file_key or os.path.basename(file_key) != file_key:
        raise ValueError('Invalid document file key')
    return os.path.join(folder, file_key)


def _replace_paragraph_text(paragraph_element, rewritten_text):
    """Redistribute text across existing runs while preserving run properties."""
    from docx.oxml.ns import qn

    text_nodes = list(paragraph_element.iter(qn('w:t')))
    if not text_nodes:
        return False

    original_lengths = [len(node.text or '') for node in text_nodes]
    total_original = sum(original_lengths)
    if total_original <= 0:
        text_nodes[0].text = rewritten_text
        return True

    cursor = 0
    cumulative = 0
    total_new = len(rewritten_text)
    for index, node in enumerate(text_nodes):
        if index == len(text_nodes) - 1:
            node.text = rewritten_text[cursor:]
            break
        cumulative += original_lengths[index]
        boundary = round(total_new * cumulative / total_original)
        node.text = rewritten_text[cursor:boundary]
        cursor = boundary
    return True


def _replace_paragraph_range(body_children, body_indexes, rewritten_text):
    """Replace plain source paragraphs with any number of output paragraphs."""
    source_elements = []
    for body_index in body_indexes:
        if body_index < 0 or body_index >= len(body_children):
            raise ValueError(f'DOCX body index out of range: {body_index}')
        child = body_children[body_index]
        if child.tag.split('}')[-1] != 'p':
            raise ValueError(f'DOCX node is not a paragraph: {body_index}')
        source_elements.append(child)
    if not source_elements:
        return 0

    output_paragraphs = [
        value.strip() for value in rewritten_text.split('\n\n') if value.strip()
    ] or ['']
    shared = min(len(source_elements), len(output_paragraphs))
    for index in range(shared):
        _replace_paragraph_text(source_elements[index], output_paragraphs[index])

    parent = source_elements[0].getparent()
    for element in source_elements[len(output_paragraphs):]:
        parent.remove(element)

    anchor = source_elements[min(len(source_elements), len(output_paragraphs)) - 1]
    for text in output_paragraphs[len(source_elements):]:
        clone = deepcopy(source_elements[-1])
        _replace_paragraph_text(clone, text)
        anchor.addnext(clone)
        anchor = clone
    return len(output_paragraphs)


def generate_order_docx(order_id):
    """Create one output DOCX for an order without blocking rewrite display."""
    from config import PROJ_ROOT
    from docx import Document
    from app.models import get_connection, Order

    conn = get_connection()
    try:
        order = Order.get_by_order_id(conn, order_id)
        if not order or not order.get('source_file_key'):
            return False
        conn.execute(
            "UPDATE orders SET document_status = 'generating', document_error = NULL, "
            "document_updated_at = ? "
            "WHERE order_id = ?",
            (datetime.now(timezone.utc).isoformat(), order_id)
        )
        conn.commit()

        source_path = _safe_file_path(
            os.path.join(PROJ_ROOT, 'instance', 'source_docs'),
            order['source_file_key']
        )
        output_key = f'{order_id}.docx'
        output_path = _safe_file_path(
            os.path.join(PROJ_ROOT, 'instance', 'output_docs'), output_key
        )

        raw_mapping = order.get('rewritten_paragraphs')
        structured = json.loads(raw_mapping) if raw_mapping else []
        replacements = []
        for item in structured:
            if not item.get('was_rewritten') or item.get('source_format') != 'docx':
                continue
            indexes = item.get('source_body_indexes')
            if not indexes and item.get('body_index') is not None:
                indexes = [item['body_index']]
            if indexes:
                replacement = dict(item)
                replacement['source_body_indexes'] = indexes
                replacements.append(replacement)

        document = Document(source_path)
        body_children = list(document.element.body.iterchildren())
        replaced = 0
        # Work backwards so removing/inserting earlier paragraphs cannot affect
        # any source references still waiting to be processed.
        replacements.sort(
            key=lambda item: min(item['source_body_indexes']), reverse=True
        )
        for item in replacements:
            replaced += _replace_paragraph_range(
                body_children, item['source_body_indexes'], item['text']
            )

        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        document.save(output_path)
        conn.execute(
            """UPDATE orders
               SET document_status = 'ready', output_file_key = ?, document_error = NULL,
                   document_updated_at = ?
               WHERE order_id = ?""",
            (output_key, datetime.now(timezone.utc).isoformat(), order_id)
        )
        conn.commit()
        logger.info('Generated DOCX for order=%s replacements=%d', order_id, replaced)
        return True
    except Exception as exc:
        conn.rollback()
        conn.execute(
            "UPDATE orders SET document_status = 'failed', document_error = ?, "
            "document_updated_at = ? "
            "WHERE order_id = ?",
            (str(exc)[:500], datetime.now(timezone.utc).isoformat(), order_id)
        )
        conn.commit()
        logger.exception('Failed to generate DOCX for order=%s', order_id)
        return False
    finally:
        conn.close()
