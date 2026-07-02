#!/bin/bash
# Rutinitas HARIAN (idempotent, cron, offset dari sistem lain). Jalankan SBG EVIL.
# TIDAK pakai `set -e` agar 1 langkah gagal tak membatalkan sisanya.
set -o pipefail
DST=/home/test/crypto-smc-agent
run_test(){ sudo -u test -H bash -c "cd $DST && $1"; }
step(){ echo ""; echo "=== $1 $(date '+%F %T') ==="; }

step "[1/1] refresh universe CoinMarketCap (mcap>=\$300M) + tier volume-24h"
run_test ".venv/bin/python -m src.smc.universe" || echo "[1] universe refresh GAGAL"
