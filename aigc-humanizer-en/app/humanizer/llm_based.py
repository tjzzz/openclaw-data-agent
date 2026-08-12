"""基于 OpenAI-compatible Chat Completions API 的英文改写实现。"""

import json
import logging
import os
import re
import time
from urllib import error as urllib_error
from urllib import request as urllib_request

from app.humanizer.adapter import HumanizerAdapter, _cfg

logger = logging.getLogger("app.humanizer.llm_based")


LLM_PROVIDERS = {
    "opencode": {
        "base_url": "https://opencode.ai/zen/v1",
        "default_model": "deepseek-v4-flash-free",
        "extra_payload": {},
    },
    "deepseek": {
        "base_url": "https://api.deepseek.com",
        "default_model": "deepseek-v4-flash",
        "extra_payload": {"thinking": {"type": "disabled"}},
    },
}


SYSTEM_PROMPT = """You are a careful English editor. Rewrite the supplied English prose so it reads naturally and reflects varied, purposeful human writing.

Requirements:
- Preserve the original meaning, argument, facts, numbers, dates, names, quotations, citations, technical terms, and level of formality.
- Do not invent evidence, sources, personal experiences, claims, or citations.
- Keep citation markers and inline references exactly associated with the claims they support.
- Reduce repetitive sentence patterns, formulaic transitions, unnecessary signposting, vague abstractions, and generic AI-style phrasing.
- Vary sentence length and structure only where it improves clarity and flow. Do not add deliberate errors, slang, or awkward wording.
- Preserve paragraph boundaries unless a small adjustment is necessary for readability.
- Return only the rewritten text. Do not add a preface, explanation, label, quotation marks, or Markdown fence.
"""


class LLMBasedHumanizer(HumanizerAdapter):
    """通过已配置的 LLM Provider 对英文正文进行自然化改写。"""

    def __init__(self, api_key=None, provider=None, model=None):
        self.provider = (
            provider or os.getenv("LLM_PROVIDER") or _cfg("LLM_PROVIDER", "opencode")
        ).lower()
        try:
            provider_config = LLM_PROVIDERS[self.provider]
        except KeyError as exc:
            supported = ", ".join(sorted(LLM_PROVIDERS))
            raise ValueError(
                f"不支持的 LLM_PROVIDER: {self.provider}；可选值：{supported}"
            ) from exc

        self.api_key = api_key or os.getenv("LLM_API_KEY") or _cfg("LLM_API_KEY", "")
        self.base_url = provider_config["base_url"].rstrip("/")
        configured_model = model or os.getenv("LLM_MODEL") or _cfg("LLM_MODEL", "")
        self.model = configured_model or provider_config["default_model"]
        self.extra_payload = provider_config["extra_payload"]
        self.temperature = float(_cfg("LLM_TEMPERATURE", 0.7))
        self.max_tokens = int(_cfg("LLM_MAX_TOKENS", 8192))
        self.timeout = float(_cfg("LLM_TIMEOUT", 90))
        self.max_retries = int(_cfg("LLM_MAX_RETRIES", 3))
        self.retry_delay = float(_cfg("LLM_RETRY_DELAY", 2.0))

        if not self.api_key:
            logger.warning("LLM_API_KEY 未配置，调用 llm_based 时会报错。")

    def humanize(self, text, mode=None, paragraphs=None):
        return self.humanize_structured(text, mode=mode, paragraphs=paragraphs)[0]

    def humanize_structured(self, text, mode=None, paragraphs=None, progress_cb=None):
        if mode is None:
            mode = _cfg("REWRITE_MODE_DEFAULT", "median")
        if not self.api_key:
            raise RuntimeError("LLM API Key 未配置，请设置 LLM_API_KEY。")
        if not text or not text.strip():
            return "", []

        if paragraphs is not None:
            return self._humanize_segmented_structured(
                mode, paragraphs, self._rewrite_with_llm_chunking, progress_cb=progress_cb
            )

        return self._rewrite_with_llm_chunking(text), []

    def _rewrite_with_llm_chunking(self, text):
        return self._rewrite_with_chunking(
            text,
            self._call_api,
            max_words=int(_cfg("REWRITE_MAX_WORDS", 2000)),
            backend_label="llm_based",
            use_global_limit=True,
        )

    def _call_api(self, text):
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stream": False,
        }
        payload.update(self.extra_payload)
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        endpoint = f"{self.base_url}/chat/completions"

        for attempt in range(1, self.max_retries + 1):
            started = time.time()
            req = urllib_request.Request(endpoint, data=body, method="POST")
            req.add_header("Authorization", f"Bearer {self.api_key}")
            req.add_header("Content-Type", "application/json")
            req.add_header("Accept", "application/json")
            req.add_header("User-Agent", "Huma/1.0 (+https://ipengai.cn)")
            try:
                with urllib_request.urlopen(req, timeout=self.timeout) as response:
                    response_body = response.read().decode("utf-8", errors="replace")
                result = self._extract_content(response_body)
                logger.info(
                    "rewrite stage=rewrite backend=llm_based provider=%s model=%s action=call_ok "
                    "words=%d out_chars=%d elapsed=%.0fms",
                    self.provider, self.model, len(text.split()), len(result),
                    (time.time() - started) * 1000,
                )
                return result
            except urllib_error.HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="replace")[:500]
                retryable = exc.code == 429 or 500 <= exc.code < 600
                message = f"LLM API 返回 HTTP {exc.code}: {detail}"
                if not retryable:
                    raise RuntimeError(message) from exc
            except (urllib_error.URLError, TimeoutError, ValueError, KeyError) as exc:
                message = f"LLM API 调用失败: {exc}"

            if attempt >= self.max_retries:
                raise RuntimeError(f"{message}（已重试 {self.max_retries} 次）")
            logger.warning(
                "rewrite stage=rewrite backend=llm_based action=retry attempt=%d err=%s",
                attempt, message,
            )
            time.sleep(self.retry_delay * attempt)

        raise RuntimeError("LLM API 调用失败。")

    @staticmethod
    def _extract_content(response_body):
        data = json.loads(response_body)
        content = data["choices"][0]["message"]["content"].strip()
        if not content:
            raise ValueError("模型返回了空内容")
        fence = re.fullmatch(r"```(?:text|markdown)?\s*\n?(.*?)\n?```", content, re.DOTALL)
        return fence.group(1).strip() if fence else content
