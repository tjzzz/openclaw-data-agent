#!/usr/bin/env python3
"""
直接调用外部 API 检测英文 AI 率。

支持的接口：
  - sapling:     Sapling.ai (免费50次/月, 之后 $25/月起)
                 https://sapling.ai/docs/api/detector/
  - originality: Originality.ai (付费 $14.95/月)
                 https://originality.ai/

用法：
    from app.ai_detector.api import analyze_text
    result = analyze_text("text", backend="sapling")

环境变量：
    SAPLING_API_KEY
    ORIGINALITY_API_KEY

日志：DELETE_UPLOADED_FILE=False 时保存到 logs/ai_detector/ 目录
"""

import hashlib
import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timezone

import requests

from config import DELETE_UPLOADED_FILE
from config import ORIGINALITY_API_KEY as _CFG_ORIGINALITY_KEY, PROJ_ROOT
from config import SAPLING_API_KEY as _CFG_SAPLING_KEY

# 统一 logger
_logger = logging.getLogger("app.ai_detector.api")

# 日志目录
_LOG_DIR = os.path.join(PROJ_ROOT, "logs", "ai_detector")


def _fmt_elapsed(start):
    """格式化耗时（毫秒）。"""
    return f"{(time.time() - start) * 1000:.0f}ms"


# ---------- 结果落盘 ----------

def _save(text: str, result: dict):
    """按配置决定是否把检测结果写到日志文件。"""
    if DELETE_UPLOADED_FILE:
        return None
    ts = datetime.now(timezone.utc)
    # 用文本前 40 字符的 hash 做摘要，方便去重
    sig = hashlib.md5(text.encode()[:200]).hexdigest()[:8]
    filename = f"{result.get('backend', 'unknown')}_{ts.strftime('%Y%m%d_%H%M%S')}_{sig}.json"
    os.makedirs(_LOG_DIR, exist_ok=True)
    path = os.path.join(_LOG_DIR, filename)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({
            "timestamp": ts.isoformat(),
            "word_count": len(text.split()),
            "char_count": len(text),
            "text_preview": text[:300],
            "result": result,
        }, f, indent=2, ensure_ascii=False)
    return path


# ---------- 评分转风险等级 ----------

def _risk_level(score: float) -> tuple:
    if score < 20:
        return "Safe", "No action needed. Your text is unlikely to be flagged."
    elif score < 40:
        return "Warning", "Consider reviewing. Some sections may trigger flags."
    elif score < 60:
        return "Moderate Risk", "Humanization recommended to reduce detection risk."
    else:
        return "High Risk", "Strong humanization recommended before submission."


# ---------- Sapling.ai ----------

# Sapling 检测的单次分块上限（字符）。长文本整篇发送会导致服务端推理过重、
# 极易触发 30s 超时（实测 8488 字符即超时）。按此阈值分块、逐块检测后
# 按单词数加权合并整篇 AI 率，即可规避超时且结果可信。
SAPLING_CHUNK_CHARS = 8000


def _split_chunks(text: str, max_chars: int = SAPLING_CHUNK_CHARS) -> list:
    """
    把文本按语义边界切成 ≤max_chars 字符的块，不截断单词/句子。

    优先在段落（\\n\\n）边界切；段落仍超长时在句子边界切；句子仍超长时
    在单词边界切（空格处兜底）。
    """
    text = text.strip()
    if len(text) <= max_chars:
        return [text]

    chunks = []
    buffer = ""

    def append_part(part, separator="\n\n"):
        nonlocal buffer
        candidate = f"{buffer}{separator if buffer else ''}{part}"
        if buffer and len(candidate) > max_chars:
            chunks.append(buffer)
            buffer = part
        else:
            buffer = candidate

    def append_sentence(sentence):
        if len(sentence) <= max_chars:
            append_part(sentence)
            return
        word_buffer = ""
        for word in sentence.split():
            candidate = f"{word_buffer} {word}".strip()
            if word_buffer and len(candidate) > max_chars:
                append_part(word_buffer)
                word_buffer = word
            else:
                word_buffer = candidate
        if word_buffer:
            append_part(word_buffer)

    for para in filter(None, (value.strip() for value in text.split('\n\n'))):
        if len(para) <= max_chars:
            append_part(para)
            continue

        sentences = re.split(r'(?<=[.!?])\s+', para)
        sentence_buffer = ""
        for sentence in filter(None, (value.strip() for value in sentences)):
            if len(sentence_buffer) + len(sentence) + 1 <= max_chars:
                sentence_buffer = f"{sentence_buffer} {sentence}".strip()
                continue
            if sentence_buffer:
                append_part(sentence_buffer)
            if len(sentence) > max_chars:
                append_sentence(sentence)
                sentence_buffer = ""
            else:
                sentence_buffer = sentence
        if sentence_buffer:
            append_part(sentence_buffer)

    if buffer:
        chunks.append(buffer)
    return chunks


def _merge_chunk_scores(chunk_results: list) -> dict:
    """
    把多块检测结果按单词数加权合并为整篇 AI 率。
    返回 {"ai_score", "risk_level", "risk_description", "word_count"}。
    """
    total_words = sum(r["word_count"] for r in chunk_results) or 1
    weighted = sum(r["ai_score"] * r["word_count"] for r in chunk_results) / total_words
    score = round(weighted, 1)
    level, desc = _risk_level(score)
    return {
        "ai_score": score,
        "risk_level": level,
        "risk_description": desc,
        "word_count": total_words,
        "chunk_count": len(chunk_results),
    }


def _sapling_call(text: str, api_key: str, timeout: float = 30.0) -> dict:
    """单次调用 Sapling aidetect，返回 (raw_score_0to100, chunk_word_count)。

    记录单次请求的耗时（无 stage，由上层 analyze_text 统一标注阶段）。
    """
    # 性能优化：关闭逐句评分与词元高亮，只算整篇 AI 率。
    # - sent_scores=false：关闭逐句评分（默认 true，会大幅拖慢长文本检测）
    # - score_string=false：关闭词元级高亮 HTML（默认 true，额外生成 token 标注，
    #   本系统只展示整篇 ai_score，无需该可视化）
    start = time.time()
    resp = requests.post(
        "https://api.sapling.ai/api/v1/aidetect",
        json={
            "key": api_key,
            "text": text,
            "session_id": f"humanizer-{int(time.time())}",
            "sent_scores": False,
            "score_string": False,
        },
        timeout=timeout,
    )
    resp.raise_for_status()
    data = resp.json()
    raw_score = data.get("score")
    if not isinstance(raw_score, (int, float)) or not 0 <= raw_score <= 1:
        raise ValueError("Sapling response has an invalid score")
    score = raw_score * 100  # 0-1 → 0-100
    _logger.info(
        "detect backend=sapling action=call chars=%d words=%d score=%.1f elapsed=%s",
        len(text), len(text.split()), round(score, 1), _fmt_elapsed(start),
    )
    return {
        "ai_score": round(score, 1),
        "word_count": len(text.split()),
        "raw_score": raw_score,
    }


def _sapling_call_with_retry(text: str, api_key: str, timeout: float = 30.0,
                             max_retries: int = 2) -> dict:
    """Call Sapling and retry transient request failures at most twice."""
    for attempt in range(max_retries + 1):
        try:
            return _sapling_call(text, api_key, timeout=timeout)
        except requests.RequestException as exc:
            if attempt >= max_retries:
                raise
            _logger.warning(
                "detect backend=sapling action=retry attempt=%d/%d error=%s",
                attempt + 1, max_retries, type(exc).__name__,
            )
            time.sleep(attempt + 1)


def _sapling(text: str, api_key: str, timeout: float = 30.0) -> dict:
    """
    Sapling 整篇 AI 率检测，超长文本自动分块规避 30s 超时。

    ≤SAPLING_CHUNK_CHARS 时单次调用；超长则按 8000 字符分块，逐块检测后
    按各块单词数加权合并为整篇 AI 率。结果按原整篇文本落盘一份。
    """
    if len(text) <= SAPLING_CHUNK_CHARS:
        r = _sapling_call_with_retry(text, api_key, timeout=timeout)
        level, desc = _risk_level(r["ai_score"])
        result = {
            "ai_score": r["ai_score"],
            "risk_level": level,
            "risk_description": desc,
            "backend": "sapling",
            "details": {
                "sentence_count": 0,
                "avg_sentence_score": 0,
                "sentence_scores": [],
                "raw_score": r["raw_score"],
            },
        }
        _save(text, result)
        return result

    # 超长：分块检测 + 单词数加权合并
    start = time.time()
    chunks = _split_chunks(text, SAPLING_CHUNK_CHARS)
    _logger.info(
        "detect backend=sapling action=chunk_split chars=%d chunks=%d", len(text), len(chunks)
    )

    chunk_results = []
    for i, chunk in enumerate(chunks, 1):
        r = _sapling_call_with_retry(chunk, api_key, timeout=timeout)
        chunk_results.append(r)

    merged = _merge_chunk_scores(chunk_results)
    _logger.info(
        "detect backend=sapling action=merge chunks=%d ai_score=%.1f elapsed=%s",
        merged["chunk_count"], merged["ai_score"], _fmt_elapsed(start),
    )
    level, desc = _risk_level(merged["ai_score"])
    result = {
        "ai_score": merged["ai_score"],
        "risk_level": level,
        "risk_description": desc,
        "backend": "sapling",
        "details": {
            "sentence_count": 0,
            "avg_sentence_score": 0,
            "sentence_scores": [],
            "chunked": True,
            "chunk_count": merged["chunk_count"],
            "chunk_scores": [
                {"ai_score": r["ai_score"], "word_count": r["word_count"]}
                for r in chunk_results
            ],
            "raw_score": None,  # 分块后无单一 raw_score，整篇分见 ai_score
        },
    }
    _save(text, result)
    return result


# ---------- Originality.ai ----------

def _originality(text: str, api_key: str) -> dict:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "X-Api-Key": api_key,
        "Content-Type": "application/json",
    }
    resp = requests.post(
        "https://api.originality.ai/v1/scan",
        json={"content": text, "aiModelVersion": "latest"},
        headers=headers,
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()

    raw = data.get("aiScore", 50)
    if isinstance(raw, float) and raw <= 1.0:
        raw *= 100

    level, desc = _risk_level(float(raw))
    result = {
        "ai_score": round(float(raw), 1),
        "risk_level": level,
        "risk_description": desc,
        "backend": "originality",
        "details": {
            "credits_used": data.get("creditsUsed", 0),
            "scan_id": data.get("scanId", ""),
            "raw_response": data,
        },
    }
    _save(text, result)
    return result


# ---------- 统一入口 ----------

KEY_MAP = {
    "sapling": _CFG_SAPLING_KEY,
    "originality": _CFG_ORIGINALITY_KEY,
}

BACKENDS = {
    "sapling": _sapling,
    "originality": _originality,
}


def analyze_text(text: str, backend: str = "sapling", api_key: str = "", stage: str = "analyze") -> dict:
    """
    分析英文文本的 AI 生成概率。配置开启时保存到 logs/ai_detector/。

    Parameters
    ----------
    text : str
        待检测文本（建议 ≥50 字符）。
    backend : str
        "sapling"（默认）或 "originality"。
    api_key : str
        留空则从 config.py 读取。
    stage : str
        调用场景标识，用于日志区分（analyze=分析 / rewrite_detect=改写后再检测）。
        由上层传入，便于按阶段排查耗时。

    Returns
    -------
    dict
        含 ai_score / risk_level / risk_description / backend / details。
        出错时含 error 字段，ai_score=50，也会落盘。
    """
    if not text or len(text.strip()) < 50:
        return {
            "error": "Text too short (minimum 50 characters)",
            "ai_score": 0,
            "risk_level": "Unknown",
            "backend": backend,
        }

    if backend not in BACKENDS:
        return {
            "error": f"Unknown backend '{backend}'",
            "ai_score": 0,
            "risk_level": "Unknown",
            "backend": backend,
        }

    key = api_key or KEY_MAP.get(backend, "")
    if not key:
        return {
            "error": f"Missing API key for {backend}. Set it in config.py.",
            "ai_score": 50,
            "risk_level": "Unknown",
            "backend": backend,
        }

    start = time.time()
    _logger.info(
        "detect stage=%s backend=%s action=start chars=%d preview=%s...",
        stage, backend, len(text), text[:60].replace("\n", " "),
    )

    try:
        handler = BACKENDS[backend]
        result = handler(text, key)
        _logger.info(
            "detect stage=%s backend=%s action=done ai_score=%.1f words=%d elapsed=%s",
            stage, backend, result.get("ai_score", 0), len(text.split()), _fmt_elapsed(start),
        )
        return result
    except requests.Timeout:
        _logger.warning("detect stage=%s backend=%s action=timeout elapsed=%s",
                        stage, backend, _fmt_elapsed(start))
        err = {"error": f"Timeout from {backend}", "ai_score": 50, "risk_level": "Unknown", "backend": backend}
        _save(text, err)
        return err
    except requests.HTTPError as e:
        _logger.warning("detect stage=%s backend=%s action=http_error status=%d",
                        stage, backend, e.response.status_code)
        err = {"error": f"HTTP {e.response.status_code} from {backend}", "ai_score": 50, "risk_level": "Unknown", "backend": backend}
        _save(text, err)
        return err
    except Exception as e:
        _logger.error("detect stage=%s backend=%s action=error err=%s", stage, backend, e)
        err = {"error": f"{backend}: {e}", "ai_score": 50, "risk_level": "Unknown", "backend": backend}
        _save(text, err)
        return err


# ---------- CLI ----------

if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="AI content detector via API")
    p.add_argument("--text", "-t", help="Text to analyze")
    p.add_argument("--file", "-f", help="Read text from file")
    p.add_argument("--backend", "-b", default="sapling", choices=list(BACKENDS))
    p.add_argument("--api-key", help="Override API key")
    p.add_argument("--no-save", action="store_true", help="不落盘（默认自动保存）")
    args = p.parse_args()

    if args.file:
        with open(args.file) as f:
            text = f.read()
    elif args.text:
        text = args.text
    else:
        p.print_help()
        sys.exit(1)

    result = analyze_text(text, backend=args.backend, api_key=args.api_key)
    print(json.dumps(result, indent=2, ensure_ascii=False))
