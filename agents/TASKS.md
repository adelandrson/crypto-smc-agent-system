# TASKS — Loop Operasi, Pagar & Papan Tugas

Loop kerja & batas operasi. Identitas & wewenang [IDENTITY.md](IDENTITY.md), persona
[SOUL.md](SOUL.md), cara kerja [AGENTS.md](AGENTS.md), profil & parameter [MEMORY.md](MEMORY.md).

---

## A. Loop operasi dry-run (cron, otomatis)

```
1. KELOLA   — cek semua posisi terbuka (kedua gaya) vs harga Binance terkini → proses TP
              bertahap yg kena + evolusi SL (BE→lock→trailing) → tutup posisi yg qty habis.
2. SCAN     — untuk tiap koin di universe (mcap>=$300M, Binance-tradable): tarik candle + FVG +
              Fib/OB/struktur + OI/FR/LSR → confluence score (-4..+4).
3. SNAPSHOT — simpan HASIL (open ATAU skip + alasan) ke SignalSnapshot — transparansi penuh,
              termasuk yang di-skip (halaman Sinyal & skill screening_highlights baca ini).
4. VERDIKT  — |full_score| >= 2 & lolos SEMUA filter (zona/ranging/volume/LSR/sesi) & masih
              ada slot (max 4/gaya) → buka posisi. Selain itu → SKIP (sah, bukan gagal).
5. RENCANA  — SL berbasis struktur (sebelum entry!), TP bertahap, ukuran dari risk%, leverage
              dalam range gaya (15-30x scalp/8-15x swing).
6. ULANGI   — kembali ke KELOLA. Tidak ada langkah EKSEKUSI NYATA — dry-run selamanya.
```

Dijalankan via `python -m src.smc.arena step` (cron) atau `monitor` (loop service).

---

## B. Batas operasi (semua harus benar, kalau tidak → skip & catat alasan)

```
[ ] Simbol ∈ universe (mcap>=$300M, Binance-perp-tradable, lihat MEMORY.md)
[ ] Risk per trade sesuai batas (1% scalp / 2% swing); leverage dalam pagar (15-30x/8-15x)
    DAN size dihitung dari risk%, bukan leverage
[ ] Confluence |full_score| >= 2 (ambang TAK BOLEH dinaikkan/diturunkan dari chat)
[ ] Tidak ada kondisi SKIP (ranging, volume anomaly, LSR kontrarian, di luar sesi utk scalp)
[ ] Disiplin zona: long HANYA discount, short HANYA premium
[ ] Slot masih tersedia (< 4 posisi terbuka di gaya itu)
[ ] SL terpasang & valid SEBELUM posisi "dibuka" (tercatat)
```

Di luar pagar mana pun → **jangan buka posisi**, catat alasan skip di SignalSnapshot.

---

## C. Checklist siklus-trade

```
PRA-ENTRY   : [ ] confluence lengkap  [ ] |score|>=2  [ ] SL & size dihitung  [ ] zona benar
ENTRY       : [ ] fill disimulasikan (slippage+fee)  [ ] tercatat DryRunTrade
KELOLA      : [ ] SL evolve sesuai TP yg kena (BE→lock→trailing)  [ ] fill tercatat DryRunFill
EXIT        : [ ] sesuai rencana (TP/SL/limit-canceled)  [ ] r_multiple & outcome tercatat
```

---

## D. Tugas terjadwal (cron)

```
- Dry-run step      : tiap ~15 menit  → kelola posisi + scan sinyal baru (kedua gaya)
- Universe refresh  : harian         → tarik ulang CMC, update tier
- Watchdog          : tiap 2 menit   → auto-restart bila web/monitor mati
```

---

## E. Papan tugas (hidup — perbarui)

### Aktif
- [ ] Kumpulkan >=20-30 trade closed per gaya sebelum evaluasi expectancy-R pertama
- [ ] Bandingkan expectancy-R & win-rate vs crypto-trader-agent-system setelah sampel cukup

### Backlog
- [ ] Kalibrasi ulang threshold tier S/A/B/C dari data volume riil setelah beberapa minggu
- [ ] Venue eksekusi = pilihan user (Binance/Bybit/Hyperliquid, lihat sumber ROADMAP.md §4b); data web saat ini Binance-only

### Selesai
- [x] Port metodologi confluence (FVG+Fib+OB+struktur+OI+FR+LSR+momentum) — verbatim
- [x] DB-backed dry-run broker (TP bertahap + evolusi SL) — 88 test hijau
- [x] Universe/tier-list CMC (mcap>=$300M, exclude stablecoin/gold-index/derivative)
