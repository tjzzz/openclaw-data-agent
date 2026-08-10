#!/usr/bin/env python3
"""
Humanizer adapter — abstracts the text humanization engine.
Uses the Adapter pattern so the app can switch between rule-based and API-driven engines.
"""

import time
import re
import logging

from config import AI_TEXT_HUMANIZER_EMAIL as _CFG_EMAIL, AI_TEXT_HUMANIZER_PASSWORD as _CFG_PASSWORD
from abc import ABC, abstractmethod
from urllib import request as urllib_request
from urllib.parse import urlencode

from app.helpers.segmenter import segment as segment_paragraphs

logger = logging.getLogger(__name__)


def _cfg(name, default):
    """从 config 安全读取配置项（本地 config.py 可能缺新配置时用默认值）。"""
    import config as _config
    return getattr(_config, name, default)


def _heading_level_from_style(style):
    """从样式名解析标题级别：Heading 1->1, Title->0, toc->None；非标题返回 None。"""
    if not style:
        return None
    sn = style.lower().strip()
    m = re.search(r'heading\s*(\d+)', sn)
    if m:
        return int(m.group(1))
    if sn == 'title':
        return 0
    return None


class HumanizerAdapter(ABC):
    """Interface for text humanization adapters."""

    @abstractmethod
    def humanize(self, text, mode='low', paragraphs=None):
        """
        Humanize the given text.
        Args:
            text: The text to humanize.
            mode: 'low'/'median'/'high' — controls segmentation granularity.
            paragraphs: Optional ordered list[dict] with paragraph structure,
                        used for structure protection.
        Returns:
            Humanized text string.
        """
        pass

    @abstractmethod
    def humanize_structured(self, text, mode='low', paragraphs=None):
        """
        Humanize and return (text_str, structured_paragraphs).

        structured_paragraphs: list[dict] 每个元素含
            {'text', 'is_heading', 'heading_level', 'style'}，
            用于下载 Word 时按标题级别重建格式。
        """
        pass

    def _humanize_segmented(self, mode, paragraphs, block_rewriter):
        """
        按段落结构分段改写，保护标题/表格/短段，保持原文顺序。

        通用骨架，供各引擎复用。改写正文块的具体逻辑由 block_rewriter 提供：
            block_rewriter(body_text) -> str

        Args:
            mode: 分段粒度（low/median/high）
            paragraphs: 有序段落 dict 列表
            block_rewriter: 改写单个正文块的回调函数
        Returns:
            str
        """
        text, _ = self._humanize_segmented_structured(mode, paragraphs, block_rewriter)
        return text

    def _humanize_segmented_structured(self, mode, paragraphs, block_rewriter):
        """
        分段改写并返回结构化结果：(text_str, structured_paragraphs)。

        structured_paragraphs 为 list[dict]：
            {'text': str, 'heading_level': int|None, 'is_heading': bool, 'style': str|None}
        用于下载 Word 时按标题级别重建格式（Heading 1/2/3...、Title、正文）。

        与 _humanize_segmented 走同一套 segmenter/结构保护逻辑，
        仅额外记录每个输出段落的结构标记：
            - protected/table 段：保留原始段落结构（标题级别从原始 style 解析）
            - rewrite 段：改写块可能含多段，按 \\n\\n 拆分，均为正文（heading_level=None）
        """
        tasks = segment_paragraphs(
            paragraphs,
            mode=mode,
            median_paras=_cfg('REWRITE_MEDIAN_PARAS', 3),
            high_paras=_cfg('REWRITE_HIGH_PARAS', 5),
            max_words=_cfg('REWRITE_MAX_WORDS', 2000),
        )

        parts = []
        structured = []
        rewrite_tasks = [t for t in tasks if t["type"] == "rewrite"]
        if rewrite_tasks:
            logger.info(
                f"Segmented rewrite (mode={mode}): {len(rewrite_tasks)} rewrite blocks, "
                f"{len(tasks) - len(rewrite_tasks)} protected/table elements"
            )

        # 频控：改写请求数超过阈值时，每次请求后 sleep，防止超 60 次/分钟
        rate_limit_max = _cfg('RATE_LIMIT_MAX_REQUESTS', 30)
        rate_limit_sleep = _cfg('RATE_LIMIT_SLEEP', 1.0)
        rate_limit_enabled = len(rewrite_tasks) > rate_limit_max

        for i, task in enumerate(tasks):
            if task["type"] == "rewrite":
                block_text = task["text"]
                rewritten = block_rewriter(block_text)
                parts.append(rewritten)
                # 频控：改写请求间 sleep（除最后一次外）
                if rate_limit_enabled and i < len(tasks) - 1:
                    time.sleep(rate_limit_sleep)
                # 改写块内所有段落均为正文，heading_level=None
                for chunk in rewritten.split('\n\n'):
                    if chunk.strip():
                        structured.append({
                            "text": chunk.strip(),
                            "is_heading": False,
                            "heading_level": None,
                            "style": None,
                        })
            else:
                # protected / table：原样保留（table 无 text，输出占位标记）
                text = task.get("text") or ""
                parts.append(text)
                # 记录结构：从该 task 涉及的原始段落继承标题级别
                for p in task.get("paragraphs") or []:
                    if "table" in p:
                        continue
                    ptext = (p.get("text") or "").strip()
                    if not ptext:
                        continue
                    style = p.get("style")
                    level = _heading_level_from_style(style)
                    structured.append({
                        "text": ptext,
                        "is_heading": bool(level is not None or p.get("is_heading", False)),
                        "heading_level": level,
                        "style": style,
                    })

        return "\n\n".join(parts), structured


class RuleBasedHumanizer(HumanizerAdapter):
    """Rule-based humanizer wrapping the existing humanize.py module."""

    def humanize(self, text, mode=None, paragraphs=None):
        """Humanize text using deterministic rule-based transformations."""
        return self.humanize_structured(text, mode=mode, paragraphs=paragraphs)[0]

    def humanize_structured(self, text, mode=None, paragraphs=None):
        """
        Humanize text using deterministic rule-based transformations.

        返回 (text_str, structured_paragraphs)。有段落结构时按 mode 分段，
        保护标题/表格/参考文献/短段，仅对正文块做规则改写。
        无段落结构时对整篇改写（structured 为空列表）。
        mode 缺省时取 config.REWRITE_MODE_DEFAULT（默认 median）。
        """
        if mode is None:
            mode = _cfg('REWRITE_MODE_DEFAULT', 'median')
        from app.humanize import humanize_text

        if paragraphs is not None:
            def block_rewriter(body_text):
                # 规则改写无字级上限，整块一次改写（兼容 academic_mode 由模式推断）
                return humanize_text(body_text, academic_mode=(mode == 'academic'))

            return self._humanize_segmented_structured(mode, paragraphs, block_rewriter)

        humanized = humanize_text(text, academic_mode=(mode == 'academic'))
        return humanized, []


class ApiHumanizer(HumanizerAdapter):
    """
    API-based humanizer calling ai-text-humanizer.com.

    Calls https://ai-text-humanizer.com/api.php with email/password auth.
    Supports automatic chunking for texts > 2000 words, rate limiting, and retries.
    """

    API_URL = "https://ai-text-humanizer.com/api.php"
    MAX_WORDS_PER_REQUEST = 2000
    RATE_LIMIT_DELAY = 1.2
    MAX_RETRIES = 3
    RETRY_DELAY = 2.0
    REQUEST_TIMEOUT = 120

    def __init__(self, email=None, password=None):
        """
        Initialize the API humanizer.

        Args:
            email: ai-text-humanizer.com account email (falls back to env var)
            password: ai-text-humanizer.com account password (falls back to env var)
        """
        self.email = email or _CFG_EMAIL
        self.password = password or _CFG_PASSWORD

        if not self.email or not self.password:
            logger.warning(
                "AI_TEXT_HUMANIZER_EMAIL/ PASSWORD not configured. "
                "ApiHumanizer will raise an error if used."
            )

    def humanize(self, text, mode=None, paragraphs=None):
        """
        Humanize text via ai-text-humanizer.com API.

        When ``paragraphs`` (an ORDERED list of paragraph dicts from
        extract_text) is provided, the document is segmented by ``mode`` and
        only body paragraphs are sent to the API. Headings / tables / short
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

    def humanize_structured(self, text, mode=None, paragraphs=None):
        """
        Humanize text via ai-text-humanizer.com API, returning structured output.

        返回 (text_str, structured_paragraphs)。有段落结构时按 mode 分段改写，
        保护标题/表格/短段，并记录每个输出段落的标题级别供下载 Word 重建格式。
        无段落结构时对整篇改写（structured 为空列表）。mode 缺省取默认。
        """
        if mode is None:
            mode = _cfg('REWRITE_MODE_DEFAULT', 'median')
        if not self.email or not self.password:
            raise RuntimeError(
                "ai-text-humanizer.com credentials not configured. "
                "Set AI_TEXT_HUMANIZER_EMAIL and AI_TEXT_HUMANIZER_PASSWORD in config.py"
            )

        # 有段落结构时：按 mode 分段改写，保护标题/表格/短段
        if paragraphs is not None:
            return self._humanize_segmented_structured(mode, paragraphs, self._process_large_text)

        word_count = self._count_words(text)

        if word_count <= self.MAX_WORDS_PER_REQUEST:
            success, result = self._call_api(text)
            if not success:
                raise RuntimeError(f"API humanize failed: {result}")
            return result, []
        else:
            return self._process_large_text(text), []

    def _call_api(self, text):
        """
        Single API call to ai-text-humanizer.com.

        Returns:
            (success: bool, result: str)
        """
        for attempt in range(self.MAX_RETRIES):
            try:
                data = urlencode({
                    'email': self.email,
                    'pw': self.password,
                    'text': text
                }).encode('utf-8')

                req = urllib_request.Request(self.API_URL, data=data, method='POST')
                req.add_header('Content-Type', 'application/x-www-form-urlencoded;charset=utf-8')

                with urllib_request.urlopen(req, timeout=self.REQUEST_TIMEOUT) as resp:
                    result = resp.read().decode('utf-8', errors='replace').strip()

                if not result:
                    return False, "API returned empty response"

                # Check for common error indicators in short responses
                error_indicators = ['error', 'Error', 'ERROR', 'failed', 'Failed', 'invalid', 'Invalid']
                if len(result) < 500 and any(ind in result[:100] for ind in error_indicators):
                    return False, f"API error: {result}"

                return True, result

            except Exception as e:
                err_msg = str(e)
                if attempt < self.MAX_RETRIES - 1:
                    logger.warning(f"API call attempt {attempt + 1} failed: {err_msg}, retrying...")
                    time.sleep(self.RETRY_DELAY)
                else:
                    return False, f"API call failed after {self.MAX_RETRIES} attempts: {err_msg}"

        return False, "Max retries exceeded"

    def _process_large_text(self, text):
        """
        Split text into chunks and process each via API.

        Args:
            text: Full text to humanize.

        Returns:
            Humanized text string.

        Raises:
            RuntimeError: If any chunk fails.
        """
        chunks = self._split_text_smartly(text)
        total = len(chunks)
        logger.info(f"Text too large ({self._count_words(text)} words), splitting into {total} chunks")

        results = []
        for i, chunk in enumerate(chunks, 1):
            chunk_words = self._count_words(chunk)
            logger.info(f"Processing chunk {i}/{total} ({chunk_words} words)...")

            success, result = self._call_api(chunk)
            if not success:
                raise RuntimeError(f"Chunk {i}/{total} failed: {result}")

            results.append(result)

            if i < total:
                time.sleep(self.RATE_LIMIT_DELAY)

        return "\n\n".join(results)

    def _split_text_smartly(self, text):
        """
        Split text into chunks respecting the word limit.

        Args:
            text: Full text to split.

        Returns:
            List of text chunks, each within MAX_WORDS_PER_REQUEST.
        """
        chunks = []
        current_chunk = ""
        current_words = 0
        paragraphs = text.split('\n\n')

        for para in paragraphs:
            para_words = self._count_words(para)

            if para_words > self.MAX_WORDS_PER_REQUEST:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                    current_chunk = ""
                    current_words = 0

                # Split by sentences for oversized paragraphs
                sentences = para.replace('. ', '. \n').replace('! ', '! \n').replace('? ', '? \n').split('\n')
                for sentence in sentences:
                    sentence_words = self._count_words(sentence)
                    if current_words + sentence_words <= self.MAX_WORDS_PER_REQUEST:
                        current_chunk += sentence + " "
                        current_words += sentence_words
                    else:
                        if current_chunk:
                            chunks.append(current_chunk.strip())
                        current_chunk = sentence + " "
                        current_words = sentence_words
            else:
                if current_words + para_words <= self.MAX_WORDS_PER_REQUEST:
                    current_chunk += para + "\n\n"
                    current_words += para_words
                else:
                    if current_chunk:
                        chunks.append(current_chunk.strip())
                    current_chunk = para + "\n\n"
                    current_words = para_words

        if current_chunk:
            chunks.append(current_chunk.strip())

        return chunks

    @staticmethod
    def _count_words(text):
        """Count words in text."""
        return len(text.split())