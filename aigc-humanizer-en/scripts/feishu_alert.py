#!/usr/bin/env python3
"""Send a personal Feishu alert, optionally with app or phone urgency."""

import argparse
import json
import os
import sys
from urllib import error, parse, request


FEISHU_BASE_URL = "https://open.feishu.cn/open-apis"


class FeishuAlertError(RuntimeError):
    pass


def _post_json(url, payload, token=None, method="POST", timeout=10):
    headers = {"Content-Type": "application/json; charset=utf-8"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method=method,
    )
    try:
        with request.urlopen(req, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise FeishuAlertError(
            f"Feishu HTTP {exc.code}: {body[:500]}"
        ) from exc
    except (error.URLError, OSError) as exc:
        raise FeishuAlertError(f"Feishu request failed: {exc}") from exc

    try:
        result = json.loads(body)
    except json.JSONDecodeError as exc:
        raise FeishuAlertError(
            f"Feishu returned invalid JSON: {body[:500]}"
        ) from exc
    if result.get("code") != 0:
        raise FeishuAlertError(
            f"Feishu API error {result.get('code')}: {result.get('msg')}"
        )
    return result


def get_tenant_access_token(app_id, app_secret):
    result = _post_json(
        f"{FEISHU_BASE_URL}/auth/v3/tenant_access_token/internal",
        {"app_id": app_id, "app_secret": app_secret},
    )
    token = result.get("tenant_access_token")
    if not token:
        raise FeishuAlertError("Feishu response did not contain tenant_access_token")
    return token


def send_personal_message(token, open_id, message):
    query = parse.urlencode({"receive_id_type": "open_id"})
    result = _post_json(
        f"{FEISHU_BASE_URL}/im/v1/messages?{query}",
        {
            "receive_id": open_id,
            "msg_type": "text",
            "content": json.dumps({"text": message}, ensure_ascii=False),
        },
        token=token,
    )
    message_id = (result.get("data") or {}).get("message_id")
    if not message_id:
        raise FeishuAlertError("Feishu response did not contain message_id")
    return message_id


def send_urgent(token, message_id, open_id, urgency):
    if urgency not in ("app", "phone"):
        return
    query = parse.urlencode({"user_id_type": "open_id"})
    _post_json(
        f"{FEISHU_BASE_URL}/im/v1/messages/{message_id}/urgent_{urgency}?{query}",
        {"user_id_list": [open_id]},
        token=token,
        method="PATCH",
    )


def send_alert(message, urgency="none"):
    app_id = os.environ.get("FEISHU_APP_ID", "").strip()
    app_secret = os.environ.get("FEISHU_APP_SECRET", "").strip()
    open_id = os.environ.get("FEISHU_ALERT_OPEN_ID", "").strip()
    missing = [
        name for name, value in (
            ("FEISHU_APP_ID", app_id),
            ("FEISHU_APP_SECRET", app_secret),
            ("FEISHU_ALERT_OPEN_ID", open_id),
        ) if not value
    ]
    if missing:
        raise FeishuAlertError(
            "Missing required environment variables: " + ", ".join(missing)
        )

    token = get_tenant_access_token(app_id, app_secret)
    message_id = send_personal_message(token, open_id, message)
    send_urgent(token, message_id, open_id, urgency)
    return message_id


def main():
    parser = argparse.ArgumentParser(
        description="Send a direct Feishu alert to the configured user."
    )
    parser.add_argument("message", help="Alert text")
    parser.add_argument(
        "--urgent",
        choices=("none", "app", "phone"),
        default="none",
        help="Urgency type (default: none)",
    )
    args = parser.parse_args()
    try:
        message_id = send_alert(args.message, urgency=args.urgent)
    except FeishuAlertError as exc:
        print(f"feishu alert failed: {exc}", file=sys.stderr)
        return 1
    print(f"feishu alert sent: message_id={message_id}, urgent={args.urgent}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
