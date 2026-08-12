#!/usr/bin/env python3
"""Shared humanizer interface and segmented rewrite orchestration."""

import time
import re
import logging
import threading

from abc import ABC, abstractmethod

from app.helpers.segmenter import segment as segment_paragraphs

logger = logging.getLogger("app.humanizer")

_UPSTREAM_SEMAPHORE = None
_UPSTREAM_SEMAPHORE_SIZE = None
_UPSTREAM_SEMAPHORE_LOCK = threading.Lock()
_UPSTREAM_RATE_LOCK = threading.Lock()
_UPSTREAM_LAST_REQUEST_AT = 0.0


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
        按段落结构分段改写，保护标题、参考文献和短段，保持原文顺序。

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

    def _humanize_segmented_structured(self, mode, paragraphs, block_rewriter, progress_cb=None):
        """
        分段改写并返回结构化结果：(text_str, structured_paragraphs)。

        structured_paragraphs 为 list[dict]：
            {'text': str, 'heading_level': int|None, 'is_heading': bool, 'style': str|None}
        用于下载 Word 时按标题级别重建格式（Heading 1/2/3...、Title、正文）。

        与 _humanize_segmented 走同一套 segmenter/结构保护逻辑，
        仅额外记录每个输出段落的结构标记：
            - protected 段：保留原始段落结构（标题级别从原始 style 解析）
            - rewrite 段：一个聚合结果映射到一个或多个源 node

        Args:
            progress_cb: 可选进度回调 progress_cb(stage, block, total_blocks)，
                每个 rewrite 块完成后调用，用于前端展示"改写 x/total"真实进度。
        """
        _start = time.time()
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
                "rewrite stage=rewrite backend=%s action=segment mode=%s blocks=%d protected=%d",
                _cfg('HUMANIZER_ADAPTER', 'rule_based'), mode,
                len(rewrite_tasks), len(tasks) - len(rewrite_tasks),
            )

        # 频控：改写请求数超过阈值时，每次请求后 sleep，防止超 60 次/分钟
        rate_limit_max = _cfg('RATE_LIMIT_MAX_REQUESTS', 30)
        rate_limit_sleep = _cfg('RATE_LIMIT_SLEEP', 1.0)
        rate_limit_enabled = len(rewrite_tasks) > rate_limit_max

        rewrite_idx = 0
        for i, task in enumerate(tasks):
            if task["type"] == "rewrite":
                block_text = task["text"]
                rewritten = block_rewriter(block_text)
                source_paragraphs = task.get("paragraphs") or []
                parts.append(rewritten)
                # 进度回调：每完成一个改写块上报（block 从 1 开始）
                if progress_cb:
                    rewrite_idx += 1
                    progress_cb(stage="rewrite", block=rewrite_idx,
                                total_blocks=len(rewrite_tasks))
                # 频控：改写请求间 sleep（除最后一次外）
                if rate_limit_enabled and i < len(tasks) - 1:
                    time.sleep(rate_limit_sleep)
                item = {
                    "text": rewritten.strip(),
                    "was_rewritten": True,
                    "is_heading": False,
                    "heading_level": None,
                    "style": None,
                    "block_id": task.get("block_id"),
                    "source_node_ids": task.get("source_node_ids", []),
                    "source_body_indexes": task.get("source_body_indexes", []),
                }
                if source_paragraphs:
                    item["source_format"] = source_paragraphs[0].get("source_format")
                structured.append(item)
            else:
                # protected：原样保留
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
                    item = {
                        "text": ptext,
                        "was_rewritten": False,
                        "is_heading": bool(level is not None or p.get("is_heading", False)),
                        "heading_level": level,
                        "style": style,
                    }
                    for key in ("node_id", "content_index", "paragraph_index",
                                "source_format", "body_index"):
                        if key in p:
                            item[key] = p[key]
                    structured.append(item)

        logger.info(
            "rewrite stage=rewrite backend=%s action=all_done blocks=%d protected=%d elapsed=%.0fms",
            _cfg('HUMANIZER_ADAPTER', 'rule_based'), len(rewrite_tasks),
            len(tasks) - len(rewrite_tasks), (time.time() - _start) * 1000,
        )
        return "\n\n".join(parts), structured

    def _rewrite_with_chunking(self, text, block_rewriter, max_words=None,
                               request_delay=0, backend_label=None,
                               use_global_limit=False):
        """按上游单次词数限制切块，并逐块调用具体改写接口。"""
        max_words = max_words or _cfg('REWRITE_MAX_WORDS', 2000)
        backend_label = backend_label or _cfg('HUMANIZER_ADAPTER', 'unknown')
        started = time.time()
        chunks = self._split_text_for_requests(text, max_words)

        if len(chunks) > 1:
            logger.info(
                "rewrite stage=rewrite backend=%s action=chunk_split words=%d chunks=%d",
                backend_label, self._count_words(text), len(chunks),
            )

        results = []
        for index, chunk in enumerate(chunks, 1):
            logger.info(
                "rewrite stage=rewrite backend=%s action=chunk_start chunk=%d/%d words=%d",
                backend_label, index, len(chunks), self._count_words(chunk),
            )
            if use_global_limit:
                results.append(self._call_with_global_limit(block_rewriter, chunk))
            else:
                results.append(block_rewriter(chunk))
            if request_delay and index < len(chunks):
                time.sleep(request_delay)

        logger.info(
            "rewrite stage=rewrite backend=%s action=done chunks=%d elapsed=%.0fms",
            backend_label, len(chunks), (time.time() - started) * 1000,
        )
        return "\n\n".join(results)

    @staticmethod
    def _call_with_global_limit(block_rewriter, chunk):
        """限制当前进程所有订单共享的上游并发数和请求启动间隔。"""
        global _UPSTREAM_SEMAPHORE, _UPSTREAM_SEMAPHORE_SIZE
        global _UPSTREAM_LAST_REQUEST_AT

        max_concurrency = max(1, int(_cfg('HUMANIZER_GLOBAL_MAX_CONCURRENCY', 2)))
        min_interval = max(0.0, float(_cfg('HUMANIZER_GLOBAL_MIN_INTERVAL', 1.0)))
        with _UPSTREAM_SEMAPHORE_LOCK:
            if (_UPSTREAM_SEMAPHORE is None or
                    _UPSTREAM_SEMAPHORE_SIZE != max_concurrency):
                _UPSTREAM_SEMAPHORE = threading.BoundedSemaphore(max_concurrency)
                _UPSTREAM_SEMAPHORE_SIZE = max_concurrency

        with _UPSTREAM_SEMAPHORE:
            with _UPSTREAM_RATE_LOCK:
                wait_seconds = min_interval - (time.monotonic() - _UPSTREAM_LAST_REQUEST_AT)
                if wait_seconds > 0:
                    time.sleep(wait_seconds)
                _UPSTREAM_LAST_REQUEST_AT = time.monotonic()
            return block_rewriter(chunk)

    @classmethod
    def _split_text_for_requests(cls, text, max_words):
        """优先按段落和句子切分，必要时按词硬切，确保每块不超上限。"""
        if not text or not text.strip():
            return []
        if cls._count_words(text) <= max_words:
            return [text.strip()]

        units = []
        for paragraph in re.split(r'\n\s*\n', text.strip()):
            if cls._count_words(paragraph) <= max_words:
                units.append(paragraph)
                continue
            sentences = re.split(r'(?<=[.!?])\s+', paragraph)
            for sentence in sentences:
                words = sentence.split()
                units.extend(
                    " ".join(words[index:index + max_words])
                    for index in range(0, len(words), max_words)
                )

        chunks = []
        current = []
        current_words = 0
        for unit in units:
            unit_words = cls._count_words(unit)
            if current and current_words + unit_words > max_words:
                chunks.append("\n\n".join(current))
                current, current_words = [], 0
            current.append(unit)
            current_words += unit_words
        if current:
            chunks.append("\n\n".join(current))
        return chunks

    @staticmethod
    def _count_words(text):
        return len(text.split())
