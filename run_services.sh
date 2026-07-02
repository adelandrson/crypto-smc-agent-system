#!/bin/bash
# Supervisor IDEMPOTEN (jalan SBG EVIL) — sistem PEMBANDING crypto-smc-agent-system, berjalan
# BERDAMPINGAN dengan crypto-quant-agent (path/port terpisah, tak saling ganggu):
#   1) WEB UI    (FastAPI/uvicorn, port 8002 default) → dashboard
#   2) MONITOR   (loop dry-run near-real-time, src.smc.arena)
#   3) TELEGRAM  (opsional — no-op graceful bila TELEGRAM_BOT_TOKEN kosong di .env)
# Dipakai di @reboot DAN sbg watchdog cron (*/2) → auto-recover bila proses mati.
# PENTING: pola pgrep/pkill SENGAJA menyertakan --port (web) & src.smc.arena (monitor, beda
# modul dari src.rnd.arena milik sistem lain) supaya stop/restart TAK PERNAH kena proses sistem lain.
set -o pipefail
DST=/home/test/crypto-smc-agent
HOST=${WEB_HOST:-127.0.0.1}
PORT=${WEB_PORT:-8002}
INTERVAL=${MONITOR_INTERVAL:-20}

LOCK=/tmp/smc_run_services.lock
exec 9>"$LOCK" 2>/dev/null || true
flock -n 9 2>/dev/null || { echo "$(date '+%F %T') run_services skip (instance lain berjalan)"; exit 0; }

started=""

# 1) WEB UI — pola match menyertakan --port $PORT (disambiguasi dari sistem lain yg sama-sama "src.web.app:app")
if ! pgrep -u test -f "uvicorn src.web.app:app --host $HOST --port $PORT" >/dev/null 2>&1; then
  sudo -u test -H setsid bash -c \
    "cd $DST && nohup .venv/bin/uvicorn src.web.app:app --host $HOST --port $PORT >> $DST/web.log 2>&1" </dev/null &
  started="$started web"
fi

# 2) MONITOR dry-run — src.smc.arena (beda modul dari src.rnd.arena milik sistem lain, aman)
if ! pgrep -u test -f "src.smc.arena monitor" >/dev/null 2>&1; then
  sudo -u test -H setsid bash -c \
    "cd $DST && nohup .venv/bin/python -m src.smc.arena monitor --interval=$INTERVAL >> $DST/monitor.log 2>&1" </dev/null &
  started="$started monitor"
fi

# 3) TELEGRAM — opsional; no-op graceful sendiri bila TELEGRAM_BOT_TOKEN kosong (lihat src/telegram/bot.py)
if ! pgrep -u test -f "src.telegram.bot" >/dev/null 2>&1; then
  sudo -u test -H setsid bash -c \
    "cd $DST && nohup .venv/bin/python -m src.telegram.bot >> $DST/telegram.log 2>&1" </dev/null &
  started="$started telegram"
fi

if [ -n "$started" ]; then
  echo "$(date '+%F %T') run_services STARTED:$started"
else
  echo "$(date '+%F %T') run_services ok (web+monitor+telegram sudah hidup)"
fi
