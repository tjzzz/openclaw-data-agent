"""Humanizer implementations and factory."""

from app.humanizer.ai_text_humanizer import AITextHumanizer
from app.humanizer.ai_text_humanizer_mock import AITextHumanizerMock
from app.humanizer.adapter import HumanizerAdapter
from app.humanizer.failover import FailoverHumanizer
from app.humanizer.llm_based import LLMBasedHumanizer
from app.humanizer.rule_based import RuleBasedHumanizer


def create_humanizer(name="rule_based", fallback_name=None):
    implementations = {
        "rule_based": RuleBasedHumanizer,
        "ai_text_humanizer": AITextHumanizer,
        "ai_text_humanizer_mock": AITextHumanizerMock,
        # 兼容旧部署配置，确认全部迁移后可删除。
        "api": AITextHumanizer,
        "api_mock": AITextHumanizerMock,
        "llm_based": LLMBasedHumanizer,
    }
    try:
        primary = implementations[name]()
    except KeyError as exc:
        raise ValueError(f"Unknown HUMANIZER_ADAPTER: {name}") from exc
    if not fallback_name:
        return primary
    if fallback_name == name:
        raise ValueError("HUMANIZER_FALLBACK_ADAPTER 不能与主适配器相同")
    try:
        fallback = implementations[fallback_name]()
    except KeyError as exc:
        raise ValueError(f"Unknown HUMANIZER_FALLBACK_ADAPTER: {fallback_name}") from exc
    return FailoverHumanizer(primary, fallback)


__all__ = [
    "AITextHumanizer",
    "AITextHumanizerMock",
    "HumanizerAdapter",
    "FailoverHumanizer",
    "LLMBasedHumanizer",
    "RuleBasedHumanizer",
    "create_humanizer",
]
