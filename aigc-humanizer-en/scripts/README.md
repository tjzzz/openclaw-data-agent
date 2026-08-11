# 运维脚本

## 飞书个人告警

`feishu_alert.py` 使用企业自建应用机器人给指定人员发送单聊消息，并可追加应用内加急或电话加急。

### 环境变量

```bash
export FEISHU_APP_ID='cli_xxx'
export FEISHU_APP_SECRET='xxx'
export FEISHU_ALERT_OPEN_ID='ou_xxx'
```

### 调用

```bash
# 普通消息
python3 scripts/feishu_alert.py '[Huma] 测试告警'

# 应用内加急
python3 scripts/feishu_alert.py '[Huma] 改写主服务已熔断' --urgent app

# 电话加急
python3 scripts/feishu_alert.py '[Huma] 主备改写服务全部失败' --urgent phone
```

应用需要启用机器人能力并发布版本，告警接收人必须位于应用可用范围内。应用还需要申请“以应用身份发送消息”以及对应的“发送应用内加急”或“发送电话加急”权限。电话加急会消耗企业额度。

## 文档文件清理

`cleanup_document_files.sh` 默认删除 `instance/source_docs/` 和 `instance/output_docs/` 中超过 7 天的文件。通过 `RETENTION_DAYS` 调整保留天数。

## 独立测试改写 API

`test_humanizer_api_standalone.py` 不导入项目代码，也不读取 `config.py`。它使用脚本内的测试文本发送一次请求，并打印 HTTP 状态和返回正文。

```bash
export AI_TEXT_HUMANIZER_EMAIL='your-email'
export AI_TEXT_HUMANIZER_PASSWORD='your-password'

python3 scripts/test_humanizer_api_standalone.py
```
