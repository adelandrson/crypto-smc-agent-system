#!/bin/bash
# Hentikan WEB + MONITOR + TELEGRAM milik crypto-smc-agent-system SAJA (kebalikan run_services.sh).
# Pola match menyertakan --port 8002 & src.smc.arena / src.telegram.bot — TAK PERNAH match proses
# crypto-quant-agent (port 8000, src.rnd.arena) meski jalan bersamaan di host & user 'test' yang sama.
PORT=${WEB_PORT:-8002}
sudo pkill -u test -f "uvicorn src.web.app:app --host .* --port $PORT" 2>/dev/null && echo "web: TERM" || echo "web tak jalan"
sudo pkill -u test -f "src.smc.arena monitor" 2>/dev/null && echo "monitor: TERM" || echo "monitor tak jalan"
sudo pkill -u test -f "src.telegram.bot" 2>/dev/null && echo "telegram: TERM" || echo "telegram tak jalan"
sudo pkill -9 -u test -f "uvicorn src.web.app:app --host .* --port $PORT" 2>/dev/null && echo "web: KILL paksa (drain)"
sudo pkill -9 -u test -f "src.smc.arena monitor" 2>/dev/null
sudo pkill -9 -u test -f "src.telegram.bot" 2>/dev/null
exit 0
