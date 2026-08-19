# 远程部署与服务管理

## 部署目标

- 服务器：`47.115.200.179`
- SSH：`root@47.115.200.179`
- 项目目录：`/home/mengalong/website/read-books`
- Nginx 目录：`/home/mengalong/website/nginx`
- 域名：`https://books.mengalong.cn`
- Next.js：宿主机 `3000`
- FastAPI：宿主机 `8001`

服务器现有 `8000` 端口属于其他应用，回卷固定使用 `8001`。Nginx 运行在 Docker 中，通过 `host.docker.internal` 访问宿主机的两个应用端口。

## 一键部署

在本地项目根目录执行：

```bash
scripts/deploy.sh
```

部署脚本会依次完成：

1. 检查本地工作区没有未提交改动并推送 `main`。
2. 将已提交版本增量同步到远端，不依赖远端旧版 Git，不执行远端删除，并保留 `.env`、SQLite、上传文件和解析数据。
3. 首次部署创建生产 `.env`，自动生成管理员临时密码。
4. 创建或更新 Conda 环境（Python 3.12、Node.js 20），通过 Conda 安装兼容 CentOS 7 的 `greenlet 3.1.1`，使用 PyMuPDF 1.25 轮子，并通过 `npm ci` 安装前端锁定依赖。
5. 构建 Next.js、执行 Alembic 迁移并启动两个 systemd 服务。
6. 安装独立 Nginx 虚拟主机，若缺少证书会自动通过 Let's Encrypt 申请，随后启用 80 -> 443 跳转并热重载 Nginx。
7. 输出服务状态；首次部署额外输出一次管理员临时密码。

首次管理员账号为 `admin`，登录后必须立即修改临时密码。初始化完成后，脚本会从 `.env` 清除初始化用户名和密码，数据库中的 Argon2 哈希不受影响。

## 统一服务脚本

远端进入项目目录：

```bash
cd /home/mengalong/website/read-books
```

常用操作：

```bash
scripts/server.sh start
scripts/server.sh stop
scripts/server.sh restart
scripts/server.sh status
scripts/server.sh logs
scripts/server.sh logs api
scripts/server.sh logs web
```

部署相关操作：

```bash
scripts/server.sh install
scripts/server.sh build
scripts/server.sh migrate
scripts/server.sh deploy
```

`deploy` 会停止当前服务，依次执行依赖安装、前端构建、数据库迁移并重新启动。服务由 systemd 托管，服务器重启后自动启动，异常退出时自动重启。

## 生产配置

生产配置位于远端项目根目录 `.env`，权限为 `600`。默认配置要点：

```env
APP_ENV=production
API_PORT=8001
WEB_PORT=3000
WEB_ORIGIN=https://books.mengalong.cn
SEED_DEMO_DATA=false
SESSION_COOKIE_SECURE=true
WECHAT_LOGIN_ENABLED=false
WECHAT_LOGIN_REQUIRED=false
WECHAT_CALLBACK_BASE_URL=https://books.mengalong.cn
OCR_ENABLED=false
NEXT_PUBLIC_API_BASE_URL=/api
```

远端是 Linux，不能使用本地 macOS Vision OCR，因此默认关闭 OCR。原生包含可读文本的 PDF 仍可正常解析；扫描版或字体编码异常的 PDF 需要后续接入 Linux OCR 服务。

## Nginx 与上传

站点配置安装到：

```text
/home/mengalong/website/nginx/conf/nginx/conf.d/books.mengalong.cn.conf
```

`/api/` 转发到 FastAPI，其余请求转发到 Next.js。HTTP 会自动跳转到 HTTPS，`client_max_body_size 0` 表示 Nginx 不限制 PDF 上传大小，同时关闭请求缓冲并将上传流式传给后端。证书文件默认放在：

```text
/home/mengalong/website/nginx/letsencrypt/live/books.mengalong.cn/
```

## HTTPS

部署脚本会在首次发现缺少证书时自动通过 Let's Encrypt 申请证书，并重建 Nginx 容器为 `80:80` 和 `443:443`。后续如果需要手动续期，可以在远端复用同一套 `certbot` 流程。微信正式联调时，系统管理里的回调地址应填写 `https://books.mengalong.cn`，并确保微信开放平台授权回调域已经配置为 `books.mengalong.cn`。
