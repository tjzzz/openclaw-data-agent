"""Simulated API implementation for local workflow testing."""

import logging
import time

from config import AI_TEXT_HUMANIZER_EMAIL as _CFG_EMAIL
from config import AI_TEXT_HUMANIZER_PASSWORD as _CFG_PASSWORD

from app.humanizer.ai_text_humanizer import AITextHumanizer

logger = logging.getLogger("app.humanizer.ai_text_humanizer_mock")


class AITextHumanizerMock(AITextHumanizer):
    """
    模拟 API 改写：不真实请求 ai-text-humanizer.com，每次改写随机 sleep 1-1.5s。
    用于测试"改写进行中"等待界面，行为/耗时与真实 API 对齐。

    仅覆盖 _call_api（mock 改写动作），其余分块/频控/结构保护逻辑完全复用 AITextHumanizer。
    """

    backend_label = "ai_text_humanizer_mock"

    def __init__(self, email=None, password=None):
        # Mock 不需要真实凭据，跳过父类校验
        self.email = email or _CFG_EMAIL
        self.password = password or _CFG_PASSWORD

    def _call_api(self, text):
        """
        Mock 单次改写：随机 sleep 1-1.5s，返回轻微改写的假文本。
        """
        import random as _random
        duration = _random.uniform(1.0, 1.5)
        start = time.time()
        logger.info(
            "rewrite stage=rewrite backend=ai_text_humanizer_mock action=call_start words=%d sleep=%.2fs",
            self._count_words(text), duration,
        )
        time.sleep(duration)
        # Mock 输出标出每次实际送审的分块边界，便于核对 segment 结果。
        lines = [l.strip() for l in text.split('\n') if l.strip()]
        result = '++++++++\n' + ' '.join(lines)
        logger.info(
            "rewrite stage=rewrite backend=ai_text_humanizer_mock action=call_ok words=%d out_chars=%d elapsed=%.0fms",
            self._count_words(text), len(result), (time.time() - start) * 1000,
        )
        return True, result
