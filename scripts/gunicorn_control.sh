#!/usr/bin/env bash
# Control simple para Gunicorn: start|stop|restart|status
# Evita arranques duplicados comprobando pidfile y puerto 8083.

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENV_PY="$PROJECT_ROOT/.venv/bin/python"
GUNICORN_BIN="$PROJECT_ROOT/.venv/bin/gunicorn"
PIDFILE="$PROJECT_ROOT/gunicorn.pid"
LOGFILE="$PROJECT_ROOT/run_gunicorn.log"
BIND_ADDR="127.0.0.1:8083"

usage() {
  echo "Usage: $0 {start|stop|restart|status}"
  exit 1
}

is_listening() {
  ss -ltnp 2>/dev/null | grep -q "$BIND_ADDR" || return 1
}

start() {
  if [ -f "$PIDFILE" ]; then
    pid=$(cat "$PIDFILE")
    if kill -0 "$pid" 2>/dev/null; then
      echo "Gunicorn already running with PID $pid (pidfile)." && return 0
    else
      echo "Removing stale pidfile." && rm -f "$PIDFILE"
    fi
  fi

  if is_listening; then
    echo "Port $BIND_ADDR already in use. Refusing to start." && ss -ltnp | grep "$BIND_ADDR" || true
    return 1
  fi

  echo "Starting Gunicorn (binding to $BIND_ADDR), logs -> $LOGFILE"
  nohup "$GUNICORN_BIN" -w 3 -b "$BIND_ADDR" wsgi:application --log-file "$LOGFILE" --access-logfile - > "$LOGFILE" 2>&1 &
  echo $! > "$PIDFILE"
  sleep 2

  if is_listening; then
    echo "Gunicorn started successfully (pid $(cat $PIDFILE))."
    return 0
  else
    echo "Failed to start Gunicorn. Check $LOGFILE" && tail -n 80 "$LOGFILE" || true
    return 2
  fi
}

stop() {
  if [ -f "$PIDFILE" ]; then
    pid=$(cat "$PIDFILE")
    echo "Stopping Gunicorn PID $pid"
    kill "$pid" 2>/dev/null || true
    sleep 1
    rm -f "$PIDFILE" || true
  fi
  # ensure no workers remain
  pkill -f "$GUNICORN_BIN" || true
  echo "Stopped.";
}

status() {
  if [ -f "$PIDFILE" ]; then
    pid=$(cat "$PIDFILE")
    echo "pidfile: $PIDFILE -> $pid"
    ps -p "$pid" -o pid,cmd || true
  else
    echo "No pidfile."
  fi
  echo "Listening sockets:"
  ss -ltnp | grep "$BIND_ADDR" || echo "(none)"
}

case "${1-}" in
  start) start ;; 
  stop) stop ;; 
  restart) stop; start ;; 
  status) status ;; 
  *) usage ;; 
esac
