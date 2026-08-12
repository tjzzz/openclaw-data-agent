#!/usr/bin/env python3
"""
Payment adapter — abstracts payment gateway integration.
Uses the Adapter pattern so the app can switch between mock and real payment providers.
"""

import json
from abc import ABC, abstractmethod
import os
import logging
import time

from config import ALIPAY_APP_ID, ALIPAY_PID, ALIPAY_PRIVATE_KEY, ALIPAY_PUBLIC_KEY, \
    ALIPAY_GATEWAY_URL, ALIPAY_NOTIFY_URL, ALIPAY_RETURN_URL, PAYMENT_ADAPTER

logger = logging.getLogger(__name__)

# Retry config for transient HTTP errors (502, 503, 504)
_MAX_RETRIES = 3
_RETRY_DELAY = 2  # seconds, doubles each retry
_RETRYABLE_STATUS = {502, 503, 504}


class PaymentAdapter(ABC):
    """Interface for payment gateway adapters."""

    def create_prepay_order(self, order_id, amount, description, **kwargs):
        """
        Create a prepay order and return QR code for scanning.
        Returns dict with qr_code, order_id, and payment info.
        Default: raises NotImplementedError (adapters must implement if supported).
        """
        raise NotImplementedError("This adapter does not support prepay orders")

    def verify_notification(self, params, signature=None):
        """
        Verify payment notification from payment gateway.
        Returns (is_valid, order_id, trade_no, amount) tuple.
        Default: raises NotImplementedError.
        """
        raise NotImplementedError("This adapter does not support notifications")

    def query_payment(self, order_id):
        """
        Query payment status from gateway (active polling).
        Returns dict with status and payment details.
        Default: raises NotImplementedError.
        """
        raise NotImplementedError("This adapter does not support status queries")


class MockPaymentAdapter(PaymentAdapter):
    """Mock payment adapter for development/testing — simulates payment flow."""

    def create_prepay_order(self, order_id, amount, description, **kwargs):
        """Simulate a prepay order with a mock QR code."""
        # Generate a mock QR code string (in real Alipay, this would be like:
        # https://qr.alipay.com/bax00xxx)
        mock_qr = f"MOCK_QR_{order_id}_{int(amount * 100)}"
        return {
            "qr_code": mock_qr,
            "order_id": order_id,
            "amount": amount,
            "method": "mock",
            "expires_in": 600
        }

    def verify_notification(self, params, signature=None):
        """Accept mock notifications with valid format."""
        # Mock: accept if out_trade_no and trade_status are present
        order_id = params.get("out_trade_no")
        trade_status = params.get("trade_status")
        if order_id and trade_status == "TRADE_SUCCESS":
            return True, order_id, f"MOCK_TRADE_{order_id}", params.get("total_amount", 0)
        return False, None, None, None

    def query_payment(self, order_id):
        """Simulate querying payment status."""
        # Mock: always return pending (in real flow, webhook handles the update)
        return {
            "order_id": order_id,
            "trade_status": "WAIT_BUYER_PAY",
            "status": "pending"
        }

    def create_prepay_form(self, order_id, amount, description, **kwargs):
        """
        Mock form_html for iframe mode testing.
        Returns a mock form HTML that mimics the real Alipay form structure.
        """
        mock_form = (
            f'<form name="punchout_form" method="post" '
            f'action="https://mock.alipay.com/gateway.do?method=mock">\n'
            f'<input type="hidden" name="biz_content" '
            f'value=\'{{"out_trade_no":"{order_id}"}}\'>\n'
            f'<input type="submit" value="立即支付" style="display:none" >\n'
            f'</form>\n'
            f'<script>document.forms[0].submit();</script>'
        )
        return {
            "form_html": mock_form,
            "order_id": order_id,
            "amount": amount,
            "method": "mock",
            "expires_in": 600
        }


class AlipayPaymentAdapter(PaymentAdapter):
    """
    Alipay Face-to-Face Payment (当面付) adapter.
    Uses alipay-sdk-python >= 3.7 (DefaultAlipayClient) for API calls.
    """

    @staticmethod
    def _to_pkcs1(key_str):
        """
        Convert PKCS8 RSA private key to PKCS1 format if needed.
        The alipay SDK's fill_private_key_marker wraps with
        '-----BEGIN RSA PRIVATE KEY-----' (PKCS1), but many modern
        OpenSSL versions output PKCS8 (-----BEGIN PRIVATE KEY-----)
        which the underlying rsa library cannot parse with PKCS1 markers.

        If conversion fails or the key is already PKCS1, returns the
        original string unchanged (the SDK's own marker-wrapping will
        handle it).
        """
        try:
            from cryptography.hazmat.primitives import serialization
            from cryptography.hazmat.primitives.serialization import load_pem_private_key
            # Try loading with PKCS8 markers first
            pem_data = (
                "-----BEGIN PRIVATE KEY-----\n"
                f"{key_str}\n"
                "-----END PRIVATE KEY-----"
            ).encode("utf-8")
            key_obj = load_pem_private_key(pem_data, password=None)

            # Export as PKCS1 (TraditionalOpenSSL = PKCS1 for RSA)
            pkcs1_der = key_obj.private_bytes(
                encoding=serialization.Encoding.DER,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption(),
            )
            # Encode back to base64 (single-line)
            import base64
            return base64.b64encode(pkcs1_der).decode("ascii")
        except Exception:
            # Not PKCS8 or cryptography not available — return as-is
            return key_str

    def __init__(self, app_id, pid, private_key, alipay_public_key,
                 gateway_url="https://openapi.alipay.com/gateway.do",
                 notify_url=None, return_url=None):
        """
        Initialize Alipay adapter with credentials.

        Args:
            app_id: Alipay application ID
            pid: Partner ID (seller ID)
            private_key: Application private key (PKCS1/PKCS8 PEM string)
            alipay_public_key: Alipay public key for signature verification
            gateway_url: Alipay gateway URL (sandbox vs production)
            notify_url: Async notification URL (webhook)
            return_url: Sync return URL after payment
        """
        self.app_id = app_id
        self.pid = pid
        self.private_key = private_key
        self.alipay_public_key = alipay_public_key
        self.gateway_url = gateway_url
        self.notify_url = notify_url
        self.return_url = return_url
        self.client = None
        self._sdk_available = False

        try:
            # Normalize and convert
            private_key_clean = self._to_pkcs1("".join(private_key.split()))
            public_key_clean = "".join(alipay_public_key.split())

            from alipay.aop.api.AlipayClientConfig import AlipayClientConfig
            from alipay.aop.api.DefaultAlipayClient import DefaultAlipayClient

            config = AlipayClientConfig(
                sandbox_debug="sandbox" in gateway_url or "alipaydev" in gateway_url
            )
            config.app_id = app_id
            config.app_private_key = private_key_clean
            config.alipay_public_key = public_key_clean
            config.sign_type = "RSA2"
            config.server_url = gateway_url

            self.client = DefaultAlipayClient(config)
            self._sdk_available = True

            # Patch the SDK's do_post to use urllib.request instead of httplib.HTTPSConnection
            # The SDK's built-in HTTP client has SSL compatibility issues on some Python/macOS setups
            self._patch_sdk_http_client()

        except ImportError:
            logger.warning(
                "alipay-sdk-python not installed or incompatible, "
                "AlipayPaymentAdapter will run in mock mode. "
                "Install with: pip install 'alipay-sdk-python>=3.7,<4.0'"
            )
        except Exception as e:
            logger.warning(f"Alipay SDK initialization failed: {e}")

    @staticmethod
    def _patch_sdk_http_client():
        """
        Monkey-patch the Alipay SDK's do_post to use urllib.request instead of httplib.

        The SDK uses http.client.HTTPSConnection which has SSL/TLS compatibility issues
        on some Python/macOS setups. This replaces it with urllib.request which handles
        SSL more robustly.
        """
        import urllib.request
        import urllib.parse
        from alipay.aop.api.util.WebUtils import ResponseException
        import alipay.aop.api.DefaultAlipayClient as _alc

        def _patched_do_post(url, query_string=None, headers=None, params=None,
                             charset='utf-8', timeout=60):
            # Build full URL with query string
            if query_string:
                url = url + ('&' if '?' in url else '?') + query_string

            # Build POST body
            body = None
            if params:
                body = urllib.parse.urlencode(params).encode(charset or 'utf-8')

            last_exc = None
            for attempt in range(_MAX_RETRIES):
                req = urllib.request.Request(url, data=body, method='POST')
                if headers:
                    for k, v in headers.items():
                        req.add_header(k, v)

                try:
                    resp = urllib.request.urlopen(req, timeout=timeout)
                    result = resp.read()
                    return result
                except urllib.request.HTTPError as e:
                    detail = e.read()
                    if isinstance(detail, bytes):
                        detail = detail.decode('utf-8', errors='replace')
                    # Retry on transient server errors (502/503/504)
                    if e.code in _RETRYABLE_STATUS and attempt < _MAX_RETRIES - 1:
                        delay = _RETRY_DELAY * (2 ** attempt)
                        logger.warning(
                            f"Alipay gateway returned HTTP {e.code}, "
                            f"retrying in {delay}s (attempt {attempt + 1}/{_MAX_RETRIES})"
                        )
                        time.sleep(delay)
                        last_exc = e
                        continue
                    raise ResponseException(
                        f'invalid http status {e.code}, detail body: {detail[:500]}'
                    )

            # Should not reach here, but just in case
            if last_exc:
                raise ResponseException(
                    f'invalid http status {last_exc.code} after {_MAX_RETRIES} retries'
                )

        # Patch at the module that imported do_post (DefaultAlipayClient)
        _alc.do_post = _patched_do_post

    def create_prepay_order(self, order_id, amount, description, **kwargs):
        """
        Call alipay.trade.page.pay with qr_pay_mode=1 to get QR code.

        电脑网站支付 + 二维码前置模式：
        qr_pay_mode=1 让支付宝在响应中直接返回 qr_code，
        用户扫二维码即可支付，无需跳转到支付宝页面。

        Returns:
            dict with qr_code, order_id, amount, expires_in
        """
        if not self._sdk_available:
            logger.warning("Alipay SDK not available, returning mock QR code")
            return {
                "qr_code": f"MOCK_ALIPAY_{order_id}",
                "order_id": order_id,
                "amount": amount,
                "method": "alipay_mock",
                "expires_in": 600
            }

        try:
            from alipay.aop.api.request.AlipayTradePagePayRequest import AlipayTradePagePayRequest
            from alipay.aop.api.domain.AlipayTradePagePayModel import AlipayTradePagePayModel

            model = AlipayTradePagePayModel()
            model.out_trade_no = order_id
            model.total_amount = str(amount)
            model.subject = description or "AI降AI率服务"
            model.timeout_express = "10m"
            # 支付宝电脑网站支付
            model.product_code = "FAST_INSTANT_TRADE_PAY"
            # 二维码前置 — 支付宝直接返回 qr_code，用户扫码支付
            model.qr_pay_mode = "1"
            # Pass seller_id (PID) so Alipay knows which account receives the payment
            if self.pid:
                model.seller_id = self.pid

            request = AlipayTradePagePayRequest(biz_model=model)
            # ⚠️ CRITICAL: notify_url must be set on the request, not just in config
            if self.notify_url:
                request.notify_url = self.notify_url

            response_raw = self.client.execute(request)
            # alipay-sdk-python 3.7.x returns bytes on Python 3.8 — decode to str
            if isinstance(response_raw, bytes):
                response_str = response_raw.decode("utf-8", errors="replace")
            else:
                response_str = response_raw
            try:
                response = json.loads(response_str)
            except (json.JSONDecodeError, TypeError):
                logger.error(f"Alipay response is not valid JSON: {str(response_str)[:500]}")
                return {"error": "支付宝接口返回异常，请稍后重试", "order_id": order_id}

            # Debug: log full response for troubleshooting
            logger.info(f"Alipay page.pay response: {json.dumps(response, ensure_ascii=False)[:1000]}")

            # Check for error_response (Alipay returns this for auth/validation errors)
            error_response = response.get("error_response")
            if error_response:
                sub_code = error_response.get("sub_code", "")
                sub_msg = error_response.get("sub_msg", "")
                code = error_response.get("code", "")
                msg = error_response.get("msg", "创建订单失败")
                logger.error(
                    f"Alipay page.pay error_response: code={code}, "
                    f"sub_code={sub_code}, msg={msg}, sub_msg={sub_msg}"
                )
                return {
                    "error": sub_msg or msg,
                    "code": code,
                    "sub_code": sub_code,
                    "order_id": order_id
                }

            # The SDK's __parse_response returns the INNER content (without
            # the "alipay_trade_page_pay_response" wrapper), so check both.
            inner = response.get("alipay_trade_page_pay_response") or response
            response_code = inner.get("code")

            if response_code == "10000":
                return {
                    "qr_code": inner.get("qr_code"),
                    "order_id": order_id,
                    "amount": amount,
                    "method": "alipay",
                    "expires_in": 600,
                    "raw_response": response
                }
            else:
                sub_code = inner.get("sub_code", "")
                sub_msg = inner.get("sub_msg", "")
                msg = inner.get("msg", "创建订单失败")
                logger.error(
                    f"Alipay page.pay failed: code={response_code}, "
                    f"sub_code={sub_code}, msg={msg}, sub_msg={sub_msg}"
                )
                return {
                    "error": sub_msg or msg,
                    "code": response_code,
                    "sub_code": sub_code,
                    "order_id": order_id
                }

        except Exception as e:
            err_msg = str(e)
            if "504" in err_msg or "502" in err_msg or "503" in err_msg:
                logger.error(
                    f"Alipay gateway returned server error after retries: {err_msg[:200]}"
                )
                err_msg = "支付宝沙箱服务暂时不可用，请稍后重试（如持续出现请切换到正式环境）"
            elif "can only concatenate str" in err_msg and "bytes" in err_msg:
                logger.error(
                    "Alipay SDK Python 3.8 compatibility error: the Alipay gateway returned "
                    "a non-200 HTTP status, and the SDK failed to read the response body. "
                    "Check ALIPAY_GATEWAY_URL and network connectivity."
                )
                err_msg = "支付宝网关连接异常，请检查网关地址和网络连接"
            else:
                logger.exception("Alipay precreate exception")
            return {"error": err_msg, "order_id": order_id}

    def create_prepay_form(self, order_id, amount, description, **kwargs):
        """
        Use page_execute("POST") to generate an HTML form for iframe embedding.
        qr_pay_mode=4: 可定义宽度的嵌入式二维码（仅显示二维码图片，无其他UI）。

        Unlike create_prepay_order (which calls execute() — a real HTTP request),
        page_execute("POST") does NOT make an HTTP request.
        It only assembles the signed form HTML locally.

        Returns:
            dict with form_html, order_id, amount, method, expires_in
        """
        if not self._sdk_available:
            logger.warning("Alipay SDK not available, returning mock form")
            return {
                "form_html": f'<div style="padding:40px;text-align:center;">Mock Alipay QR for {order_id}</div>',
                "order_id": order_id,
                "amount": amount,
                "method": "alipay_mock",
                "expires_in": 600
            }

        try:
            from alipay.aop.api.request.AlipayTradePagePayRequest import AlipayTradePagePayRequest
            from alipay.aop.api.domain.AlipayTradePagePayModel import AlipayTradePagePayModel

            model = AlipayTradePagePayModel()
            model.out_trade_no = order_id
            model.total_amount = str(amount)
            model.subject = description or "AI降AI率服务"
            model.timeout_express = "10m"
            # 支付宝电脑网站支付(product_code必填)
            model.product_code = "FAST_INSTANT_TRADE_PAY"
            # 仅显示二维码图片（无支付宝登录/账号表单 UI）
            model.qr_pay_mode = "4"
            model.qrcode_width = "200"
            if self.pid:
                model.seller_id = self.pid

            request = AlipayTradePagePayRequest(biz_model=model)
            if self.notify_url:
                request.notify_url = self.notify_url

            # page_execute("POST") 不发起 HTTP 请求，仅生成表单 HTML
            form_html = self.client.page_execute(request, "POST")

            logger.info(
                f"Alipay pageExecute success for {order_id}, "
                f"form_html length={len(form_html)}, "
                f"preview={form_html[:300]}"
            )

            return {
                "form_html": form_html,
                "order_id": order_id,
                "amount": amount,
                "method": "alipay",
                "expires_in": 600
            }

        except Exception as e:
            logger.exception("Alipay pageExecute exception")
            return {"error": f"支付宝页面请求失败: {str(e)[:200]}", "order_id": order_id}

    def verify_notification(self, params, signature=None):
        """
        Verify Alipay async notification signature and extract payment info.

        Note: Uses get_sign_content + verify_with_rsa from the SDK's
        SignatureUtils because DefaultAlipayClient does not expose a
        public notification verification method.

        Args:
            params: Dict of notification parameters from Alipay
                    (sign and sign_type should already be removed)
            signature: The sign string (extracted from params before calling)

        Returns:
            (is_valid, order_id, trade_no, amount) tuple
        """
        if not self._sdk_available:
            order_id = params.get("out_trade_no")
            if order_id and params.get("trade_status") == "TRADE_SUCCESS":
                return True, order_id, params.get("trade_no"), float(params.get("total_amount", 0))
            return False, None, None, None

        try:
            from alipay.aop.api.util.SignatureUtils import get_sign_content, verify_with_rsa

            sign = signature or params.get("sign", "")

            # Build sorted sign content (same algorithm Alipay uses)
            sign_content = get_sign_content(params)

            # Verify signature using Alipay public key
            is_valid = verify_with_rsa(
                self.alipay_public_key,
                sign_content.encode("utf-8"),
                sign
            )

            if not is_valid:
                logger.warning(
                    f"Alipay notification signature verification failed "
                    f"for {params.get('out_trade_no')}"
                )
                return False, None, None, None

            # Verify it's for our app
            if params.get("app_id") != self.app_id:
                logger.warning(
                    f"Alipay notification app_id mismatch: "
                    f"{params.get('app_id')} != {self.app_id}"
                )
                return False, None, None, None

            # Check trade status
            trade_status = params.get("trade_status")
            if trade_status not in ("TRADE_SUCCESS", "TRADE_FINISHED"):
                logger.info(f"Alipay notification with non-success status: {trade_status}")
                return False, None, None, None

            order_id = params.get("out_trade_no")
            trade_no = params.get("trade_no")
            amount = float(params.get("total_amount", 0))

            return True, order_id, trade_no, amount

        except Exception as e:
            logger.exception("Alipay notification verification exception")
            return False, None, None, None

    def query_payment(self, order_id):
        """
        Query payment status via alipay.trade.query.
        Used for active polling when webhook is not available.

        Returns:
            dict with trade_status and payment details
        """
        if not self._sdk_available:
            return {"order_id": order_id, "trade_status": "UNKNOWN", "status": "unknown"}

        try:
            from alipay.aop.api.request.AlipayTradeQueryRequest import AlipayTradeQueryRequest
            from alipay.aop.api.domain.AlipayTradeQueryModel import AlipayTradeQueryModel

            model = AlipayTradeQueryModel()
            model.out_trade_no = order_id

            request = AlipayTradeQueryRequest(biz_model=model)
            response_str = self.client.execute(request)
            # The patched do_post returns raw bytes — decode first
            if isinstance(response_str, bytes):
                response_str = response_str.decode("utf-8", errors="replace")
            response = json.loads(response_str)

            # The patched do_post bypasses SDK's __parse_response, so the response
            # may or may not be wrapped in "alipay_trade_query_response".
            # Handle both formats (same pattern as create_prepay_order).
            alipay_trade_query_response = response.get(
                "alipay_trade_query_response"
            ) or response
            response_code = alipay_trade_query_response.get("code")

            if response_code == "10000":
                trade_status = alipay_trade_query_response.get("trade_status", "UNKNOWN")
                returned_order_id = alipay_trade_query_response.get("out_trade_no")
                return {
                    "order_id": returned_order_id,
                    "trade_no": alipay_trade_query_response.get("trade_no"),
                    "trade_status": trade_status,
                    "total_amount": float(alipay_trade_query_response.get("total_amount", 0)),
                    "status": "paid" if trade_status in ("TRADE_SUCCESS", "TRADE_FINISHED") else "pending",
                    "raw_response": response
                }
            else:
                sub_code = alipay_trade_query_response.get("sub_code", "")
                sub_msg = alipay_trade_query_response.get("sub_msg", "")
                msg = alipay_trade_query_response.get("msg", "")

                # ★ 交易不存在 — 使用 page_execute 时属于正常情况
                #   （表单尚未提交到支付宝网关），当作 pending 而非 error
                if sub_code == "ACQ.TRADE_NOT_EXIST":
                    logger.info(
                        f"Alipay trade query for {order_id}: "
                        f"交易不存在（正常 — page_execute 模式，交易尚未提交）"
                    )
                    return {
                        "order_id": order_id,
                        "trade_status": "WAIT_BUYER_PAY",
                        "status": "pending",
                    }

                logger.warning(
                    f"Alipay trade query failed for {order_id}: "
                    f"code={response_code}, sub_code={sub_code}, msg={msg}, sub_msg={sub_msg}"
                )
                return {
                    "order_id": order_id,
                    "trade_status": "UNKNOWN",
                    "status": "unknown",
                    "error": sub_msg or msg
                }

        except Exception as e:
            logger.exception("Alipay query exception")
            return {"order_id": order_id, "trade_status": "ERROR", "error": str(e)}


def create_payment_adapter(config=None):
    """
    Factory function to create payment adapter based on configuration.

    Args:
        config: dict with PAYMENT_ADAPTER and related settings,
                or None to read from environment

    Returns:
        PaymentAdapter instance
    """
    if config is None:
        config = {
            "PAYMENT_ADAPTER": PAYMENT_ADAPTER,
            "ALIPAY_APP_ID": ALIPAY_APP_ID,
            "ALIPAY_PID": ALIPAY_PID,
            "ALIPAY_PRIVATE_KEY": ALIPAY_PRIVATE_KEY,
            "ALIPAY_PUBLIC_KEY": ALIPAY_PUBLIC_KEY,
            "ALIPAY_GATEWAY_URL": ALIPAY_GATEWAY_URL,
            "ALIPAY_NOTIFY_URL": ALIPAY_NOTIFY_URL,
            "ALIPAY_RETURN_URL": ALIPAY_RETURN_URL,
        }

    adapter_type = config.get("PAYMENT_ADAPTER", "mock")

    if adapter_type == "alipay":
        required_config = {
            "ALIPAY_APP_ID": config.get("ALIPAY_APP_ID"),
            "ALIPAY_PRIVATE_KEY": config.get("ALIPAY_PRIVATE_KEY"),
            "ALIPAY_PUBLIC_KEY": config.get("ALIPAY_PUBLIC_KEY"),
        }
        missing = [name for name, value in required_config.items() if not value]
        if missing:
            raise RuntimeError(
                "PAYMENT_ADAPTER=alipay requires configuration: "
                + ", ".join(missing)
            )

        adapter = AlipayPaymentAdapter(
            app_id=config["ALIPAY_APP_ID"],
            pid=config.get("ALIPAY_PID", ""),
            private_key=config.get("ALIPAY_PRIVATE_KEY", ""),
            alipay_public_key=config.get("ALIPAY_PUBLIC_KEY", ""),
            gateway_url=config.get("ALIPAY_GATEWAY_URL", "https://openapi.alipay.com/gateway.do"),
            notify_url=config.get("ALIPAY_NOTIFY_URL"),
            return_url=config.get("ALIPAY_RETURN_URL")
        )
        if not adapter._sdk_available:
            raise RuntimeError(
                "PAYMENT_ADAPTER=alipay could not initialize the Alipay SDK; "
                "check the SDK installation and Alipay key configuration"
            )
        return adapter
    if adapter_type == "mock":
        return MockPaymentAdapter()
    raise ValueError(
        f"Unknown PAYMENT_ADAPTER: {adapter_type}; expected 'mock' or 'alipay'"
    )
