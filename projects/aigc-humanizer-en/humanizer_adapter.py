#!/usr/bin/env python3
"""
Humanizer adapter — abstracts the text humanization engine.
Uses the Adapter pattern so the app can switch between rule-based and API-driven engines.
"""

from abc import ABC, abstractmethod


class HumanizerAdapter(ABC):
    """Interface for text humanization adapters."""

    @abstractmethod
    def humanize(self, text, mode='academic'):
        """
        Humanize the given text.
        Args:
            text: The text to humanize.
            mode: 'academic' or 'aggressive' — controls transformation intensity.
        Returns:
            Humanized text string.
        """
        pass


class RuleBasedHumanizer(HumanizerAdapter):
    """Rule-based humanizer wrapping the existing humanize.py module."""

    def humanize(self, text, mode='academic'):
        """Humanize text using deterministic rule-based transformations."""
        from humanize import humanize_text
        return humanize_text(text, academic_mode=(mode == 'academic'))


class ApiHumanizer(HumanizerAdapter):
    """API-based humanizer (placeholder — not yet connected)."""

    def humanize(self, text, mode='academic'):
        """Raise NotImplementedError — API humanizer not yet available."""
        raise NotImplementedError("API humanizer not yet connected")
