# 美国 VPS 开发测试环境：已部署

> 记录日期：2026-10-12。这里仅记录非敏感运行信息，不保存任何密钥或登录凭据。

## 在线地址和验证

- **公用测试中心首页**：https://dev.2858888.xyz/
- **好奇猴快传项目路径**：https://dev.2858888.xyz/kauichuan/
- 以后所有项目复用同一个 `dev.2858888.xyz` 域名，分别使用 `/项目名/`，不用每次申请新域名
- 静态界面预览：**https://xiaohouzidoudou.github.io/hamoki-transfer/**
- 美国 VPS 公开 IPv4：`104.233.200.159`
- DNS：`dev.2858888.xyz` A 记录指向上述 IPv4
- 公网 HTTPS 由现有 1Panel OpenResty 提供；`/` 静态开发测试中心；`/kauichuan/` 反向代理到宿主机 `127.0.0.1:8018`，无需开放 8018 端口
- Let's Encrypt 证书签发成功，证书到期时间为 2027-01-10；`acme.sh` 已安装证书和续期后的 OpenResty reload hook，宿主机现有 cron 定期运行 acme.sh
- 实际验证：从公司电脑打开网页、`/health`、CSS/JS 均返回 200；公网 HTTPS 文件/文字上传、取件码查询、SVG 二维码、文件字节完整性、文字领取全部通过，匿名上传返回 403

## 宿主机结构（非密钥）

- AgentDock 连接节点：`raksmart`，先使用经过授权的宿主机 SSH 网关，**不要把 AgentDock 容器的本地系统等同于 VPS 宿主机**
- 项目路径：`/opt/hamoki-dev/app`
- Compose 项目名称：`hamoki-dev`，容器：`hamoki-dev-hamoki-1`
- 仅监听宿主机 `127.0.0.1:8018` → 容器 `8000`
- 独立 SQLite 和临时文件：`/opt/hamoki-dev/app/data`
- 上传授权、大小限制和 `PUBLIC_URL` 等配置位于 `/opt/hamoki-dev/app/.env`，**该文件绝不提交公共仓库**，本项目使用私密链接进行上传授权，下载无需登录
- OpenResty 公共入口虚拟主机：`/opt/1panel/www/conf.d/dev.2858888.xyz.conf`
- 公共项目首页：`/opt/1panel/www/sites/dev.2858888.xyz/index/index.html`
- 项目反向代理规则目录：`/opt/1panel/www/sites/dev.2858888.xyz/projects/`（`kauichuan.conf` 为第一个项目）
- 前端 JS/HTML 使用相对路径及项目基本路径；快传在 .env 中的 `PUBLIC_URL` 为 `https://dev.2858888.xyz/kauichuan`，二维码、复制的链接均含 `/kauichuan/`
- 网站证书：`/opt/1panel/www/sites/dev.2858888.xyz/ssl/`
- HTTP 阶段配置备份：`/opt/hamoki-dev/dev.2858888.xyz.http.conf.bak`
- HTTPS `/kauichuan/health` 返回 200，HTTP 自动 301 跳转 HTTPS；原来根目录的 `/?code=XXXXXXXXXXXX` 分享链接自动 302 转到 `/kauichuan/?code=XXXXXXXXXXXX`
- **注意**：该域名直接通过 1Panel OpenResty 的挂载配置文件注册，而不是通过 1Panel 网站数据库新建；可能不会显示在 1Panel「网站」列表中。修改网站时需注意此项，不要在面板里建立同名冲突站点

## 如何迭代

1. 前端样式改动：提交 GitHub `main` 后 GitHub Pages 自动更新静态预览；先校验构建成功，再把固定预览链接发给用户
2. 完整前后端改动：先在开发分支测试；确认之后更新 **独立** Compose 项目 `hamoki-dev`，只重建这个服务，复查健康接口和关键操作
3. 备份/还原时保护 `data/`、独立 `.env`、虚拟站点配置和 SSL 续期安装状态；不要把私钥、上传密钥或数据库内容同步到公开 GitHub
4. 用户满意后才合并稳定版、发布 GitHub Release 和正式上线；开发测试 URL 不等于生产服务

## 以后新增其他项目

- **一个域名多个项目路径**：使用 `https://dev.2858888.xyz/项目名/`。根目录是项目入口列表，不再直接运行单个软件；不必给每个新项目重复申请 DNS 与证书。
- 每个新项目使用独立代码目录、Docker Compose 名、卷、端口和应用授权；例如将新应用绑定 `127.0.0.1:8020`，在 `projects/新项目.conf` 增加独立的 `location ^~ /新项目/`，配置代理去除项目前缀，并在公共首页添加项目入口。变更前备份、`openresty -t` 后再 reload，禁止覆盖其它站点和项目数据。
- 应用应支持被托管在子路径之下：静态资源、API、下载链接、二维码均使用项目路径，必要时配置对应的 URL 前缀。
- 在 AgentDock 使用模板 `hamoki-universal-dev-preview-release`，持续复用「需求 → 开发 → 在线预览 → 用户反馈 → 验收发布」
- 未经用户明确确认，不自动发布新的生产版本；正式站点验证完成之后，按照下线规则撤销对应项目路径、移除首页卡片，关闭该项目测试容器，不保留无用测试网站

## 后续注意

- 当前完整测试站的应用代码更新仍是人工执行，**并非每次 GitHub 提交都会自动重建 Docker**；未来可以单独增加可回滚的 CI/CD 发布。
- 不公开分享发送方私密上传链接。必要时通过受控设备或管理通道授权；公共页面直接访问仅支持取件及展示。

## 公共域名的浏览器安全边界

`/kauichuan/`、`/新项目/` 在同一个域名下，**它们共享浏览器同源权限**，包括 `localStorage`、`sessionStorage` 和非 Path 隔离的 Cookie。不可把来自不受信任的第三方项目直接部署在同一个公共开发域名；更不能在这个域名下测试真实敏感账户或生产密钥。需要严格安全隔离的项目，应单独使用测试子域名。

已验证：从公司电脑访问公共首页、`/kauichuan/` 和资源/健康接口均返回 200；公网 HTTPS 下上传、取件、二维码（编码新路径）、文件字节比对、匿名上传 403 和旧链接兼容跳转均通过。
## 何时停用项目测试路径

- `dev.2858888.xyz` 是永久共用的开发测试中心，**每个 `/<项目名>/` 是临时测试地址**。
- 只有用户验收满意，已经交付正式站点或最终产品且最终入口经真实检查正常，才开始回收其测试地址。**好奇猴快传当前仍处于测试中，不能现在回收**。
- 回收时先说明影响（仍有效的取件码、二维码和测试文件将无法继续从该路径领取），检查备份，再移除公共首页项目入口和对应 `projects/<项目名>.conf` 的代理路由；对于已下线的项目前缀应由网关明确返回 **410 Gone**（含接口、资源与下载），不能继续代理到容器；运行 `openresty -t` 后 reload，再从公网验证 410。
- 最后停止/移除该项目独立 Docker Compose 测试服务，并按已确认的保留期清理测试数据。保留必要的源码、正式构建、非敏感部署文档和恢复材料，不留下多余的活跃容器和公网地址。
- 旧根目录 `/?code=...` 的兼容重定向也须在相关项目下线时取消，避免继续指向已停用链接。其他项目路由与公共 HTTPS 域名不受影响。

## 开发测试域名闲时关闭（2026-10-12 更新）

需求约定：`dev.2858888.xyz` 是永久保留的统一开发域名，**没有在测试的项目时对外关闭**，只有需要测试才重新开放。各项目的 `/项目名/` 仅在测试期间存在，用户完成验收并迁移到正式版后不永久保留。

美国 VPS 已建立独立站点开关：

```sh
/opt/hamoki-dev/dev-control/dev-site.sh status  # 查询 online/offline 和活跃项目路由数
/opt/hamoki-dev/dev-control/dev-site.sh on      # 准备开始新项目时开启公共开发站
/opt/hamoki-dev/dev-control/dev-site.sh sync    # 依据 projects/*.conf 数量自动决定 online/offline
/opt/hamoki-dev/dev-control/dev-site.sh off     # 无活跃项目才允许关闭，拒绝误关运行中项目
```

- 控制脚本与在线/离线 Nginx 配置：`/opt/hamoki-dev/dev-control/`；每次实际切换前备份原虚拟主机文件到 `/opt/hamoki-dev/dev-control/backups/`，`openresty -t` 验证成功后才 reload。
- 在线配置为独立站点 `/opt/1panel/www/conf.d/dev.2858888.xyz.conf` 的备份快照。若管理员或 1Panel 修改了网站设置，脚本会识别当前配置与已知快照不同并拒绝覆盖，需要先人工审查及更新模板。
- 离线配置仅针对 `dev.2858888.xyz` 的 HTTP/HTTPS 请求返回 **Nginx 444**，保留 `/.well-known/acme-challenge/` 路径用于 Let’s Encrypt HTTP-01 续期；其余网站及 OpenResty 服务保持在线。主域名会继续解析到美国 VPS，TLS 仍握手但不提供网页。
- 禁止在还有项目路由时执行离线切换。用户确认最后项目完成后，先核对是否存在仍需要领取的文件及临时数据，移除项目代理规则/卡片，停止项目容器，再运行 `dev-site.sh sync`。
- 新项目使用时，通过授权的 AgentDock/SSH 通道执行 `on`，复用已有证书及路径路由能力，不再额外申请子域名。
- 已验证：脚本 `bash -n`、`status`、`on` 幂等、`sync` 在 1 个活跃项目时维持在线、`off` 在 1 个活跃项目时安全拒绝；离线 Nginx 配置通过独立 `openresty -t`。**当前因好奇猴快传仍在使用，未实际切到 offline 做停站验证**，正式关闭时须检查公网访问状态。
- 控制脚本无密钥的 GitHub 备份：[shared-dev-site.sh](../ops/shared-dev-site.sh)、[shared-dev-offline.conf](../ops/shared-dev-offline.conf)。
