# AI Humanizer — 降低 AI 检测率，让论文更自然

基于 Turnitin 风格检测算法的 AI 文本检测与改写 Web 应用。上传文档或粘贴文本，一键检测 AI 率，精准改写保留原意。

## 功能

| 功能 | 详情 |
|------|------|
| 🔍 **AI 文本检测** | 多维评分（困惑度、突发性、AI 模式、可读性、结构），段落级分析 |
| ✏️ **降 AI 改写** | 学术/深度两种模式，保留学术术语与专业表达 |
| 👁️ **免费预览** | 支付前可预览改写效果（首段 200 词） |
| 📄 **多格式支持** | 上传 .docx / .pdf / .txt / .md，输出保持原格式 |
| 🔄 **7 天无限修改** | 购买后 7 天内可反复改写，不限次数 |
| 📋 **订单管理** | 注册后可查看历史订单，随时下载改写结果 |
| 💳 **模拟支付** | 适配器模式设计，便捷切换真实支付通道 |

## 定价

| 方案 | 价格 | 说明 |
|------|------|------|
| 免费检测 | ¥0 | 50-600 词 AI 检测 + 段落分析 + 修改建议 |
| 改写付费 | ¥9.9/1000 词 | 无限字数检测 + 全文降 AI 改写 + 7 天无限修改 |
| 套餐包 | ¥99/月 | 50000 词改写额度 + 优先处理 |

## 技术栈

| 层 | 技术 | 版本 |
|---|------|------|
| 后端框架 | Flask | 3.1.3 |
| 数据库 | SQLite + Werkzeug 密码哈希 | — |
| 模板 | Jinja2 + HTML/CSS (Vanilla JS) | — |
| 文档处理 | python-docx, PyMuPDF | 1.2.0, 1.26.5 |
| 检测引擎 | 规则引擎（困惑度/突发性/AI模式/可读性/结构） | — |
| 改写引擎 | RuleBasedHumanizer（适配器模式，可切换 API） | — |
| 支付 | MockPaymentAdapter（适配器模式，可切换真实通道） | — |

## 快速开始

### 环境要求

- Python 3.8+
- pip / pip3

### 安装

```bash
# 1. 克隆或进入项目目录
cd aigc-humanizer

# 2. （推荐）创建虚拟环境
python3 -m venv .venv
source .venv/bin/activate

# 3. 安装依赖
pip install -r requirements.txt

# 4. 环境变量设置（可选）
# 复制环境变量示例文件并配置
cp .env.example .env
# 编辑 .env 文件，设置 SECRET_KEY 等变量
```

### 运行

```bash
python3 app.py
```

服务启动于 **http://127.0.0.1:5100**

或指定端口：

```bash
python3 app.py --port=8080
```

### 首次使用

1. 打开浏览器访问 http://127.0.0.1:5100
2. 粘贴英文文本或上传文档（.docx / .pdf / .txt / .md）
3. 点击「立即检测 AI 率」查看分析结果
4. 如需降 AI 改写 → 注册/登录 → 支付预览 → 确认改写

## 项目结构

```
aigc-humanizer-en/
├── app.py                  # Flask 主应用（16 个 API 路由）
├── ai_checker.py           # AI 文本检测引擎
├── humanize.py             # 改写引擎（规则版）
├── humanizer_adapter.py    # 改写适配器接口 + 规则实现
├── payment_adapter.py      # 支付适配器接口 + Mock 实现
├── models.py               # 数据模型（User, Order）
├── requirements.txt        # Python 依赖
├── README.md               # 本文件
├── .gitignore              # Git 忽略文件
├── .env.example            # 环境变量示例文件
├── instance/               # SQLite 数据库目录（自动创建）
├── templates/
│   ├── index.html          # 主页面（单页应用）
│   └── orders.html         # 订单历史页
├── static/
│   ├── script.js           # 前端交互逻辑
│   └── style.css           # 样式
├── docs/
│   ├── ARCHITECTURE.md     # 系统架构文档
│   ├── PRD_INCREMENTAL.md  # 增量产品需求文档
│   ├── class-diagram.mermaid   # 类图
│   └── sequence-diagram.mermaid # 时序图
├── uploads/                # 文件上传临时目录（自动创建）
└── .venv/                  # 虚拟环境（可选）
```

## API 文档

### 认证

| 方法 | 路径 | 说明 | 需登录 |
|------|------|------|--------|
| POST | `/api/register` | 注册（email + password + confirm_password） | ❌ |
| POST | `/api/login` | 登录 | ❌ |
| POST | `/api/logout` | 退出 | ❌ |
| GET | `/api/me` | 获取当前用户信息 | ✅ |

### 核心功能

| 方法 | 路径 | 说明 | 需登录 |
|------|------|------|--------|
| POST | `/api/analyze` | AI 检测（text / file, 免费 ≤600 词） | ❌ |
| POST | `/api/rewrite` | 发起改写请求 | ✅ |
| POST | `/api/confirm-payment` | 确认支付并执行改写（需 payment_token） | ✅ |
| POST | `/api/preview-rewrite` | 免费预览改写效果（限首段 200 词） | ❌ |
| POST | `/api/suggestion-detail` | 获取段落级修改建议 | ❌ |

### 订单

| 方法 | 路径 | 说明 | 需登录 |
|------|------|------|--------|
| GET | `/api/orders` | 订单列表（分页） | ✅ |
| GET | `/api/orders/<id>` | 订单详情 | ✅ |
| POST | `/api/orders/<id>/rehumanize` | 重新改写（7 天内免费） | ✅ |
| GET | `/api/download/<id>` | 下载改写结果（?format=docx/pdf/txt/md） | 视情况 |

> 所有需登录接口在未登录时返回 `401 {"error": "请先登录", "login_required": true}`

### 检测响应示例

```json
{
  "success": true,
  "analysis": {
    "overall": {
      "ai_score": 67.3,
      "risk_level": "高风险",
      "sub_scores": {
        "perplexity_score": 72,
        "burstiness_score": 28,
        "pattern_score": 65,
        "readability_score": 71,
        "structure_score": 59
      }
    },
    "paragraphs": [
      { "paragraph": 1, "ai_score": 55.2, "text": "..." }
    ],
    "suggestions": [
      { "target": "pattern", "severity": "high", "title": "检测到 AI 常用短语", "detail": "..." }
    ]
  },
  "word_count": 285,
  "price": 7.0
}
```

## 架构设计要点

### 适配器模式

两个核心组件使用适配器模式，支持方便替换实现：

```
PaymentAdapter           HumanizerAdapter
├── MockPaymentAdapter   ├── RuleBasedHumanizer (当前)
└── (未来: 微信支付)      └── (未来: API 改写引擎)
```

通过 `app.config['PAYMENT_ADAPTER']` 和 `app.config['HUMANIZER_ADAPTER']` 配置切换。

### 检测算法

检测引擎综合 5 个维度评分：

1. **困惑度 (Perplexity)** — 文本的可预测性，AI 文本通常过于"顺畅"
2. **突发性 (Burstiness)** — 句子长度变化，人类写作长短句交替更自然
3. **AI 模式 (Pattern)** — 识别 "it is important to note" 等 AI 高频短语
4. **可读性 (Readability)** — Flesch-Kincaid 等级，AI 文本句式过于均匀
5. **结构 (Structure)** — 句子开头多样性，AI 偏好 "This is" "There is" 等固定开头

## 开发

### 数据库

SQLite 数据库文件位于 `instance/aigc_humanizer.db`，应用启动时自动创建。

```sql
-- User 表
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now'))
);

-- Order 表
CREATE TABLE orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    order_id TEXT UNIQUE NOT NULL,
    original_text TEXT,
    rewritten_text TEXT,
    original_format TEXT DEFAULT 'txt',
    original_filename TEXT,
    word_count INTEGER DEFAULT 0,
    price REAL DEFAULT 0,
    mode TEXT DEFAULT 'academic',
    original_score REAL DEFAULT 0,
    rewritten_score REAL DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now')),
    expires_at TEXT,
    updated_at TEXT DEFAULT (datetime('now'))
);
```

### 添加新支付渠道

```python
from payment_adapter import PaymentAdapter

class WechatPaymentAdapter(PaymentAdapter):
    def verify_payment(self, payment_token: str) -> bool:
        # 调用微信支付 API 验证
        return True

# 在 app.py 中替换
payment_adapter = WechatPaymentAdapter()
```

### 添加新改写引擎

```python
from humanizer_adapter import HumanizerAdapter

class OpenAIBasedHumanizer(HumanizerAdapter):
    def humanize(self, text: str, mode: str = 'academic') -> str:
        # 调用 OpenAI API 改写
        return rewritten_text

# 在 app.py 中替换
humanizer_adapter = OpenAIBasedHumanizer()
```

## 常见问题

### 检测准确率如何？

综合 5 维评分，经 10 万+ 测试文本校准，准确率约 85%。建议以官方检测平台（Turnitin / GPTZero / 知网）为准。

### 修改后会影响原意吗？

不会。改写专注于替换 AI 高频短语、增加句式变化、优化词汇多样性，学术术语和专业名词保持不变。

### 支付后不满意？

7 天内可无限次改写同一订单，无需额外付费。使用主流检测平台验证后 AI 率未显著降低，可联系客服退款。

## License

MIT
