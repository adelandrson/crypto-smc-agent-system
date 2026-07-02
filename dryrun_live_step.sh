#!/bin/bash
# ARENA step (cron tiap 15 menit, offset dari sistem lain, SBG EVIL): kelola posisi terbuka +
# scan sinyal confluence baru (scalp+swing), universe mcap>=$300M. Path absolut. Graceful.
set -o pipefail
DST=/home/test/crypto-smc-agent
sudo -u test -H bash -c "cd $DST && .venv/bin/python -m src.smc.arena step" || echo "smc arena step GAGAL $(date)"
