# 好奇猴快传 · 独立部署指南

本指南适用于通过 GitHub 下载源码、在**自己的服务器**部署好奇猴快传的使用者。**域名、SSL 证书、DNS、数据存储、设备配对空间都由部署者自行管理**；不会自动连接仓库作者的正式服务。

## 1. 准备条件

- 一台可运行 Docker 与 Docker Compose v2 的 Linux 主机。
- 若要公网使用：一个解析到自己服务器的域名、可用的 HTTPS 反向代理（Nginx/Caddy/1Panel 等）。
- 足够的磁盘空间；默认上传限额单次为 5 GiB、存储配额为 10 GiB，上传缓冲还需要额外空间。
- 尽量使用单个应用实例，避免并行运行多个持有各自内存限流器的进程。

`compose.yaml` 默认把服务绑定在 `127.0.0.1:8018`，不会直接公开 8018 端口给互联网访问。已有程序占用该端口时，请修改 `compose.yaml` 左侧主机端口，并同步修改代理设置。

## 2. 下载并启动

```bash
git clone https://github.com/xiaohouzidoudou/hamoki-transfer.git
cd hamoki-transfer
cp .env.example .env

# 使用自己的实际地址，示例只是占位符
# 用编辑器设置 PUBLIC_URL=https://send.example.com

mkdir -p data upload-tmp
sudo chown 10001:10001 data upload-tmp

docker compose up -d --build
docker compose ps
curl -fsS http://127.0.0.1:8018/health
```

预期健康接口返回 `{"ok":true}`。如果这里不通，先检查 `docker compose logs --tail=100 hamoki`，再排查域名与代理。

常用 `.env` 配置：

| 配置项 | 示例默认值 | 用途 |
| --- | --- | --- |
| `PUBLIC_URL` | `https://send.example.com` | 公开分享时二维码/链接使用的公开地址 |
| `MAX_UPLOAD_MB` | `5120` | 单个 HTTP 上传请求的最大文件字节数（单位 MiB） |
| `TOTAL_LIMIT_MB` | `10240` | 公开分享与私人空间合计的文件容量配额（单位 MiB） |
| `GUEST_DAILY_MB` | `1024` | 每个访问 IP 在滚动 24 小时内允许的公开上传量（单位 MiB） |
| `UPLOAD_UNLOCK_PASSWORD` | *空* | 上传额度用完后使用的口令，必须在你自己的 `.env` 中配置，不要提交到公开仓库 |

修改配置后执行 `docker compose up -d` 让容器使用新的配置。**未设置 `UPLOAD_UNLOCK_PASSWORD` 时，普通访客用完额度后不能解锁**；不要在公开仓库示例中填写真实口令。使用较长且随机的口令，并确保 `.env` 文件仅管理员可读。

## 3. 域名与 HTTPS

1. 在你的 DNS 服务商处，为 **你自己的域名** 添加 A/AAAA 记录，解析到自己服务器。
2. 通过已有 1Panel、Nginx 或 Caddy 为这个域名创建 HTTPS 站点并申请有效 TLS 证书。
3. 把根路径 `/` 反向代理到 `http://127.0.0.1:8018`；保留原始 Host，并正确设置 `X-Forwarded-Proto`。
4. 将 `.env` 中的 `PUBLIC_URL` 设置成同一个 `https://...` 地址。
5. 打开 `https://send.example.com/health` 检查响应，再测试手机与电脑配对、分享/下载。

可参考的 Nginx **配置片段**（假定 TLS 证书已经由你自己的系统配置；不是可直接复制的完整 TLS 站点）：

```nginx
# 放在你现有的 HTTPS server { } 内
client_max_body_size 5122m;

location / {
    proxy_pass http://127.0.0.1:8018;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;

    proxy_request_buffering off;
    proxy_read_timeout 3600s;
    proxy_send_timeout 3600s;
}
```

`client_max_body_size`、上传超时和流式代理行为必须根据你实际使用的网关配置。若前面还有 CDN 或其他反代，**它们的最大请求体限制也必须允许你的目标文件大小**；任何中间节点限制较低时，上传仍可能失败。

> 私人设备使用 Secure Cookie，需要在真实 HTTPS 站点验证。HTTP 本地测试不代表公网 HTTPS 下的自动配对行为。优先使用独立子域名部署，不建议直接部署在 `/subpath/` 等 URL 子路径。

## 4. 首次使用和设备管理

- 默认进入「私人快传」，创建配对空间，然后在「设备管理」直接查看并复制配对码。
- 手机、电脑等其他浏览器访问**同一个域名**，输入配对码即可绑定；每个空间最多 8 台。
- 此后可双向传文字与文件。打开网页能看到共享空间的最新一条；发送新内容会替换旧内容。
- 设备管理支持改名与解绑。仅服务器端配对关系长期保留；浏览器 Cookie 丢失后仍需重新加入。
- 「寄文件 / 取文件」是独立的公开分享模式，不需要登录，但任何访问者也可以公开上传，请酌情限制公网访问。

### 访问日志与保护

部署成功后，网页底部有「访问日志」入口，也可以直接访问你**自己的域名**下的 `/admin/logs`。它会先显示口令输入框：

1. 在服务器自己的 `.env` 中配置 `UPLOAD_UNLOCK_PASSWORD`（**不需要另设日志密码**）。配置生效后，日志功能复用这个口令。
2. 打开日志页，输入上述口令，点击「查看日志」。
3. 选择日期后查看访问次数、不同 IP 数、成功上传、失败/拒绝，以及每条访问记录；可以刷新、加载更多或退出查看。

日志数据接口 `/api/admin/summary` 与 `/api/admin/events` 在未登录时返回 HTTP 401。登录凭证为浏览器的 HttpOnly、SameSite=Strict 签名 Cookie，最多保留 12 小时；输入错误的口令会被拒绝，频繁登录尝试受基础频率限制。如果未配置 `UPLOAD_UNLOCK_PASSWORD`，管理员无法登录日志。

**日志记录范围**：访问首页、公开上传、公开/私人文件下载、设备配对/解绑/改名、未知路径请求和一些失败操作。不会记录文件内容、上传文字、密码、配对码、分享令牌或请求的 URL 查询参数。静态文件、健康检查及部分频繁轮询接口不采集，减小日志噪声。日志于安装该功能后开始产生，**不能反向恢复以前没记录的访问**。

**保留规则**：数据存放于 `./data/index.sqlite3` 的 `audit_events` 表，约保留 30 天，最多约 25,000 条；清理由后续访问触发，不保证每条记录在恰好第 30 天即时删除。密码签名使用 `./data/.audit-session-secret`，该文件应随 `data/` 一起备份，绝对不要提交到公开 GitHub。

**安全提醒**：公开上传的解锁口令**也能查看访问日志**，请不要随意告诉陌生人。日志中的 IP 有可能是代理地址或共享出口；429、403 等错误只是异常访问线索，并不能单独证明攻击。公网运营应遵守当地适用的隐私与日志保留要求。

## 5. 备份与恢复

至少备份 `./data/` **整个目录**，包括：

- `index.sqlite3`：公开分享信息、私人房间、设备绑定等记录；
- `files/`：公开分享文件；
- `private-files/`：私人空间当前文件；
- `.private-invite-secret`：私密配对码派生密钥，**不要提交到公开 GitHub**；
- `.upload-access-secret`：上传口令登录 Cookie 和访客 IP 匿名索引使用的实例私钥，不可公开；
- `.audit-session-secret`：访问日志管理员会话的签名密钥，不可公开。

SQLite 运行期间请使用 SQLite 的在线备份 API，或者先停止服务再复制数据库。单纯复制正在写入的 `index.sqlite3` 可能无法获得一致备份。实际灾备还应包含 `compose.yaml`、配置文件和 HTTPS/代理配置（凭据须单独安全保存）。

恢复前先停止目标服务，确保恢复的数据库、上传文件和密钥是一套匹配的备份。运行状态数据**不会随着 `git clone` 从仓库下载**。如果恢复时丢失了旧配对密钥，原配对码可能需要更新；老设备是否仍可正常访问取决于原数据库和浏览器凭证是否完整。

`upload-tmp/` 仅用于上传过程缓冲，不应被当作持久数据备份；部署时需要单独创建并授予容器用户可写权限。

## 6. 更新与常见问题

更新源码前先完成数据备份，然后在确认没有未提交的本地改动时：

```bash
git pull --ff-only
docker compose up -d --build
docker compose ps
curl -fsS http://127.0.0.1:8018/health
```

- **网页打不开**：检查 DNS、TLS 证书、Nginx/1Panel 代理、容器启动状态及目标端口。
- **上传太大失败**：检查 Docker、Nginx、CDN 和客户端的限制，确认磁盘剩余空间与 `upload-tmp/` 权限。
- **刷新后设备不再配对**：核查 HTTPS、Cookie/浏览器清理规则，必要时使用设备管理里的配对码重新绑定。
- **配对码与原来不同**：旧版本可能只保留过配对码的单向校验值，更新后可重新生成，新码会覆盖旧码，已绑定的设备凭证不因此失效。
- **多个设备出现不同内容**：确认它们确实访问同一域名、绑定同一个私人空间，并排除浏览器缓存。
- **访问日志打不开或无法查看**：确认 `/admin/logs` 路径由反向代理转发；检查 `UPLOAD_UNLOCK_PASSWORD` 是否已在容器中生效。未登录访问日志 API 返回 HTTP 401 是正常保护行为。
- **端口 8018 占用**：更改 `compose.yaml` 中的主机绑定端口，同时更新反代上游。

## 7. 安全事项

这不是端到端加密存储，运行服务器的人能访问上传数据；公开分享可匿名上传。请合理设置配额、定期备份、限制后台访问，并对高敏感内容使用更适合的传输方案。访客限额是以 IP 为单位的滚动24小时累计量，多个用户共用出口 IP 会共享额度，切换 IP 也可能规避额度，不能代替 CDN/WAF 限流和带宽防护。上传口令解锁后的浏览器 Cookie 有效期约24小时。

GitHub 上公开的是应用源码，不要上传 `.env`、`data/`、私钥或实际的 SSH/运维配置。
