#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="$ROOT_DIR/logs"
mkdir -p "$LOG_DIR"

WEB_LOG="$LOG_DIR/web_runtime.log"
OLLAMA_LOG="$LOG_DIR/ollama_runtime.log"

echo "[1/5] Cleaning duplicate web processes..."
mapfile -t web_pids < <(pgrep -f "python3 run.py|/root/miniconda3/bin/python3 run.py" || true)
if ((${#web_pids[@]} > 0)); then
  echo "Found web PIDs: ${web_pids[*]}"
  kill "${web_pids[@]}" || true
  sleep 1
fi

# Force kill leftovers if still alive.
mapfile -t web_left < <(pgrep -f "python3 run.py|/root/miniconda3/bin/python3 run.py" || true)
if ((${#web_left[@]} > 0)); then
  echo "Force killing leftover web PIDs: ${web_left[*]}"
  kill -9 "${web_left[@]}" || true
  sleep 1
fi

echo "[2/5] Ensuring Ollama service is up..."
if ! curl -sSf --max-time 2 http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
  echo "Ollama is down, starting..."
  nohup ollama serve >"$OLLAMA_LOG" 2>&1 &
  sleep 2
fi

if ! curl -sSf --max-time 3 http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
  echo "ERROR: Ollama failed to start. Check $OLLAMA_LOG"
  exit 1
fi

echo "[3/5] Starting web app in single-process mode..."
cd "$ROOT_DIR"
SECRET_KEY_VALUE="${SECRET_KEY:-financial-analysis-secret-2024}"
APP_DEBUG=0 APP_ENV=production SECRET_KEY="$SECRET_KEY_VALUE" UPSTREAM_REPORT_TIMEOUT_SECONDS=1200 nohup python3 run.py >"$WEB_LOG" 2>&1 &
sleep 2

echo "[4/5] Running health checks..."
if ! curl -sSf --max-time 3 http://127.0.0.1:5000/ >/dev/null 2>&1; then
  echo "ERROR: Web app health check failed. Check $WEB_LOG"
  exit 1
fi

if ! curl -sSf --max-time 3 http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
  echo "ERROR: Ollama health check failed after web start. Check $OLLAMA_LOG"
  exit 1
fi

echo "[5/5] Runtime status"
echo "Web PID(s): $(pgrep -f "python3 run.py|/root/miniconda3/bin/python3 run.py" | tr '\n' ' ')"
echo "Ollama PID(s): $(pgrep -f "ollama serve" | tr '\n' ' ')"
echo "Web URL: http://127.0.0.1:5000"
echo "Logs: $WEB_LOG | $OLLAMA_LOG"
