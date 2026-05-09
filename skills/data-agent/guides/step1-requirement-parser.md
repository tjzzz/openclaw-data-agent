# Step 1: 读取任务需求与项目初始化

---

## 需求文件类型

| 文件 | 提取要点 |
|------|---------|
| **作业简介表.doc** | 字数、格式(Essay/Report)、参考文献数量 |
| **任务需求.pdf/.docx** | 分析目标、数据来源、deadline |
| **参考资料** | 格式规范、评分标准 |

---

## 约束提取

### 必须提取的信息

| 约束 | 来源 | 示例 |
|------|------|------|
| 字数 | 作业简介表 | 2000 words |
| 格式 | 作业简介表 | Essay / Report |
| 引用格式 | lecture课件 | APA / MLA / Harvard |
| 工具要求 | 任务需求 | Excel, Power BI |
| Deadline | 作业简介表 | 2026-05-31 |

### 提取方法

统一使用 `scripts/setup_env.py`，自动探测可用工具，不需要手动试：

```bash
# 首次运行先检查环境（自动安装依赖）
python3 scripts/setup_env.py --check

# 提取任意格式文件（统一接口，支持 .doc/.docx/.pdf/.pptx/.txt/.md）
python3 scripts/setup_env.py --extract "作业简介表.doc"
python3 scripts/setup_env.py --extract "assignment.pdf"
python3 scripts/setup_env.py --extract "lecture.pptx"
```

> 脚本会自动选择对应工具（antiword / PyMuPDF / python-pptx），无需手动判断。

---

## 项目初始化

### 创建项目

```bash
python3 scripts/init_project.py "项目名称" [字数]

# 示例
python3 scripts/init_project.py "ISO2036_Report" 2000
```

### 生成的 project.yaml

```yaml
project:
  id: "20260509_ISO2036_Report"
  name: "ISO2036_Report"
  created_at: "2026-05-09T14:00:00"

requirements:
  word_count:
    target: 2000
    min: 1800
    max: 2200
  format:
    type: "Report"
    citation_style: "APA"
  tools:
    required: []
  deadline: ""

ai_checks: []

delivery:
  final_file: ""
  delivered_at: ""
```

### 完善配置

如需补充信息，直接编辑 `project.yaml`：
```bash
cd ~/.workbuddy/workspace-data-agent/projects/2026-05-09_xxx
vim project.yaml
```

---

## 付费需求登记（飞书）

### 登记信息

| 字段 | 值 |
|------|-----|
| 订单id | 项目目录名，如 `2026-05-09_Credit_Card_Debt_Intervention` |
| 收入 | 字数 × 350元/千字 |
| 月份 | 当前月份 |
| 任务截止日期 | 客户要求 |
| 写手 | zzzheng / Eden |
| 订单来源 | 客户来源 |

### 登记命令

```bash
# 从 project.yaml 提取信息后登记
NODE_OPTIONS="" lark-cli base +record-upsert \
  --base-token K5SXbNDiWaiYO4s6EWhcPn2unef \
  --table-id tblQ1965U6EyRAIq \
  --json '{
    "订单id": "<项目目录名>",
    "收入": 613,
    "成本": 0,
    "月份": "2026-05-01 00:00:00",
    "任务截止日期": "2026-05-14 00:00:00",
    "写手": ["zzzheng"],
    "订单来源": "xxx",
    "是否结单": "否",
    "备注": "项目名称 - 2000字"
  }'
```

> ⚠️ lark-cli 需提前安装配置

---

## 任务确认

向客户确认：

```
📊 任务需求已读取

✅ 任务：xxx分析，2000字
✅ 格式：Report，APA引用
✅ 工具：Excel, Power BI
✅ 截止：2026-05-31
✅ 输出：projects/2026-05-09_xxx/

确认后开始执行？
```

---

## 常见问题

**Q: 需求文件格式不支持？**
手动提取关键信息填入 project.yaml

**Q: 飞书登记失败？**
- 检查 lark-cli 安装
- 检查网络连接
- 手动到飞书表格登记

**Q: 约束冲突？**
以**作业简介表**为准
