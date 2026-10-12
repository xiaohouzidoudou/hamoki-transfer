# 好奇猴快传 v1.1.0 · 公开上传防滥用

本次针对公开分享增加基础防滥用保护，私人快传继续保持原有操作习惯和功能。

- **普通访客上传限制**：每个 IP 在滚动24小时内，累计公开上传最多1 GiB。
- **上传口令解锁**：访客超过限制时可在「寄文件」页面输入站长设定的口令。验证成功后的浏览器24小时内免每日访客额度。
- **总存储配额**：默认改为10 GiB，公开分享与私人空间共用总额。
- **保持不变**：单次最高5 GiB、公开分享最多10次领取及1/3/7天有效期；私人配对设备双向快传不计入访客日限额。

下载 **Source code (zip)** 或 **Source code (tar.gz)** 可自行部署。详见 [README](https://github.com/xiaohouzidoudou/hamoki-transfer) 和 [部署指南](https://github.com/xiaohouzidoudou/hamoki-transfer/blob/main/docs/DEPLOYMENT.md)。

站长必须在自己的服务器 `.env` 内配置 `UPLOAD_UNLOCK_PASSWORD`，公开模板不包含真实密码。共享 IP 和更换 IP 可影响按 IP 限额效果；这不是严格账号额度或带宽计费系统。
