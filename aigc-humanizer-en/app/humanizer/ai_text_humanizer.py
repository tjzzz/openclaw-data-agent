"""ai-text-humanizer.com implementation."""

import logging
import threading
import time
from urllib import request as urllib_request
from urllib.parse import urlencode

from config import AI_TEXT_HUMANIZER_EMAIL as _CFG_EMAIL
from config import AI_TEXT_HUMANIZER_PASSWORD as _CFG_PASSWORD

from app.humanizer.adapter import HumanizerAdapter, _cfg

logger = logging.getLogger("app.humanizer.ai_text_humanizer")


class AITextHumanizer(HumanizerAdapter):
    """
    API-based humanizer calling ai-text-humanizer.com.

    Calls https://ai-text-humanizer.com/api.php with email/password auth.
    Supports automatic chunking for texts > 2000 words, rate limiting, and retries.
    """

    API_URL = "https://ai-text-humanizer.com/api.php"
    MAX_WORDS_PER_REQUEST = 2000
    RATE_LIMIT_DELAY = 1.2
    MAX_RETRIES = 2
    RETRY_DELAY = 2.0
    REQUEST_TIMEOUT = 30
    CIRCUIT_FAILURE_THRESHOLD = 3
    CIRCUIT_COOLDOWN_SECONDS = 60
    ERROR_RESPONSES = {"RESULT_TOO_LONG"}
    # 日志里的 backend 标识；Mock 子类会覆盖为专用标识。
    backend_label = "ai_text_humanizer"

    def __init__(self, email=None, password=None):
        """
        Initialize the API humanizer.

        Args:
            email: ai-text-humanizer.com account email (falls back to env var)
            password: ai-text-humanizer.com account password (falls back to env var)
        """
        self.email = email or _CFG_EMAIL
        self.password = password or _CFG_PASSWORD
        self._circuit_lock = threading.Lock()
        self._consecutive_failures = 0
        self._circuit_opened_until = 0.0

        if not self.email or not self.password:
            logger.warning(
                "AI_TEXT_HUMANIZER_EMAIL/ PASSWORD not configured. "
                "AITextHumanizer will raise an error if used."
            )

    def _circuit_is_open(self):
        with self._circuit_lock:
            remaining = self._circuit_opened_until - time.monotonic()
            if remaining <= 0:
                return False, 0
            return True, remaining

    def _record_api_success(self):
        with self._circuit_lock:
            self._consecutive_failures = 0
            self._circuit_opened_until = 0.0

    def _record_api_failure(self):
        with self._circuit_lock:
            self._consecutive_failures += 1
            if self._consecutive_failures >= self.CIRCUIT_FAILURE_THRESHOLD:
                self._circuit_opened_until = (
                    time.monotonic() + self.CIRCUIT_COOLDOWN_SECONDS
                )
                return True
            return False

    def humanize(self, text, mode=None, paragraphs=None):
        """
        Humanize text via ai-text-humanizer.com API.

        When ``paragraphs`` (an ORDERED list of paragraph dicts from
        extract_text) is provided, the document is segmented by ``mode`` and
        only body paragraphs are sent to the API. Headings / references / short
        paragraphs are kept as-is and the output preserves document structure.

        ``mode`` controls the segmentation granularity:
            - low    : send each body paragraph individually (compat: paragraph)
            - median : aggregate consecutive body paragraphs (default max 3)
            - high   : aggregate consecutive body paragraphs (default max 5)
            - (aggregation limit configurable; =1 equals low)

        Without ``paragraphs``, falls back to processing the whole text
        (original behavior). mode 缺省时取 config.REWRITE_MODE_DEFAULT。

        Args:
            text: The text to humanize.
            mode: Segmentation granularity (low/median/high).
            paragraphs: Optional ORDERED list[dict] with paragraph structure.

        Returns:
            Humanized text string.

        Raises:
            RuntimeError: If credentials are missing or API calls fail.
        """
        return self.humanize_structured(text, mode=mode, paragraphs=paragraphs)[0]

    def humanize_structured(self, text, mode=None, paragraphs=None, progress_cb=None):
        """
        Humanize text via ai-text-humanizer.com API, returning structured output.

        返回 (text_str, structured_paragraphs)。有段落结构时按 mode 分段改写，
        保护标题、参考文献和短段，并记录输出结构供下载 Word 回填。
        无段落结构时对整篇改写（structured 为空列表）。mode 缺省取默认。

        Args:
            progress_cb: 可选进度回调，透传给 _humanize_segmented_structured。
        """
        if mode is None:
            mode = _cfg('REWRITE_MODE_DEFAULT', 'median')
        if not self.email or not self.password:
            raise RuntimeError(
                "ai-text-humanizer.com credentials not configured. "
                "Set AI_TEXT_HUMANIZER_EMAIL and AI_TEXT_HUMANIZER_PASSWORD in config.py"
            )

        # 有段落结构时按 mode 分段改写。
        if paragraphs is not None:
            return self._humanize_segmented_structured(
                mode, paragraphs, self._rewrite_with_api_chunking, progress_cb=progress_cb)

        word_count = self._count_words(text)

        if word_count <= self.MAX_WORDS_PER_REQUEST:
            success, result = self._call_api(text)
            if not success:
                raise RuntimeError(f"API humanize failed: {result}")
            return result, []
        else:
            return self._rewrite_with_api_chunking(text), []

    def _call_api(self, text):
        """
        Single API call to ai-text-humanizer.com.

        Returns:
            (success: bool, result: str)
        """
        circuit_open, remaining = self._circuit_is_open()
        if circuit_open:
            logger.error(
                "rewrite stage=rewrite backend=%s action=circuit_open retry_after=%.0fs",
                self.backend_label, remaining,
            )
            return False, "Upstream humanizer is temporarily unavailable"

        for attempt in range(self.MAX_RETRIES):
            start = time.time()
            try:
                data = urlencode({
                    'email': self.email,
                    'pw': self.password,
                    'text': text
                }).encode('utf-8')

                req = urllib_request.Request(self.API_URL, data=data, method='POST')
                req.add_header('Content-Type', 'application/x-www-form-urlencoded;charset=utf-8')

                with urllib_request.urlopen(req, timeout=self.REQUEST_TIMEOUT) as resp:
                    status_code = resp.status
                    result = resp.read().decode('utf-8', errors='replace').strip()

                if status_code != 200:
                    raise RuntimeError(f"API returned HTTP {status_code}")
                if not result:
                    raise RuntimeError("API returned empty response")
                if result.upper() in self.ERROR_RESPONSES:
                    logger.warning(
                        "rewrite stage=rewrite backend=%s action=business_reject status=%s words=%d",
                        self.backend_label, result, self._count_words(text),
                    )
                    return False, f"API rejected this text block: {result}"

                self._record_api_success()
                logger.info(
                    "rewrite stage=rewrite backend=%s action=call_ok words=%d out_chars=%d elapsed=%.0fms",
                    self.backend_label, self._count_words(text), len(result), (time.time() - start) * 1000,
                )
                return True, result

            except Exception as e:
                err_msg = str(e)
                circuit_opened = self._record_api_failure()
                if circuit_opened:
                    logger.error(
                        "rewrite stage=rewrite backend=%s action=circuit_trip failures=%d cooldown=%ds err=%s",
                        self.backend_label, self.CIRCUIT_FAILURE_THRESHOLD,
                        self.CIRCUIT_COOLDOWN_SECONDS, err_msg,
                    )
                    return False, "Upstream humanizer is temporarily unavailable"
                if attempt < self.MAX_RETRIES - 1:
                    logger.warning(
                        "rewrite stage=rewrite backend=%s action=retry attempt=%d elapsed=%.0fms err=%s",
                        self.backend_label, attempt + 1, (time.time() - start) * 1000, err_msg,
                    )
                    time.sleep(self.RETRY_DELAY)
                else:
                    return False, f"API call failed after {self.MAX_RETRIES} attempts: {err_msg}"

        return False, "Max retries exceeded"

    def _rewrite_with_api_chunking(self, text):
        return self._rewrite_with_chunking(
            text,
            self._rewrite_api_block,
            max_words=self.MAX_WORDS_PER_REQUEST,
            request_delay=self.RATE_LIMIT_DELAY,
            backend_label=self.backend_label,
            use_global_limit=True,
        )

    def _rewrite_api_block(self, text):
        success, result = self._call_api(text)
        if not success:
            raise RuntimeError(f"API humanize failed: {result}")
        return result
