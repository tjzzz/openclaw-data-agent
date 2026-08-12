"""主备改写适配器。"""

import logging

from app.humanizer.adapter import HumanizerAdapter

logger = logging.getLogger("app.humanizer.failover")


class FailoverHumanizer(HumanizerAdapter):
    """主适配器异常时自动调用备用适配器。"""

    def __init__(self, primary, fallback):
        self.primary = primary
        self.fallback = fallback

    def humanize(self, text, mode=None, paragraphs=None):
        return self.humanize_structured(text, mode=mode, paragraphs=paragraphs)[0]

    def humanize_structured(self, text, mode=None, paragraphs=None, progress_cb=None):
        try:
            return self.primary.humanize_structured(
                text, mode=mode, paragraphs=paragraphs, progress_cb=progress_cb
            )
        except Exception:
            logger.exception(
                "Primary humanizer %s failed; switching to %s",
                type(self.primary).__name__, type(self.fallback).__name__,
            )
            if progress_cb:
                progress_cb(stage="rewrite", message="正在切换备用改写服务")
            try:
                return self.fallback.humanize_structured(
                    text, mode=mode, paragraphs=paragraphs, progress_cb=progress_cb
                )
            except Exception as fallback_error:
                raise RuntimeError("主改写服务和备用改写服务均不可用") from fallback_error
