"""
AI Detector Adapter — 根据配置返回对应的 analyze_text 函数。

用法：在 create_app() 中调用 create_detector(name)，
然后把返回的函数注册到 app.extensions.ai_detector。

适配的 adapter_name：
  - "rule_based"  → 本地规则 (rule_based.py)
  - "sapling"     → Sapling.ai API
  - "originality"  → Originality.ai API
  - "sapling_mock" → 模拟 Sapling（随机 sleep 1-1.5s，不真实请求），用于测试等待界面
  - "rule_based_mock" → 模拟本地规则（随机 sleep），用于测试等待界面
"""

import random
import time

from app.ai_detector.api import analyze_text as _api_detect
from app.ai_detector.rule_based import analyze_text as _rule_detect


def _make_api_detect(backend: str):
    """
    API 检测 + 规则子评分 = 混合模式。
    主分用 API，子分（perplexity / 句式 / 可读性等）仍用规则。
    """
    def _detect(text: str, stage: str = "analyze") -> dict:
        import logging
        _logger = logging.getLogger("app.ai_detector.adapter")
        api = _api_detect(text, backend=backend, stage=stage)
        if "error" in api:
            _logger.warning(
                "detect stage=%s backend=%s action=fallback_to_rule fallback=1 "
                "result=rule_estimate error=%s chars=%d",
                stage, backend, api.get("error", "unknown"), len(text),
            )
            # API 失败/超时时降级到规则，但保留规则的真实结果，
            # 不覆盖成 API 的占位值（ai_score=50 / Unknown），避免误导用户。
            rule = _rule_detect(text)
            rule["backend"] = f"{backend}_fallback"
            rule["error"] = api.get("error", "unknown")
            return rule
        _logger.info("detect stage=%s backend=%s action=ok ai_score=%.1f",
                     stage, backend, api.get("ai_score", 0))
        rule = _rule_detect(text)
        rule["ai_score"] = api["ai_score"]
        rule["risk_level"] = api["risk_level"]
        rule["risk_description"] = api["risk_description"]
        rule["backend"] = backend
        return rule
    return _detect


def _make_mock_detect(label: str):
    """
    模拟检测：随机 sleep 1-1.5s，返回规则结果，不真实请求外部 API。
    用于测试"改写进行中"等待界面。
    """
    def _mock(text: str, stage: str = "analyze") -> dict:
        import logging
        _logger = logging.getLogger("app.ai_detector.adapter")
        duration = random.uniform(1.0, 1.5)
        _logger.info("detect stage=%s backend=%s_mock action=start chars=%d sleep=%.2fs",
                     stage, label, len(text), duration)
        time.sleep(duration)
        rule = _rule_detect(text)
        rule["backend"] = f"{label}_mock"
        rule["mock"] = True
        _logger.info("detect stage=%s backend=%s_mock action=done ai_score=%.1f elapsed=%.0fms",
                     stage, label, rule.get("ai_score", 0), duration * 1000)
        return rule
    return _mock


def create_detector(adapter_name: str = "rule_based"):
    """
    返回一个 analyze_text 可调用对象（仅整篇 AI 率检测）。

    adapter_name 取值：
      rule_based  → 本地规则检测
      sapling     → Sapling.ai
      originality → Originality.ai
      sapling_mock → 模拟 Sapling（随机 sleep，不请求外部），测试用
      rule_based_mock → 模拟本地规则（随机 sleep），测试用

    返回的函数签名：callable(text, stage="analyze") -> dict。
    """
    if adapter_name == "rule_based":
        return _rule_detect
    elif adapter_name in ("sapling", "originality"):
        return _make_api_detect(adapter_name)
    elif adapter_name == "sapling_mock":
        return _make_mock_detect("sapling")
    elif adapter_name == "rule_based_mock":
        return _make_mock_detect("rule_based")
    raise ValueError(f"Unknown AI_DETECTOR_ADAPTER: {adapter_name}")
