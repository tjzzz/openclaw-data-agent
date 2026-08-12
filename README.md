# 芃芃工作室

芃芃工作室的工作空间：开发中项目、数据分析技能包、Agent配置与项目代码。

## 项目

| 项目 | 说明 | 技术栈 |
|------|------|--------|
| [aigc-humanizer-en](./aigc-humanizer-en/) | Huma — 英文内容 AI 风险检测与自然化改写 Web 应用，支持三种改写模式、多格式上传下载、文档结构保护、LLM 主备容灾、词数余额与支付宝支付 | Flask + SQLite + DeepSeek/OpenCode |
| [spider-leads](./spider-leads/) | 小红书需求线索监控平台（Spider-Man Web App），通过 xiaohongshu-mcp 搜索高热帖子、业务匹配、导出 CSV | Flask + xiaohongshu-mcp |

## Huma 当前能力

- 支持粘贴英文文本，以及上传 Word、PDF、TXT、Markdown 文件。
- 提供精细、标准、快速三种改写模式，保护标题、参考文献、数字、引用和专业术语。
- 支持 DeepSeek 官方与 OpenCode 等 OpenAI-compatible 服务，可配置付费改写 API 作为自动备用服务。
- 外部改写请求统一处理长文本切块、重试、进程级并发限制和请求间隔控制。
- 改写任务异步执行并展示真实进度；支付成功后的任务支持延迟重投和服务重启恢复。
- 支持用户词数余额、激活码充值、支付宝支付、订单记录和结果下载。

详细的安装、配置、架构和待办事项见 [aigc-humanizer-en/README.md](./aigc-humanizer-en/README.md)。
