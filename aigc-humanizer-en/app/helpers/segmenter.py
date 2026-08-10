"""Document segmenter: split an ordered paragraph list into rewrite tasks.

按文档结构把段落分组，供改写时决定"每次送 API 的文本块大小"。

核心能力：
    1. 结构保护（should_protect）—— 标题/图表/目录/短段 不改写
    2. 标题栈归属 —— 把正文段挂到最近的激活标题下
    3. 三种 mode 粒度：
        - low   : 单段（兼容旧值 paragraph）
        - median: 按二级标题(Heading 2)分块
        - high  : 按一级标题(Heading 1)分块
        无对应级别标题时退化为"段落块"（按动态 M 段一组）
    4. 返回有序的重建任务列表，含每个块需要送 API 的文本与应保护的段落。
"""

import re


# 聚合配置：相邻正文段聚合为一次改写请求的段落数与字数上限
DEFAULT_MEDIAN_PARAS = 3      # median：最多聚合 3 个连续正文段
DEFAULT_HIGH_PARAS = 5        # high：最多聚合 5 个连续正文段
DEFAULT_MAX_WORDS = 2000      # 单次请求最大字数（聚合超过即切新 part）


def _looks_like_title(text, words):
    """启发式判断一个 Normal 段是否像标题（无样式时的兜底）。"""
    if words > 15:
        return False
    stripped = text.strip()
    # 以数字/编号开头：1. 1.1 (1) 第一章 等
    if re.match(r'^(?:[\d]+[\s.、)）]+|[（(]\s*[\d]+[）)]\s*|第[一二三四五六七八九十百千0-9]+[章节部分篇])', stripped):
        return True
    # 无结尾句号（标题通常无句号）
    if not stripped.endswith(('.', '!', '?', '。', '！', '？')):
        # 且较短，视为标题
        if words <= 8:
            return True
    return False


class _StructureGuard:
    """段落保护判定器。

    基于 extract_text 阶段已标记好的段落属性做判断：
        - 表格占位 {'table': N}
        - 标题/目录类（is_heading=True）
        - 参考文献条目（is_reference=True，在 extract_text 阶段已标记）
        - 无格式正文且过短（< min_words）
        - 启发式"伪标题"识别

    无需维护前后文状态（参考文献标记已在 extract_text 解析时完成）。
    """

    def __init__(self, min_words=10):
        self.min_words = min_words

    def should_protect(self, para):
        if not para:
            return True
        # 表格占位
        if "table" in para:
            return True
        text = (para.get("text") or "").strip()
        if not text:
            return True

        # 参考文献条目（extract_text 已标记）
        if para.get("is_reference"):
            return True

        # 标题/目录类样式
        if para.get("is_heading", False):
            return True

        words = para.get("word_count", len(text.split()))
        # 无格式正文且过短
        if words < self.min_words:
            return True
        # 启发式"伪标题"识别
        if _looks_like_title(text, words):
            return True
        return False


def should_protect(para, min_words=10):
    """无状态的段落保护判定（供外部单段调用 / 测试用）。"""
    guard = _StructureGuard(min_words=min_words)
    return guard.should_protect(para)


# ---------- mode 分块 ----------

def segment(paragraphs, mode="low", min_words=10,
            median_paras=DEFAULT_MEDIAN_PARAS, high_paras=DEFAULT_HIGH_PARAS,
            max_words=DEFAULT_MAX_WORDS):
    """按 mode 把有序段落切分为"改写任务"。

    mode 枚举：
        low   = 单段（逐段改写，兼容旧值 paragraph）
        median= 连续正文段聚合（默认最多 3 段 / 总字数<max_words）
        high  = 连续正文段聚合（默认最多 5 段 / 总字数<max_words）

    聚合规则（median/high 共用，仅可聚合段落数不同）：
        - 标题 / 表格 / 参考文献 / 短段 是硬边界，不聚合进 part，原样保留
        - 相邻的正文段聚合成一个 part，最多 max_paras 段 且 总字数 < max_words
        - 达到任一上限即开启新的 part
        - 当 max_paras == 1 时，等价于 low（每段独立一次请求）

    Args:
        median_paras: median 模式最多聚合的连续正文段数（可配置）。
        high_paras:   high 模式最多聚合的连续正文段数（可配置）。
        max_words:    单次请求最大字数（聚合超过即切新 part）。

    Returns:
        list[dict]: 每个元素：
            {
                "type": "protected" | "rewrite" | "table",
                "text": 送 API 的文本（protected 时为原样保留文本）,
                "paragraphs": 该块涉及的段落 dict 列表,
            }
        按文档原顺序排列。
    """
    mode = (mode or "low").lower()
    # 兼容旧值 paragraph（等价于 low）
    if mode == "paragraph":
        mode = "low"
    guard = _StructureGuard(min_words=min_words)

    # 1) 单段模式：每段独立判断，保护段原样、正文段单独送
    if mode == "low":
        return _segment_paragraph(paragraphs, guard)

    # 2) median/high：先逐段打标记，再在连续正文之间按 N 段聚合
    max_paras = high_paras if mode == "high" else median_paras
    if max_paras <= 1:
        return _segment_paragraph(paragraphs, guard)
    return _segment_aggregate(paragraphs, guard, max_paras, max_words)


def _segment_paragraph(paragraphs, guard):
    tasks = []
    for para in paragraphs:
        if "table" in para:
            tasks.append({"type": "table", "paragraphs": [para]})
        elif guard.should_protect(para):
            tasks.append({"type": "protected", "text": para["text"],
                          "paragraphs": [para]})
        else:
            tasks.append({"type": "rewrite", "text": para["text"],
                          "paragraphs": [para]})
    return tasks


def _count_words(para):
    return para.get("word_count", len((para.get("text") or "").split()))


def _segment_aggregate(paragraphs, guard, max_paras, max_words):
    """连续正文段按 max_paras 段 + max_words 字聚合为一个 rewrite part。

    硬边界（表格/标题/参考文献/短段）作为分割点，不聚合进 part。
    """
    tasks = []
    buffer = []      # 当前聚合的正文段
    buffer_words = 0

    def flush():
        nonlocal buffer, buffer_words
        if buffer:
            body_text = "\n\n".join(p["text"] for p in buffer)
            tasks.append({"type": "rewrite", "text": body_text,
                          "paragraphs": buffer})
            buffer = []
            buffer_words = 0

    for para in paragraphs:
        if "table" in para:
            flush()
            tasks.append({"type": "table", "paragraphs": [para]})
        elif guard.should_protect(para):
            # 标题 / 参考文献 / 短段 是硬边界
            flush()
            tasks.append({"type": "protected", "text": para["text"],
                          "paragraphs": [para]})
        else:
            w = _count_words(para)
            # 若已满 max_paras 段，或加上本段会超过 max_words，则开启新 part
            if buffer and (len(buffer) >= max_paras or buffer_words + w > max_words):
                flush()
            buffer.append(para)
            buffer_words += w

    flush()
    return tasks
