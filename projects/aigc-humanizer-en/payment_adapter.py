#!/usr/bin/env python3
"""
Payment adapter — abstracts payment gateway integration.
Uses the Adapter pattern so the app can switch between mock and real payment providers.
"""

from abc import ABC, abstractmethod


class PaymentAdapter(ABC):
    """Interface for payment gateway adapters."""

    @abstractmethod
    def create_payment(self, order_id, amount, description):
        """
        Create a payment order.
        Returns a dict with payment_url and method info.
        """
        pass

    @abstractmethod
    def verify_payment(self, payment_token):
        """
        Verify that a payment was completed successfully.
        Returns True if valid, False otherwise.
        """
        pass


class MockPaymentAdapter(PaymentAdapter):
    """Mock payment adapter for development/testing — simulates payment flow."""

    def create_payment(self, order_id, amount, description):
        """Return a simulated payment URL."""
        return {"payment_url": f"/mock-pay/{order_id}", "method": "mock"}

    def verify_payment(self, payment_token):
        """Accept any token starting with 'PAY-'."""
        return bool(payment_token and payment_token.startswith("PAY-"))
