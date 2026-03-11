#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

BACKEND_HOST="${BACKEND_HOST:-127.0.0.1}"
BACKEND_PORT="${BACKEND_PORT:-18000}"
BACKEND_PROXY_HOST="${BACKEND_PROXY_HOST:-127.0.0.1}"
FRONTEND_HOST="${FRONTEND_HOST:-0.0.0.0}"
FRONTEND_PORT="${FRONTEND_PORT:-15173}"

DB_PATH="${DB_PATH:-data/papers.db}"
TASK_LOG_DIR="${TASK_LOG_DIR:-data/task_logs}"
SKILLS_DIR="${SKILLS_DIR:-skills}"

PYTHON_BIN="${PYTHON_BIN:-python3}"
NPM_BIN="${NPM_BIN:-npm}"

if [[ "$DB_PATH" != /* ]]; then
  DB_PATH="$ROOT_DIR/$DB_PATH"
fi
if [[ "$TASK_LOG_DIR" != /* ]]; then
  TASK_LOG_DIR="$ROOT_DIR/$TASK_LOG_DIR"
fi
if [[ "$SKILLS_DIR" != /* ]]; then
  SKILLS_DIR="$ROOT_DIR/$SKILLS_DIR"
fi

export DAILY_PAPER_DB_PATH="$DB_PATH"
export DAILY_PAPER_TASKS_DIR="$TASK_LOG_DIR"
export DAILY_PAPER_SKILLS_DIR="$SKILLS_DIR"
export VITE_PROXY_TARGET="http://$BACKEND_PROXY_HOST:$BACKEND_PORT"

mkdir -p "$TASK_LOG_DIR"

cleanup() {
  if [[ -n "${BACKEND_PID:-}" ]] && kill -0 "$BACKEND_PID" >/dev/null 2>&1; then
    kill "$BACKEND_PID" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT INT TERM

cd "$ROOT_DIR"

"$PYTHON_BIN" -m uvicorn website.backend.main:app \
  --host "$BACKEND_HOST" \
  --port "$BACKEND_PORT" \
  --reload &
BACKEND_PID=$!

echo "backend: http://$BACKEND_HOST:$BACKEND_PORT"
echo "frontend: http://$FRONTEND_HOST:$FRONTEND_PORT"

cd "$ROOT_DIR/website/frontend"
if [[ ! -d node_modules ]]; then
  "$NPM_BIN" install
fi

"$NPM_BIN" run dev -- --host "$FRONTEND_HOST" --port "$FRONTEND_PORT"
