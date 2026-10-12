# 美国 VPS 开发测试环境：已部署

> 记录日期：2026-10-12。这里仅记录非敏感运行信息，不保存任何密钥或登录凭据。

## 在线地址和验证

- 完整测试站：**https://dev.2858888.xyz/**
- 静态界面预览：**https://xiaohouzidoudou.github.io/hamoki-transfer/**
- 美国 VPS 公开 IPv4：`104.233.200.159`
- DNS：`dev.2858888.xyz` A 记录指向上述 IPv4
- 公网 HTTPS 由现有 1Panel OpenResty 反向代理到宿主机 `127.0.0.1:8018`，无需开放 8018 端口
- Let's Encrypt 证书签发成功，证书到期时间为 2027-01-10；`acme.sh` 已安装证书和续期后的 OpenResty reload hook，宿主机现有 cron 定期运行 acme.sh
- 实际验证：从公司电脑打开网页、`/health`、CSS/JS 均返回 200；公网 HTTPS 文件/文字上传、取件码查询、SVG 二维码、文件字节完整性、文字领取全部通过，匿名上传返回 403

## 宿主机结构（非密钥）

- AgentDock 连接节点：`raksmart`，先使用经过授权的宿主机 SSH 网关，**不要把 AgentDock 容器的本地系统等同于 VPS 宿主机**
- 项目路径：`/opt/hamoki-dev/app`
- Compose 项目名称：`hamoki-dev`，容器：`hamoki-dev-hamoki-1`
- 仅监听宿主机 `127.0.0.1:8018` → 容器 `8000`
- 独立 SQLite 和临时文件：`/opt/hamoki-dev/app/data`
- 上传授权、大小限制和 `PUBLIC_URL` 等配置位于 `/opt/hamoki-dev/app/.env`，**该文件绝不提交公共仓库**，本项目使用私密链接进行上传授权，下载无需登录
- OpenResty 虚拟站点配置：`/opt/1panel/www/conf.d/dev.2858888.xyz.conf`
- 网站证书：`/opt/1panel/www/sites/dev.2858888.xyz/ssl/`
- HTTP 阶段配置备份：`/opt/hamoki-dev/dev.2858888.xyz.http.conf.bak`
- HTTPS `/health` 返回 200，HTTP 自动 301 跳转 HTTPS
- **注意**：该域名直接通过 1Panel OpenResty 的挂载配置文件注册，而不是通过 1Panel 网站数据库新建；可能不会显示在 1Panel「网站」列表中。修改网站时需注意此项，不要在面板里建立同名冲突站点

## 如何迭代

1. 前端样式改动：提交 GitHub `main` 后 GitHub Pages 自动更新静态预览；先校验构建成功，再把固定预览链接发给用户
2. 完整前后端改动：先在开发分支测试；确认之后更新 **独立** Compose 项目 `hamoki-dev`，只重建这个服务，复查健康接口和关键操作
3. 备份/还原时保护 `data/`、独立 `.env`、虚拟站点配置和 SSL 续期安装状态；不要把私钥、上传密钥或数据库内容同步到公开 GitHub
4. 用户满意后才合并稳定版、发布 GitHub Release 和正式上线；开发测试 URL 不等于生产服务

## 以后新增其他项目

- 复用同一台美国 VPS 的开发测试流程，但**新项目各自使用独立目录、Docker Compose 项目、卷、端口和项目专属测试域名**，禁止所有项目共用好奇猴快传的数据库或上传密钥
- 为新项目配置新的 DNS、证书和 OpenResty 虚拟主机，然后将独立服务绑定宿主机回环端口；不修改其他现有容器
- 在 AgentDock 使用模板 `hamoki-universal-dev-preview-release`，持续复用「需求 → 开发 → 在线预览 → 用户反馈 → 验收发布」
- 未经用户明确确认，不自动发布新的生产版本

## 后续注意

- 当前完整测试站的应用代码更新仍是人工执行，**并非每次 GitHub 提交都会自动重建 Docker**；未来可以单独增加可回滚的 CI/CD 发布。
- 不公开分享发送方私密上传链接。必要时通过受控设备或管理通道授权；公共页面直接访问仅支持取件及展示。
