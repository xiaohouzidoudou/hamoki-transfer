---
name: hamoki-private-ai
description: Use when a user explicitly asks an AI to send text or a specific authorized file from an AgentDock-connected computer/VPS into their paired Hamoki private transfer room, or read that room's latest text and file metadata. It also provides a local stdio MCP server for other AI clients; it must not access unrequested files or extract unrelated clipboard data.
---

# Hamoki Private AI

This integration connects an authorized AI tool to a **paired private Hamoki room**. Supported actions: `send_text`, `send_file`, `get_latest`, `status`.

1. In a **paired browser**, open **设备管理 → AI 工具接入 → 生成接入令牌**, then copy the displayed one-time token.
2. Configure `HAMOKI_BASE_URL` with the deployment's root HTTPS URL and `HAMOKI_AGENT_TOKEN` with the issued token **only in the local AI agent environment**. Do not reveal them in chat, public code, logs or process arguments.
3. For AgentDock execute `python run.py` (Windows) or `python3 run.py` (Linux) on the **device that holds the requested file**, passing one JSON object via `stdin`. Example: `{"skill_action":"send_text","text":"Please copy this on my phone"}`.
4. For a standalone MCP integration launch `python mcp_server.py` as a **stdio** child process, with the same environment variables. It advertises tools `send_text`, `send_file`, `get_latest`.
5. Revoke compromised or retired AI tokens from the existing browser's Device Management screen.

## Constraints

- Only use the file/text explicitly requested by the user. Never scan entire disks, extract passwords, keys, confidential source or browser credentials.
- AI tokens authorize reading and sending **only**; they cannot manage devices, issue new credentials, or regenerate pairing codes.
- Sending a new item **overwrites** the last private-room item. A failed or timed-out upload may have succeeded; call `get_latest` before any retry.
- The PC must have an online, authorized background agent. Locking the screen is compatible with background file access, but sleep/shutdown or locked desktop applications may prevent it.
- This feature does not independently read clipboard contents, scan windows or push mobile notifications. **Pasting text in the web private textbox triggers immediate send**, while manual typing and file selection still use the Send button.
- Server does not provide end-to-end encryption; use HTTPS and a trustworthy self-hosted instance. Limit 64KiB for text and up to 5GiB per file subject to server capacity.
