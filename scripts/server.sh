#!/usr/bin/env bash

set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${APP_ENV_FILE:-$ROOT_DIR/.env}"
CONDA_ENV="${CONDA_ENV:-read-books}"
CONDA_BIN="${CONDA_BIN:-$(command -v conda || true)}"
API_SERVICE="read-books-api.service"
WEB_SERVICE="read-books-web.service"

log() {
  printf '[read-books] %s\n' "$*"
}

die() {
  printf '[read-books] 错误：%s\n' "$*" >&2
  exit 1
}

load_environment() {
  [[ -f "$ENV_FILE" ]] || die "未找到配置文件 $ENV_FILE"
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
  API_PORT="${API_PORT:-8001}"
  WEB_PORT="${WEB_PORT:-3000}"
  NEXT_PUBLIC_API_BASE_URL="${NEXT_PUBLIC_API_BASE_URL:-/api}"
}

require_conda() {
  [[ -n "$CONDA_BIN" && -x "$CONDA_BIN" ]] || die "未找到 conda 命令"
}

run_in_conda() {
  require_conda
  "$CONDA_BIN" run --no-capture-output -n "$CONDA_ENV" "$@"
}

run_systemctl() {
  if [[ "${EUID:-$(id -u)}" -eq 0 ]]; then
    systemctl "$@"
  elif command -v sudo >/dev/null 2>&1; then
    sudo systemctl "$@"
  else
    die "服务操作需要 root 或 sudo 权限"
  fi
}

wait_for_url() {
  local name="$1"
  local url="$2"
  local attempts="${3:-60}"
  local index
  for ((index = 1; index <= attempts; index += 1)); do
    if curl -fsS --max-time 3 "$url" >/dev/null 2>&1; then
      log "$name 已就绪：$url"
      return 0
    fi
    sleep 1
  done
  run_systemctl --no-pager --full status "$API_SERVICE" "$WEB_SERVICE" || true
  die "$name 在 ${attempts} 秒内未就绪"
}

install_dependencies() {
  require_conda
  if "$CONDA_BIN" env list | awk '{print $1}' | grep -qx "$CONDA_ENV"; then
    log "更新 Conda 环境 $CONDA_ENV"
    "$CONDA_BIN" env update -n "$CONDA_ENV" -f "$ROOT_DIR/environment.yml" --prune
  else
    log "创建 Conda 环境 $CONDA_ENV"
    "$CONDA_BIN" env create -f "$ROOT_DIR/environment.yml"
  fi
  log "安装前端锁定依赖"
  run_in_conda npm --prefix "$ROOT_DIR/apps/web" ci
}

build_frontend() {
  log "构建 Next.js 生产版本"
  run_in_conda env NEXT_PUBLIC_API_BASE_URL="$NEXT_PUBLIC_API_BASE_URL" \
    npm --prefix "$ROOT_DIR/apps/web" run build
}

migrate_database() {
  log "执行数据库迁移"
  run_in_conda alembic -c "$ROOT_DIR/apps/api/alembic.ini" upgrade head
}

start_services() {
  [[ -f "$ROOT_DIR/apps/web/.next/BUILD_ID" ]] || die "前端尚未构建，请先执行 $0 build"
  log "启动 API 和 Web 服务"
  run_systemctl start "$API_SERVICE" "$WEB_SERVICE"
  wait_for_url "API" "http://127.0.0.1:$API_PORT/api/health"
  wait_for_url "Web" "http://127.0.0.1:$WEB_PORT/login"
}

stop_services() {
  log "停止 API 和 Web 服务"
  run_systemctl stop "$WEB_SERVICE" "$API_SERVICE"
}

restart_services() {
  log "重启 API 和 Web 服务"
  run_systemctl restart "$API_SERVICE" "$WEB_SERVICE"
  wait_for_url "API" "http://127.0.0.1:$API_PORT/api/health"
  wait_for_url "Web" "http://127.0.0.1:$WEB_PORT/login"
}

show_status() {
  printf '%-24s %s\n' "$API_SERVICE" "$(run_systemctl is-active "$API_SERVICE" 2>/dev/null || true)"
  printf '%-24s %s\n' "$WEB_SERVICE" "$(run_systemctl is-active "$WEB_SERVICE" 2>/dev/null || true)"
  curl -fsS --max-time 3 "http://127.0.0.1:$API_PORT/api/health" || true
  printf '\n'
}

show_logs() {
  local target="${1:-all}"
  case "$target" in
    api) journalctl -u "$API_SERVICE" -n 200 -f ;;
    web) journalctl -u "$WEB_SERVICE" -n 200 -f ;;
    all) journalctl -u "$API_SERVICE" -u "$WEB_SERVICE" -n 200 -f ;;
    *) die "日志目标仅支持 api、web 或 all" ;;
  esac
}

deploy_application() {
  stop_services || true
  install_dependencies
  build_frontend
  migrate_database
  start_services
}

usage() {
  cat <<'EOF'
用法：scripts/server.sh <command> [options]

命令：
  install          创建或更新 Conda 环境，并安装前端依赖
  build            构建 Next.js 生产版本
  migrate          执行 Alembic 数据库迁移
  start            启动 API 与 Web 服务
  stop             停止 API 与 Web 服务
  restart          重启 API 与 Web 服务
  status           查看服务状态和 API 健康信息
  logs [api|web]   持续查看服务日志，默认查看全部
  deploy           安装依赖、构建、迁移并启动全部服务
EOF
}

load_environment

case "${1:-}" in
  install) install_dependencies ;;
  build) build_frontend ;;
  migrate) migrate_database ;;
  start) start_services ;;
  stop) stop_services ;;
  restart) restart_services ;;
  status) show_status ;;
  logs) show_logs "${2:-all}" ;;
  deploy) deploy_application ;;
  *) usage; exit 1 ;;
esac
