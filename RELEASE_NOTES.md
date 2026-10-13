# 好奇猴快传 v1.2.0 · AI 接入与访问日志

本次升级让好奇猴快传可以被 AI 工具调用，同时保持原有网页操作方式。

- **AI 接入**：私人快传设备管理可创建/撤销 AI 接入令牌；AI 可发送文字、文件、读取最新内容，不得管理配对码和设备。
- **通用 MCP / AgentDock**：仓库 `integrations/hamoki-private-ai` 包含跨平台 Python CLI、MCP stdio 服务和使用指南，不限 AI 模型和客户端。
- **粘贴即发送**：私人快传文字框粘贴文字就自动发送；普通输入及文件选择仍点击发送。
- **访问日志**：页脚新增按日期查看访问 IP、操作和失败状态的日志页，使用已有上传口令查看。
- **原有保护不变**：公开分享每份最多 10 次领取；访客每 IP 滚动24小时最多 1 GiB 公开上传，总容量默认 10 GiB。

### 如何给 AI 授权？

在已配对设备进入「设备管理 → AI 工具接入」，生成一次性可复制的令牌，再在自己的 AI 客户端环境设置 `HAMOKI_BASE_URL` 与 `HAMOKI_AGENT_TOKEN`。**不要把实际令牌或私人域名凭证提交到 GitHub。**

文档：[项目 README](https://github.com/xiaohouzidoudou/hamoki-transfer) · [AI 接入教程](https://github.com/xiaohouzidoudou/hamoki-transfer/tree/main/integrations/hamoki-private-ai)

**限制**：电脑锁屏时只要后台 Agent 在线且有权限，仍能发送文件；睡眠/关机时无法使用。AI 工具不自动读取未授权剪贴板、软件窗口或推送手机后台通知。
