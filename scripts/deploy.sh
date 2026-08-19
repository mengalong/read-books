#!/usr/bin/env bash

set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REMOTE_HOST="${REMOTE_HOST:-root@47.115.200.179}"
REMOTE_DIR="${REMOTE_DIR:-/home/mengalong/website/read-books}"
REMOTE_NGINX_DIR="${REMOTE_NGINX_DIR:-/home/mengalong/website/nginx}"
TLS_DOMAIN="${TLS_DOMAIN:-books.mengalong.cn}"
DEPLOY_BRANCH="${DEPLOY_BRANCH:-main}"

if ! git -C "$ROOT_DIR" diff --quiet || ! git -C "$ROOT_DIR" diff --cached --quiet; then
  printf '部署前必须提交当前工作区改动。\n' >&2
  exit 1
fi

printf '推送 %s 分支到 GitHub...\n' "$DEPLOY_BRANCH"
git -C "$ROOT_DIR" push origin "$DEPLOY_BRANCH"

SYNC_DIR="$(mktemp -d)"
trap 'rm -rf "$SYNC_DIR"' EXIT
git -C "$ROOT_DIR" archive --format=tar "$DEPLOY_BRANCH" | tar -xf - -C "$SYNC_DIR"

printf '同步代码并部署到 %s:%s...\n' "$REMOTE_HOST" "$REMOTE_DIR"
ssh "$REMOTE_HOST" "mkdir -p '$REMOTE_DIR'"
rsync -az \
  --exclude='.env' \
  --exclude='.git/' \
  --exclude='data/app.db*' \
  --exclude='data/uploads/' \
  --exclude='data/parsed/' \
  --exclude='apps/web/node_modules/' \
  --exclude='apps/web/.next/' \
  --exclude='apps/web/.next-dev/' \
  "$SYNC_DIR/" "$REMOTE_HOST:$REMOTE_DIR/"

ssh "$REMOTE_HOST" bash -s -- \
  "$REMOTE_DIR" "$REMOTE_NGINX_DIR" "$TLS_DOMAIN" <<'REMOTE_SCRIPT'
set -Eeuo pipefail

remote_dir="$1"
nginx_dir="$2"
tls_domain="$3"
created_environment=false
initial_admin_password=""
tls_live_dir="$nginx_dir/letsencrypt/live/$tls_domain"
tls_fullchain="$tls_live_dir/fullchain.pem"
tls_privkey="$tls_live_dir/privkey.pem"
certbot_name="certbot-${tls_domain//./-}"

cd "$remote_dir"

mkdir -p "$nginx_dir/letsencrypt" "$nginx_dir/html" "$nginx_dir/log"

if [[ ! -f .env ]]; then
  initial_admin_password="ReadBooks-$(openssl rand -hex 12)A1"
  cp deploy/production.env.example .env
  sed -i "s/^INITIAL_ADMIN_PASSWORD=.*/INITIAL_ADMIN_PASSWORD=$initial_admin_password/" .env
  chmod 600 .env
  created_environment=true
else
  saved_admin_username="$(sed -n 's/^INITIAL_ADMIN_USERNAME=//p' .env | head -n 1)"
  saved_admin_password="$(sed -n 's/^INITIAL_ADMIN_PASSWORD=//p' .env | head -n 1)"
  if [[ "$saved_admin_username" == "admin" && "$saved_admin_password" == ReadBooks-*A1 ]]; then
    created_environment=true
    initial_admin_password="$saved_admin_password"
  fi
fi

if [[ ! -f "$tls_fullchain" || ! -f "$tls_privkey" ]]; then
  printf "检测到缺少 %s 的 TLS 证书，先通过 Let's Encrypt 申请。\n" "$tls_domain"
  docker rm -f nginx >/dev/null 2>&1 || true
  docker run --rm \
    --name "$certbot_name" \
    -p 80:80 \
    -v "$nginx_dir/letsencrypt:/etc/letsencrypt" \
    certbot/certbot certonly \
    --standalone \
    --agree-tos \
    --non-interactive \
    --register-unsafely-without-email \
    -d "$tls_domain"
fi

install -m 0644 deploy/systemd/read-books-api.service /etc/systemd/system/read-books-api.service
install -m 0644 deploy/systemd/read-books-web.service /etc/systemd/system/read-books-web.service
install -m 0644 deploy/nginx/books.mengalong.cn.conf \
  "$nginx_dir/conf/nginx/conf.d/books.mengalong.cn.conf"

systemctl daemon-reload
systemctl enable read-books-api.service read-books-web.service
scripts/server.sh deploy

if [[ "$created_environment" == true ]]; then
  sed -i 's/^INITIAL_ADMIN_USERNAME=.*/INITIAL_ADMIN_USERNAME=/' .env
  sed -i 's/^INITIAL_ADMIN_PASSWORD=.*/INITIAL_ADMIN_PASSWORD=/' .env
  systemctl restart read-books-api.service
  for _ in $(seq 1 60); do
    if curl -fsS --max-time 3 http://127.0.0.1:8001/api/health >/dev/null 2>&1; then
      break
    fi
    sleep 1
  done
fi

docker rm -f nginx >/dev/null 2>&1 || true
docker run -d \
  --name nginx \
  --restart unless-stopped \
  -p 80:80 \
  -p 443:443 \
  -v "$nginx_dir/conf/nginx:/etc/nginx" \
  -v "$nginx_dir/html:/usr/share/nginx/html" \
  -v "$nginx_dir/log:/var/log/nginx" \
  -v "$nginx_dir/letsencrypt:/etc/letsencrypt:ro" \
  --add-host=host.docker.internal:host-gateway \
  nginx
docker exec nginx nginx -t
docker exec nginx nginx -s reload

scripts/server.sh status
if [[ "$created_environment" == true ]]; then
  printf 'INITIAL_ADMIN_USERNAME=admin\n'
  printf 'INITIAL_ADMIN_TEMP_PASSWORD=%s\n' "$initial_admin_password"
fi
REMOTE_SCRIPT

printf '部署完成：https://books.mengalong.cn\n'
