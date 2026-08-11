"""Humanizer implementations and factory."""

from app.humanizer.api import ApiHumanizer
from app.humanizer.api_mock import ApiMockHumanizer
from app.humanizer.adapter import HumanizerAdapter
from app.humanizer.rule_based import RuleBasedHumanizer


def create_humanizer(name="rule_based"):
    implementations = {
        "rule_based": RuleBasedHumanizer,
        "api": ApiHumanizer,
        "api_mock": ApiMockHumanizer,
    }
    try:
        return implementations[name]()
    except KeyError as exc:
        raise ValueError(f"Unknown HUMANIZER_ADAPTER: {name}") from exc


__all__ = [
    "ApiHumanizer",
    "ApiMockHumanizer",
    "HumanizerAdapter",
    "RuleBasedHumanizer",
    "create_humanizer",
]
