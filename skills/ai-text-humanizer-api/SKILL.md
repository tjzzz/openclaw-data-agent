---
name: ai-text-humanizer-api
description: 调用 ai-text-humanizer.com API 对英文 Markdown 报告进行去AI化处理，使其更自然、降低AI检测率
agent_created: true
version: 1.0.0
author: DuMate
created_date: 2026-05-09
---

# AI Text Humanizer API - 英文文本去AI化

## 技能目的

本技能调用 ai-text-humanizer.com 的 API，将英文 Markdown 报告进行去AI化处理，使其读起来更自然、更像人类写作，从而降低被 AI 检测器识别的概率。

## 使用场景

此技能应在以下场景触发：
- 用户需要对英文 Markdown 文档进行去AI化处理
- 用户希望降低文档的 AI 检测率（Turnitin、GPTZero 等）
- 用户需要将 AI 生成的文本转换为更自然的人类写作风格
- 用户提到 "ai-text-humanizer.com" 或 "humanizer API"

## API 信息

**API 端点**: `https://ai-text-humanizer.com/api.php`

**请求方式**: POST

**参数**:
- `email`: ai-text-humanizer.com 账户邮箱
- `pw`: 账户密码
- `text`: 需要处理的文本内容

**限制**:
- 需要 PRO 计划
- **每次请求最多 2000 words**
- 每分钟最多 60 次 API 调用
- 脚本会自动分段处理超过 2000 words 的文本

## 使用指南

### 1. 前置准备

使用本技能前，需要：
1. 安装 Python 依赖：`pip install requests`
2. 在 ai-text-humanizer.com 注册账户
3. 购买 PRO 计划
4. **安全存储凭据**（见下方说明）

**凭据存储方式（推荐）**:

**方式一：环境变量（推荐）**
```bash
# 设置环境变量后执行脚本
export AI_TEXT_HUMANIZER_EMAIL="your-email@example.com"
export AI_TEXT_HUMANIZER_PASSWORD="your-password"
python3 scripts/humanize.py input.md
```

**方式二：系统密钥链（最安全）**
```bash
# macOS Keychain
security add-generic-password -a "your-email" -s "ai-text-humanizer" -w "your-password"

# 使用时读取
export AI_TEXT_HUMANIZER_PASSWORD=$(security find-generic-password -a "your-email" -s "ai-text-humanizer" -w)
```

**安全提醒**:
- 绝对不要将真实密码写入任何代码文件
- 不要将凭据提交到 Git 仓库
- 定期更换密码

### 2. 执行处理

**支持两种输入方式**:

**方式一：文件输入**
```bash
# 处理文件（自动生成 output_humanized.md）
python3 scripts/humanize.py input.md

# 指定输出文件
python3 scripts/humanize.py input.md output.md
```

**方式二：直接文本输入**
```bash
# 直接处理文本（输出到控制台）
python3 scripts/humanize.py --text "This is the text to humanize..."

# 处理文本并保存到文件
python3 scripts/humanize.py -t "Your text here" -o output.md
```

**参数说明**:
- `input`: 输入文件路径
- `output`: 输出文件路径（可选，默认在原文件名后添加 `_humanized`）
- `-t, --text`: 直接输入文本内容（不读取文件）
- `-o, --output`: 输出文件路径（与 `--text` 配合使用）

### 3. 大文件处理策略

对于超过 2000 words 的文档，脚本会：
1. 按段落智能分割文本（保持 Markdown 格式）
2. 每个分段不超过 2000 words
3. 分批次调用 API（每次间隔 1.2 秒，避免频率限制）
4. 合并处理结果并保持原有格式

### 4. 验证结果

处理完成后建议：
1. 使用 Turnitin 或 GPTZero (https://gptzero.me/) 检测 AI 率，对比处理前后的变化
2. 检查语义是否保持完整
3. 评估文本自然度和可读性

## 工作流程

```
输入方式选择
    ├─ 文件输入 → 读取文件内容
    └─ 文本输入 → 直接使用文本
         ↓
    统计单词数
         ↓
    判断是否超过 2000 words
         ├─ 否 → 单次 API 调用
         └─ 是 → 智能分段 → 多次 API 调用
              ↓
         合并处理结果
              ↓
    输出方式选择
         ├─ 指定输出文件 → 保存到文件
         └─ 未指定 → 输出到控制台
```

## 注意事项

### 技术限制
- **每次请求最多 2000 words**（API 硬性限制）
- API 有频率限制（60次/分钟），脚本会自动等待 1.2 秒
- 超过 2000 words 的文本会自动分段处理
- 处理时间取决于文本长度和 API 响应速度

### 质量保证
- API 会保持原文的核心语义
- 处理后的文本更自然、更像人类写作
- 建议人工审核处理结果

### 费用说明
- 需要 ai-text-humanizer.com 的 PRO 计划
- 具体定价请参考: https://ai-text-humanizer.com/pricing/

## 错误处理

脚本会处理以下常见错误：
- 认证失败：检查邮箱和密码是否正确
- 频率限制：自动等待后重试
- 网络错误：显示错误信息并退出
- 文件不存在：提示用户检查路径

## 示例

**示例 1: 处理文件**

```bash
python3 scripts/humanize.py report.md

# 输出:
# 📄 Processing: report.md
# 📊 Text length: 12,500 characters, 2,500 words
# 📦 Split into 2 chunks for processing
#   [1/2] Processing chunk (2,000 words)...
#   ✓ Chunk 1 done
#   [2/2] Processing chunk (500 words)...
#   ✓ Chunk 2 done
#
# ✅ All chunks processed! Result saved to: report_humanized.md
```

**示例 2: 直接处理文本**

```bash
python3 scripts/humanize.py --text "This is AI-generated content that needs to be humanized to sound more natural."

# 输出:
# 📄 Processing text input...
# 📊 Text length: 89 characters, 16 words
# 🚀 Calling API...
# ✅ Success!
#
# ============================================================
# RESULT:
# ============================================================
# This is AI-generated content that has been humanized to sound more natural...
```

**示例 3: 处理文本并保存**

```bash
python3 scripts/humanize.py -t "Your text here" -o result.md
# ✅ Result saved to: result.md
```

**示例 4: 指定输出路径**

```bash
python3 scripts/humanize.py input.md /path/to/output.md
```

## 相关资源

- API 文档: https://ai-text-humanizer.com/humanize-api/
- 定价页面: https://ai-text-humanizer.com/pricing/
- 免费试用: https://ai-text-humanizer.com/

## 与其他 skill 的区别

- `humanize-ai`: 基于开源工具和本地脚本，免费但效果可能不稳定
- `ai-text-humanizer-api` (本技能): 使用商业 API，效果更稳定但需要付费
- `ai-text-detector`: 用于检测文本的 AI 率，不进行改写
