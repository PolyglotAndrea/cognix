#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_DIR="${COGNIX_RUN_DIR:-$ROOT_DIR/.cognix-dev/run}"
LOG_DIR="${COGNIX_LOG_DIR:-$ROOT_DIR/.cognix-dev/logs}"

BACKEND_HOST="${COGNIX_BACKEND_HOST:-127.0.0.1}"
BACKEND_PORT="${COGNIX_BACKEND_PORT:-8001}"
FRONTEND_HOST="${COGNIX_FRONTEND_HOST:-127.0.0.1}"
FRONTEND_PORT="${COGNIX_FRONTEND_PORT:-5173}"
COGNIX_HOME="${COGNIX_HOME:-$ROOT_DIR/.cognix-dev}"
COGNIX_AUTH__SECRET_KEY="${COGNIX_AUTH__SECRET_KEY:-local-dev-secret}"
VITE_API_TARGET="${VITE_API_TARGET:-http://$BACKEND_HOST:$BACKEND_PORT}"

BACKEND_PID="$RUN_DIR/backend.pid"
FRONTEND_PID="$RUN_DIR/frontend.pid"
BACKEND_LOG="$LOG_DIR/backend.log"
FRONTEND_LOG="$LOG_DIR/frontend.log"

mkdir -p "$RUN_DIR" "$LOG_DIR"

usage() {
  cat <<EOF
Usage: scripts/dev.sh <start|stop|restart|status|logs>

Environment overrides:
  COGNIX_BACKEND_PORT=$BACKEND_PORT
  COGNIX_FRONTEND_PORT=$FRONTEND_PORT
  COGNIX_HOME=$COGNIX_HOME
  VITE_API_TARGET=$VITE_API_TARGET
EOF
}

is_running() {
  local pid_file="$1"
  [[ -f "$pid_file" ]] && kill -0 "$(cat "$pid_file")" 2>/dev/null
}

python_bin() {
  if [[ -x "$ROOT_DIR/.venv/bin/python" ]]; then
    echo "$ROOT_DIR/.venv/bin/python"
  else
    command -v python3
  fi
}

start_backend() {
  if is_running "$BACKEND_PID"; then
    echo "Backend already running: pid $(cat "$BACKEND_PID")"
    return
  fi

  local python
  python="$(python_bin)"
  echo "Starting backend on http://$BACKEND_HOST:$BACKEND_PORT"
  (
    cd "$ROOT_DIR"
    COGNIX_HOME="$COGNIX_HOME" \
    COGNIX_DEBUG="${COGNIX_DEBUG:-true}" \
    COGNIX_AUTH__SECRET_KEY="$COGNIX_AUTH__SECRET_KEY" \
    "$python" -m uvicorn cognix.api.app:app \
      --host "$BACKEND_HOST" \
      --port "$BACKEND_PORT" \
      --reload
  ) >"$BACKEND_LOG" 2>&1 &
  echo $! > "$BACKEND_PID"
}

start_frontend() {
  if is_running "$FRONTEND_PID"; then
    echo "Frontend already running: pid $(cat "$FRONTEND_PID")"
    return
  fi

  if [[ ! -d "$ROOT_DIR/web/node_modules" ]]; then
    echo "web/node_modules is missing. Run: cd web && npm install"
    exit 1
  fi

  echo "Starting frontend on http://$FRONTEND_HOST:$FRONTEND_PORT"
  (
    cd "$ROOT_DIR/web"
    VITE_API_TARGET="$VITE_API_TARGET" \
    npm run dev -- --host "$FRONTEND_HOST" --port "$FRONTEND_PORT"
  ) >"$FRONTEND_LOG" 2>&1 &
  echo $! > "$FRONTEND_PID"
}

stop_one() {
  local name="$1"
  local pid_file="$2"
  if ! [[ -f "$pid_file" ]]; then
    echo "$name is not running"
    return
  fi

  local pid
  pid="$(cat "$pid_file")"
  if kill -0 "$pid" 2>/dev/null; then
    echo "Stopping $name: pid $pid"
    kill "$pid" 2>/dev/null || true
    for _ in {1..20}; do
      if ! kill -0 "$pid" 2>/dev/null; then
        break
      fi
      sleep 0.2
    done
    if kill -0 "$pid" 2>/dev/null; then
      echo "Force stopping $name: pid $pid"
      kill -9 "$pid" 2>/dev/null || true
    fi
  else
    echo "$name pid file is stale: $pid"
  fi
  rm -f "$pid_file"
}

start_all() {
  start_backend
  start_frontend
  status
  echo "Logs:"
  echo "  Backend:  $BACKEND_LOG"
  echo "  Frontend: $FRONTEND_LOG"
}

stop_all() {
  stop_one "frontend" "$FRONTEND_PID"
  stop_one "backend" "$BACKEND_PID"
}

status() {
  if is_running "$BACKEND_PID"; then
    echo "Backend:  running pid $(cat "$BACKEND_PID") -> http://$BACKEND_HOST:$BACKEND_PORT"
  else
    echo "Backend:  stopped"
  fi

  if is_running "$FRONTEND_PID"; then
    echo "Frontend: running pid $(cat "$FRONTEND_PID") -> http://$FRONTEND_HOST:$FRONTEND_PORT"
  else
    echo "Frontend: stopped"
  fi
}

logs() {
  touch "$BACKEND_LOG" "$FRONTEND_LOG"
  tail -f "$BACKEND_LOG" "$FRONTEND_LOG"
}

case "${1:-}" in
  start)
    start_all
    ;;
  stop)
    stop_all
    ;;
  restart)
    stop_all
    start_all
    ;;
  status)
    status
    ;;
  logs)
    logs
    ;;
  *)
    usage
    exit 1
    ;;
esac
