# Hamoki Private AI · AgentDock / MCP

让有权限的 AI 工具直接把本机的一段文字或指定文件送入**已经配对的私人快传空间**，在手机打开同一个私人空间即可读取最新内容。**AI 工具无法通过令牌管理配对设备或邀请码。**

## 1. 在网页生成 AI 令牌

在已经配对的 Hamoki 设备打开 **设备管理 → AI 工具接入 → 生成接入令牌**，立即复制生成的 `hka_...`。每个私人空间最多生成 5 个 AI 令牌，可随时撤销，原始明文只显示一次。不要把令牌发到聊天窗口、截图或公开仓库。

## 2. 配置需要执行任务的 AI 设备

在 **真正持有目标文件的电脑**（也可以是可访问该电脑指定文件的授权 AgentDock 节点）设置两个本地环境变量：

| 变量 | 意义 |
| --- | --- |
| `HAMOKI_BASE_URL` | 你自己的私人快传 HTTPS 网站根地址，例如 `https://transfer.example.com` |
| `HAMOKI_AGENT_TOKEN` | 从配对设备管理页生成的 AI 访问令牌 |

令牌保存到该设备私有的 AgentDock 环境配置或本机秘密存储，不要写进 GitHub 和普通用户消息。Python 3.10+ 自带的标准库即可运行客户端和 MCP，不需要安装依赖。

## 3. AgentDock Skill / CLI 调用

下载本目录，将 `SKILL.md` 作为 AI 工具指引；调用程序时从标准输入传入一条 JSON 指令。

```json
{"skill_action":"send_text","text":"把这段文字同步到我手机"}
```

```json
{"skill_action":"send_file","file_path":"D:\\Documents\\report.txt"}
```

```json
{"skill_action":"get_latest"}
```

使用 AgentDock `exec_command` 时应把 JSON 放在 `stdin`，不要拼接进 Shell 命令行。Windows 使用 `python run.py`，Linux 使用 `python3 run.py`，执行位置应当是实际存有目标文件的设备。另一端手机无需执行 AI 程序，只需要打开已配对的私人快传网页。

## 4. 通用 MCP 客户端

MCP 客户端配置一个本地 stdio 进程：

```json
{
  "mcpServers": {
    "hamoki-private": {
      "command": "python",
      "args": ["<本地目录>/mcp_server.py"],
      "env": {
        "HAMOKI_BASE_URL": "https://transfer.example.com",
        "HAMOKI_AGENT_TOKEN": "<你的私有AI令牌>"
      }
    }
  }
}
```

上面只是示意配置，**不要提交填有真实令牌的 MCP JSON 到公开仓库**。工具暴露三个命令：`send_text`、`send_file`、`get_latest`。不同 MCP 客户端的配置路径、启动方式可能不同。

## 边界与注意事项

- 无需电脑屏幕解锁，但**电脑必须开机、联网且后台 Agent 运行**。锁屏不等于自动拥有读取剪贴板/窗口内容的权限。
- `send_text` 需要 AI 已经获取用户明确提供的文字，`send_file` 需要明确路径及权限；工具本身不会主动搜索所有磁盘或监控剪贴板。
- 发送新的私人内容会覆盖空间原来的最新一条；上传失败可能发生在服务端已保存之后，不要自动重复上传，先调用 `get_latest` 确认。
- 上传口令与设备配对码**不是** AI 令牌，不能拿来代替，也不应该给 AI 公开。
- 浏览器私人快传文字框支持**粘贴文字后立即发送**；单纯键盘输入或选择/拖拽文件仍需点击「发送」。
- 内容不是端到端加密，服务端可读取数据。下载文件仍需要在已配对网页中点击下载。
