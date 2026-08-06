#!/bin/sh

set -eu

ROOT=/data/disk1/portfolio-track-record
RUNTIME_DIR=${XDG_RUNTIME_DIR:-/run/user/$(id -u)}
ENABLE_FILE=$RUNTIME_DIR/portfolio-track-record-scheduler.enabled
LOCK_FILE=$ROOT/.local_update.lock
PYTHON=$ROOT/.venv/bin/python
PROXYCHAINS=/usr/bin/proxychains4
PROXYCHAINS_CONFIG=$ROOT/config/proxychains.conf

run_update() {
  [ -x "$PROXYCHAINS" ] || {
    echo "proxychains4 is required but is not executable: $PROXYCHAINS" >&2
    exit 1
  }
  [ -r "$PROXYCHAINS_CONFIG" ] || {
    echo "Project proxychains config is missing: $PROXYCHAINS_CONFIG" >&2
    exit 1
  }
  cd "$ROOT"
  exec "$PROXYCHAINS" -q -f "$PROXYCHAINS_CONFIG" "$PYTHON" -B -m src.local_update
}

is_running() {
  ! flock -n "$LOCK_FILE" -c true 2>/dev/null
}

case "${1:-}" in
  start)
    mkdir -p "$RUNTIME_DIR"
    : > "$ENABLE_FILE"
    chmod 600 "$ENABLE_FILE"
    echo "Scheduled updates enabled; running one update now."
    run_update
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
    run_update
    ;;
  *)
    echo "Usage: $0 {start|stop|status|run}" >&2
    exit 2
    ;;
esac
