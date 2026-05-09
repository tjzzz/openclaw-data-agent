# Step 3: AI检查和降低AI率

---

## 三级降重策略

```
L1: 免费工具 (turnitin-ai-checker humanize.py)
  ↓ AI率 < 20% → 完成 ✅
  ↓ AI率 ≥ 20%
L2: 手动优化 (拆分长句、简化词汇)
  ↓ AI率 < 20% → 完成 ✅
  ↓ AI率 ≥ 20%
L3: 付费API (ai-text-humanizer-api) — 需经过用户确认，且仅发高风险段落
  ↓
最终验证
```

> ⚠️ **付费 API 额度有限，仅当 L1+L2 都无效时才调用 L3。且发送前需要用户确认**
> 调用时只发送 AI 率高的段落，不要整篇发送。

---

## 流程

```
初稿检测 → 定向处理 → 验证 → 字数调整
```

---

## 1. 检测

加载 `@skill:turnitin-ai-checker`，然后执行：

```bash
ai_checker.py --file output/essay_draft.md
```

⚠️ 工作目录：`~/.workbuddy/workspace-data-agent/projects/日期_项目名称/`

### 关键指标

| 指标 | 阈值 | 含义 |
|------|------|------|
| `readability_score` | > 25 | 句子复杂度过高 |
| `avg_sentence_length` | > 15 | 句子太长 |
| `pattern_score` | > 5 | AI短语过多 |
| `ai_score` | < 20 | 目标达标线 |

---

## 2. 定向处理

### 决策

| 主因 | 处理方式 |
|------|---------|
| 词汇问题 | 加载 skill 自动处理 |
| 句长问题 | 手动拆分长句 (>15词) |
| 复合问题 | skill + 手动结合 |

### 处理

加载 `@skill:turnitin-ai-checker` 或 `@skill:humanize-ai`，执行降重脚本：
```bash
# 输入文件 → 输出文件
humanize.py output/essay_draft.md output/essay_humanized.md
```

### 手动处理（句长问题）

拆分超过15词的长句：
```
原句："This is a very long sentence that contains too many words..."
拆分："This is a shorter sentence. It contains fewer words."
```

---

## L3: 付费 API（仅限最后手段，且需要用户确认）

### 何时使用
L1 自动降重 + L2 手动优化后，AI 率仍 ≥20%。

### 操作方式

**Step 1 — 找出高风险段落**
用 `ai_checker.py` 的段落分析结果，确定 AI 率最高的段落。

**Step 2 — 仅提取高风险文本**
将高风险段落单独提取出来，不要发送整篇文章。

**Step 3 — 调用付费 API**
```bash
# 仅处理高风险文本片段
AI_TEXT_HUMANIZER_EMAIL="your-email" \
AI_TEXT_HUMANIZER_PASSWORD=$(security find-generic-password -s "ai-text-humanizer" -w | tr -d '\n') \
python3 <skill_path>/scripts/humanize.py high_risk_section.md
```

**Step 4 — 替换回原文**
用 API 处理后的段落替换原文中的对应部分。

**Step 5 — 验证**
```bash
ai_checker.py --file essay_reassembled.md
```

### 重要规则
- 只发高风险段落，不提整个文档
- 先确认段落分离后语义完整，不会截断句子
- 处理后人工检查，确保原文逻辑、引用不受影响

## 3. 验证

加载 `@skill:turnitin-ai-checker`，执行检测：

```bash
ai_checker.py --file output/essay_humanized.md
```

### 结果判断

| AI率 | 操作 |
|------|------|
| < 20% | ✅ 达标，记录结果 |
| ≥ 20% | 升级到下一级处理（L1→L2→L3），每级**仅执行一次** |

### 迭代规则（重要）

```
L1 处理后 ≥20% → 进入 L2（不重跑 L1）
L2 处理后 ≥20% → 进入 L3（不重跑 L1/L2）
L3 处理后 ≥20% → ⛔ 停止，输出未达标报告
```

**每级只执行一次，不反复迭代。** L3 后仍不达标时，进入「未达标处理」流程。

---

## 4. 记录结果

```bash
# 记录检测历史（内置脚本）
python3 scripts/record_ai_check.py <项目目录> essay_draft.md 45 "sentence_length"
python3 scripts/record_ai_check.py <项目目录> essay_humanized.md 18
```

记录后 `project.yaml`：
```yaml
ai_checks:
  - date: "2026-05-09T14:00"
    file: "essay_draft.md"
    score: 45
    issues: ["sentence_length"]
  - date: "2026-05-09T15:00"
    file: "essay_humanized.md"
    score: 18
    issues: []
```

---

## 5. 字数调整

AI率达标后，检查字数：
- 目标范围：±10%
- 不足：补充分析内容
- 超出：精简冗余描述

---

## 完整流程速查

```bash
# 1. 检测 → 加载 @skill:turnitin-ai-checker
ai_checker.py --file output/essay_draft.md

# 2. 降重 → 加载 @skill:turnitin-ai-checker
humanize.py output/essay_draft.md output/essay_humanized.md

# 3. 验证 → 加载 @skill:turnitin-ai-checker
ai_checker.py --file output/essay_humanized.md

# 4. 记录（内置）
python3 scripts/record_ai_check.py . essay_draft.md 45
python3 scripts/record_ai_check.py . essay_humanized.md 18
```

---

## 未达标处理（最终终止点）

> ⛔ 仅当 L1+L2+L3 全部执行完毕后 AI 率仍高于 20% 时进入此流程。
> 此流程**不触发新的 API 调用或自动改写**，仅输出手工修改指引。

输出以下报告：

```
⚠️ AI率未达标（L1+L2+L3 已全部执行）

检测记录:
  L1 (humanize.py): 45% → 30%
  L2 (手动拆分): 30% → 25%
  L3 (付费API): 25% → 22%

建议手动处理:
1. 拆分以下长句 (>15词):
   - 第X段: "..." (XX词)
   - 第Y段: "..." (XX词)

2. 简化词汇:
   - utilize → use
   - demonstrate → show
```

用户确认后手动修改，重新从 L1 开始检测。

处理后重新检测。
