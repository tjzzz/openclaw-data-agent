"""Shared utility functions for AI Humanizer, organized by domain.

Sub-modules:
    - db:               database connection & order-id generation
    - auth_helpers:     login decorator
    - analysis_helpers: AI-analysis result helpers (risk level / suggestions)
    - file_output:      downloadable file generation
    - tasks:            background payment & rewrite orchestration
    - segmenter:        paragraph segmentation / structure protection

This package re-exports all public functions so existing callers
using ``from app.helpers import X`` keep working unchanged.
"""

from app.helpers.db import generate_order_id, get_db, close_db
from app.helpers.auth_helpers import login_required
from app.helpers.analysis_helpers import derive_risk_level
from app.helpers.file_output import generate_docx, generate_file_response
from app.helpers.tasks import (
    do_background_rewrite,
    process_payment_success,
    submit_rewrite_task,
    recover_awaiting_balance_orders,
    recover_processing_orders,
    rewrite_and_analyze,
    _load_paragraphs,
)

__all__ = [
    "generate_order_id",
    "get_db",
    "close_db",
    "login_required",
    "derive_risk_level",
    "generate_docx",
    "generate_file_response",
    "do_background_rewrite",
    "process_payment_success",
    "submit_rewrite_task",
    "recover_awaiting_balance_orders",
    "recover_processing_orders",
    "rewrite_and_analyze",
    "_load_paragraphs",
]
