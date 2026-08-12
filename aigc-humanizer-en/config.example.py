"""
配置示例 — 部署时复制为 config.py 并填入真实值。
"""

import os

PROJ_ROOT = os.path.dirname(os.path.abspath(__file__))

SECRET_KEY = 'your-secret-key-here'

AI_DETECTOR_ADAPTER = 'rule_based'  # rule_based | sapling | originality
HUMANIZER_ADAPTER = 'rule_based'    # rule_based | ai_text_humanizer | ai_text_humanizer_mock | llm_based
HUMANIZER_FALLBACK_ADAPTER = ''     # 例如主 llm_based、备用 ai_text_humanizer
PAYMENT_ADAPTER = 'mock'            # mock | alipay
ALLOW_MOCK_PAYMENT = True           # 仅本地/测试环境允许；生产必须为 False

SAPLING_API_KEY = ''
ORIGINALITY_API_KEY = ''

AI_TEXT_HUMANIZER_EMAIL = ''
AI_TEXT_HUMANIZER_PASSWORD = ''

# 大模型改写（HUMANIZER_ADAPTER='llm_based'）
# LLM_PROVIDER 决定接口地址及默认模型，可选：opencode | deepseek
LLM_PROVIDER = 'opencode'
LLM_API_KEY = ''
LLM_MODEL = ''  # 留空时使用 provider 对应的默认模型
LLM_TEMPERATURE = 0.7
LLM_MAX_TOKENS = 8192
LLM_TIMEOUT = 90
LLM_MAX_RETRIES = 3
LLM_RETRY_DELAY = 2.0

PRICE_PER_1000_WORDS = 14.9
RECHARGE_PACKAGE_WORDS = [2000, 5000, 10000]
SIGNUP_BONUS_WORDS = 200

# ── 改写模式（mode）与频控 ──
REWRITE_MODE_DEFAULT = 'median'    # 默认改写模式：low=逐段 / median=章节聚合 / high=大段聚合
REWRITE_MEDIAN_PARAS = 3           # median 模式最多聚合的连续正文段数（=1 时等价于 low）
REWRITE_HIGH_PARAS = 5             # high 模式最多聚合的连续正文段数（=1 时等价于 low）
REWRITE_MAX_WORDS = 2000           # 单次改写请求的最大字数上限（聚合超过即切新 part）
RATE_LIMIT_MAX_REQUESTS = 30       # 改写请求数超过该值则启用 sleep 频控（防超 60 次/分钟）
RATE_LIMIT_SLEEP = 1.0             # 频控时每次改写请求后的 sleep 秒数（60 次/分钟 → 间隔≥1s）
HUMANIZER_GLOBAL_MAX_CONCURRENCY = 2
HUMANIZER_GLOBAL_MIN_INTERVAL = 1.0

ALLOWED_UPLOAD_MIMETYPES = {
    'text/plain', 'text/markdown', 'application/pdf',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
}
DELETE_UPLOADED_FILE = True   # 上传文件解析完成后是否删除临时文件（True=删除，False=保留）

ADMIN_PASSWORD = 'admin123'

ALIPAY_APP_ID = ''
ALIPAY_PID = ''
ALIPAY_PRIVATE_KEY = ''
ALIPAY_PUBLIC_KEY = ''
ALIPAY_GATEWAY_URL = 'https://openapi.alipay.com/gateway.do'
ALIPAY_NOTIFY_URL = ''
ALIPAY_RETURN_URL = ''
