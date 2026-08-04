#!/bin/sh

set -eu

ROOT=/data/disk1/portfolio-track-record
RUNTIME_DIR=${XDG_RUNTIME_DIR:-/run/user/$(id -u)}
ENABLE_FILE=$RUNTIME_DIR/portfolio-track-record-scheduler.enabled
LOCK_FILE=$ROOT/.local_update.lock
PYTHON=$ROOT/.venv/bin/python

is_running() {
  ! flock -n "$LOCK_FILE" -c true 2>/dev/null
}

case "${1:-}" in
  start)
    mkdir -p "$RUNTIME_DIR"
    : > "$ENABLE_FILE"
    chmod 600 "$ENABLE_FILE"
    echo "Scheduled updates enabled; running one update now."
    cd "$ROOT"
    exec "$PYTHON" -B -m src.local_update
    ;;
  stop)
    rm -f "$ENABLE_FILE"
    echo "Future scheduled updates disabled."
    if is_running; then
      echo "The current update is still running and was not interrupted."
    fi
    ;;
  status)
    if [ -f "$ENABLE_FILE" ]; then
      echo "Schedule: enabled"
    else
      echo "Schedule: disabled"
    fi
    if is_running; then
      echo "Updater: running"
    else
      echo "Updater: idle"
    fi
    ;;
  run)
    [ -f "$ENABLE_FILE" ] || exit 0
    cd "$ROOT"
    exec "$PYTHON" -B -m src.local_update
    ;;
  *)
    echo "Usage: $0 {start|stop|status|run}" >&2
    exit 2
    ;;
esac
