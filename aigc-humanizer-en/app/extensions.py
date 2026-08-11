"""
Shared extensions and adapters — initialized during create_app().
These module-level objects are imported by routes and helpers.
"""

import logging
from concurrent.futures import ThreadPoolExecutor
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect

csrf = CSRFProtect()
limiter = Limiter(key_func=get_remote_address, default_limits=[], storage_uri="memory://")
rewrite_executor = ThreadPoolExecutor(max_workers=5)
document_executor = ThreadPoolExecutor(max_workers=2)

# Adapters — set during create_app()
payment_adapter = None
humanizer_adapter = None
ai_detector = None          # analyze_text(text) -> dict


def set_adapters(payment, humanizer):
    """Set payment and humanizer adapters (called once during app creation)."""
    global payment_adapter, humanizer_adapter
    payment_adapter = payment
    humanizer_adapter = humanizer
    logging.info(
        f"Adapters initialized: payment={type(payment).__name__}, "
        f"humanizer={type(humanizer).__name__}"
    )


def set_ai_detector(detect_fn):
    """Set AI detector function (called once during app creation)."""
    global ai_detector
    ai_detector = detect_fn
    logging.info(
        f"AI detector initialized: {getattr(detect_fn, '__name__', '?')}"
    )
