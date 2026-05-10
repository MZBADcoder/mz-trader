#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${BACKEND_DIR}"

if ! command -v poetry >/dev/null 2>&1; then
  echo "poetry is required but was not found in PATH." >&2
  exit 1
fi

export PYTHONPATH="${BACKEND_DIR}/src${PYTHONPATH:+:${PYTHONPATH}}"

APP_HOST="${APP_HOST:-0.0.0.0}"
APP_PORT="${APP_PORT:-8000}"
UVICORN_LOG_LEVEL="${UVICORN_LOG_LEVEL:-info}"
CELERY_LOG_LEVEL="${CELERY_LOG_LEVEL:-INFO}"
CELERY_WORKER_CONCURRENCY="${CELERY_WORKER_CONCURRENCY:-2}"
RUN_GAP_RECONCILIATION_ON_START="${RUN_GAP_RECONCILIATION_ON_START:-1}"
GAP_RECONCILIATION_TRIGGER_DELAY_SECONDS="${GAP_RECONCILIATION_TRIGGER_DELAY_SECONDS:-5}"

RUNTIME_DIR="${BACKEND_DIR}/var/run"
mkdir -p "${RUNTIME_DIR}"

PIDS=()

cleanup() {
  local exit_code=$?
  trap - INT TERM EXIT

  if [ "${#PIDS[@]}" -gt 0 ]; then
    echo
    echo "Stopping backend dev stack..."
    for pid in "${PIDS[@]}"; do
      if kill -0 "${pid}" >/dev/null 2>&1; then
        kill "${pid}" >/dev/null 2>&1 || true
      fi
    done
    for pid in "${PIDS[@]}"; do
      wait "${pid}" >/dev/null 2>&1 || true
    done
  fi

  exit "${exit_code}"
}

trap cleanup INT TERM EXIT

start_process() {
  local name="$1"
  shift

  echo "Starting ${name}: $*"
  "$@" &
  local pid=$!
  PIDS+=("${pid}")
  echo "${name} pid=${pid}"
}

trigger_gap_reconciliation() {
  if [ "${RUN_GAP_RECONCILIATION_ON_START}" != "1" ]; then
    echo "Skipping historical bars gap reconciliation trigger."
    return
  fi

  echo "Waiting ${GAP_RECONCILIATION_TRIGGER_DELAY_SECONDS}s before triggering historical bars gap reconciliation..."
  sleep "${GAP_RECONCILIATION_TRIGGER_DELAY_SECONDS}"

  echo "Triggering worker.tasks.bar_refresh.run_historical_bars_gap_reconciliation..."
  poetry run celery \
    -A worker.celery_app \
    call worker.tasks.bar_refresh.run_historical_bars_gap_reconciliation
}

start_process \
  "celery worker" \
  poetry run celery \
    -A worker.celery_app \
    worker \
    --loglevel="${CELERY_LOG_LEVEL}" \
    --concurrency="${CELERY_WORKER_CONCURRENCY}" \
    --hostname="trader-local@%h"

start_process \
  "celery beat" \
  poetry run celery \
    -A worker.celery_app \
    beat \
    --loglevel="${CELERY_LOG_LEVEL}" \
    --schedule="${RUNTIME_DIR}/celerybeat-schedule"

start_process \
  "uvicorn server" \
  poetry run uvicorn \
    main:app \
    --reload \
    --host "${APP_HOST}" \
    --port "${APP_PORT}" \
    --log-level "${UVICORN_LOG_LEVEL}"

trigger_gap_reconciliation

echo
echo "Backend dev stack is running."
echo "Server: http://${APP_HOST}:${APP_PORT}"
echo "Press Ctrl+C to stop server, celery worker, and celery beat."

wait "${PIDS[@]}"
