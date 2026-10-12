# 好奇猴快传

一个从零编写的极简网页临时传输工具。电脑上传文件，自动生成 **12 位取件码与二维码**，手机扫码即可领取。无需安装客户端、无需注册，也不需要 Telegram 或代理。

**项目名称：** 好奇猴快传（Hamoki）  
**技术：** Python、Flask、SQLite、原生 HTML / CSS / JavaScript  
**许可证：** MIT

## 功能

- 支持文件上传以及短文字传递
- 可选保存时间：1 小时、24 小时、7 天
- 每个取件码最多领取 5 次；取件码使用安全随机数生成
- 服务端生成二维码，另一台设备扫码领取
- SQLite 保存记录，文件保存在服务器本地
- 发送方凭私密链接上传；接收方只需取件码，无须登录
- 上传大小限制、总存储容量限制及按 IP 请求限流
- 下载文件强制以附件形式提供，避免直接在站点执行文件内容

## Docker 部署

```sh
cp .env.example .env
# 在 .env 中配置 UPLOAD_SECRET、PUBLIC_URL
mkdir -p data && sudo chown 10001:10001 data
docker compose up -d --build
```

建议在 1Panel 或 Nginx 等反向代理后通过 HTTPS 使用，把域名转发到 `127.0.0.1:8018`。例如把 `PUBLIC_URL` 设置为 `https://send.example.com`。

**发送方私密链接（不得公开）：**

`https://send.example.com/#key=YOUR_UPLOAD_SECRET`

首次打开后，浏览器会把密钥保存在当前标签页的会话存储中，并从地址栏清除。上传请求使用请求头提交密钥。**接收方不需要密钥**，只用这样的领取链接：

`https://send.example.com/?code=THE_CODE`

不要在截图、聊天记录或公开网页中泄露私密链接。在多人共用的电脑上，不建议长期保留带上传密钥的浏览器会话。需要撤销上传权限时，修改服务器里的 `UPLOAD_SECRET`。

## 安全提示

- 上传密钥至少 24 个字符；可用 `openssl rand -hex 32` 生成
- `.env` 包含私密配置，不要提交到 GitHub
- 文件并非端到端加密，服务器管理员可以访问存储内容
- 上线前需要配置 HTTPS、反向代理的上传大小限制、磁盘配额及备份
- 内置限流适合单实例轻量使用；高流量部署需加反向代理限流
- 只有在有权传输相关文件时，才使用本服务

## 本地开发

```sh
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt pytest
export UPLOAD_SECRET="$(openssl rand -hex 32)"
export DATA_DIR=./data
flask --app app run --port 8000
pytest -q
```

## 开发原则

简单、独立、自行维护。第一版不加入复杂的账号系统、前端框架、云存储或者服务器间同步功能，有实际需要再添加。

这是原创实现，并非 FileCodeBox 的 Fork 或其源码复制。
