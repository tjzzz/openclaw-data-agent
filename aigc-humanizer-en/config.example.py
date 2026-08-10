"""
配置示例 — 部署时复制为 config.py 并填入真实值。
"""

import os

PROJ_ROOT = os.path.dirname(os.path.abspath(__file__))

SECRET_KEY = 'your-secret-key-here'

AI_DETECTOR_ADAPTER = 'rule_based'  # rule_based | sapling | originality
HUMANIZER_ADAPTER = 'rule_based'    # rule_based | api
PAYMENT_ADAPTER = 'mock'            # mock | alipay

SAPLING_API_KEY = ''
ORIGINALITY_API_KEY = ''

AI_TEXT_HUMANIZER_EMAIL = ''
AI_TEXT_HUMANIZER_PASSWORD = ''

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
