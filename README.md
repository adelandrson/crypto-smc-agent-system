# crypto-smc-agent-system ◈

**Sistem PEMBANDING** untuk [crypto-trader-agent-system](https://github.com/adelandrson/crypto-trader-agent-system)
(pattern-screening) — metodologi **BERBEDA TOTAL**: **Smart Money Concepts (SMC)** — Fair Value
Gap (FVG) + Fibonacci/Order Block/struktur BOS-CHoCH, dikombinasikan dengan Open Interest,
Funding Rate, dan Long/Short Ratio menjadi satu **confluence score (−4..+4)**. Trade hanya
dieksekusi (dry-run) bila `|full_score| ≥ 2` dan lolos semua filter (disiplin zona, ranging,
volume anomaly, LSR kontrarian).

> **Mode dry-run/paper SELAMANYA** — tidak ada API key bursa, tidak ada eksekusi order nyata,
> tidak ada dana nyata tersentuh. Berjalan **berdampingan** dengan sistem pembanding (port &
> database terpisah), bukan menggantikannya.

---

## Kenapa sistem ini ada

Win-rate & akurasi sinyal sistem pembanding (pattern-screening) buruk. Alih-alih menambal
metodologinya, dibangun sistem independen dengan metodologi **teruji dari sumber eksternal**
(159 test hijau di bundel sumbernya, `AUDIT.md`-nya sendiri jujur soal hit-rate <50% tapi
ekspektasi positif dari R:R) — untuk perbandingan yang bermakna, apples-to-apples, live.

## Metodologi (inti diporting dari sumber + penyempurnaan: signal-gaps, TP struktur, entry fleksibel)

```
FVG (engine tunggal)         → zona imbalance fresh/tested/mitigated
Fibonacci/Order Block/BOS-CHoCH (engine tunggal) → golden pocket/OTE, struktur, zona premium/discount
Open Interest + Funding Rate + Long/Short Ratio  → sentimen derivatif (kontrarian di ekstrem)
Momentum/Volatilitas (RSI+ADX+volume z-score+RSI-quality) → filter SKIP + kualitas
Liquidity sweep/EQH-EQL · CVD per-candle divergence · MTF divergence → BOOSTER A+
                    ↓
     CONFLUENCE SCORE (−4..+4) = FVG + Fib + OI + FR
                    ↓
     |score| ≥ gerbang (default 2) & disiplin zona & lolos semua filter → TRADE (dry-run)
                    ↓
     ENTRY FLEKSIBEL: harga di zona (FVG/OB/OTE)=MARKET; di luar=LIMIT retest (pending→fill saat
     pullback / batal bila TTL/harga kabur) · SL struktur · TP: SCALP 1 TP tutup
     100% di 2R (main cepat) / SWING 1-3 TP by Volatility State + ATR, LEVEL dari struktur (BE→lock-TP1)
     · sizing dari risk% (bukan leverage) · harga ditulis 5/4 angka utama
```

## Penyesuaian eksplisit (satu-satunya yang berbeda dari metodologi sumber)

| Param | Sistem ini |
|---|---|
| Universe | CMC mcap ≥ $300M, exclude stablecoin/gold/derivative, Binance-perp-tradable, **tier TERPISAH scalp (mcap40/vol60) & swing (mcap60/vol40)** S/A/B/C |
| Max posisi | 4 per gaya (scalp DAN swing) |
| Leverage scalp | 15x–30x |
| Leverage swing | 8x–15x |
| Risk/trade | 1% scalp · 2% swing dari ekuitas (risk%, bukan leverage) |
| TP | scalp 1 TP 100% · swing 1-3 TP by Volatility+ATR, level dari struktur |
| Entry | fleksibel market/limit · +4 signal-gap booster A+ (sweep/CVD/MTF/RSI-quality) |

Detail lengkap & alasan tiap penyesuaian → `agents/MEMORY.md`.

## Arsitektur

```
src/engines/{fvg,sfib,ind}/     # 3 engine sumber (stdlib-only), diporting verbatim + test masing2
src/smc/                        # confluence.py, decide.py, arena.py (broker DB-backed), universe.py
src/storage/models.py           # Token(+tier), DryRunTrade+DryRunFill, SignalSnapshot, ChatSession
src/agents/roster.py            # 5 agent: Orin/Vega/Arka/Wira/Bayu
src/llm/{client,skills}.py      # skill: analisa live + status dry-run + akses data + config_* + write_source/run_tests (per mode otoritas)
src/web/app.py                  # FastAPI: chat SSE + /api/{analyze,signals,universe,agent,admin}
src/web/static/                 # UI baru (dark/cyan-violet, gauge confluence, TP-ladder)
src/telegram/bot.py             # jembatan Telegram (opsional) — satu otak, dua pintu masuk
agents/*.md                     # IDENTITY/SOUL/AGENTS/MEMORY/TASKS/USER — konstitusi agent
```

## Roster agent

| Agent | Peran |
|---|---|
| **Orin** (Orchestrator) | Koordinasi, chat website & Telegram, sintesis |
| **Vega** (Struktur & Imbalance) | FVG + Fib + Order Block + BOS/CHoCH |
| **Arka** (Sentimen Derivatif) | OI + FR + LSR + momentum/volatilitas |
| **Wira** (Eksekutor Dry-Run) | Sizing, SL struktur, TP (scalp single/swing 1-3), entry fleksibel, leverage |
| **Bayu** (Evaluator) | Expectancy-R jujur (bukan win-rate mentah), universe/tier |

## Instalasi

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env   # isi CMC_API_KEY minimal
.venv/bin/python -m src.smc.universe        # bangun universe pertama kali
.venv/bin/uvicorn src.web.app:app --host 0.0.0.0 --port 8002
```

## Verifikasi

```bash
python3 -m pytest src/engines/tests_fvg src/engines/tests_sfib src/engines/tests_ind tests/ -q
# 128 test hijau: 29 FVG + 25 swing-fib + 21 indicators + 53 tests/ (universe/decide/arena/telegram/config-store/db/authority)
```

## Wewenang agen (3 mode — disetel admin, default `none`)

Seberapa jauh agen (Orin) boleh mengubah sistem diatur **mode otoritas** di panel **Admin**
(ber-password `ADMIN_TOKEN`). Mode disimpan di `admin_settings.json` (TERPISAH dari `config_store`
yang agent-editable → **agen tak bisa menaikkan otoritasnya sendiri**; hanya admin/manusia bisa).

| Mode | Agen bisa |
|---|---|
| 🔒 **none** *(default)* | HANYA observasi & analisa (FVG/struktur/sentimen/sinyal/status). Tak ubah apa pun |
| ⚙️ **medium** | + set **parameter** metodologi via `config_get/set/reset` (gerbang, filter, leverage/risk/margin/tf/TTL per gaya, perp/spot, perilaku limit) + operasi dry-run |
| 🔓 **full** | + edit **KODE** (`write_source`/`run_tests` di `src/`|`tests/`, berlaku live via uvicorn `--reload`) |

Tool disaring per-mode di `roster.agent_tools_spec/impls` (bukan cuma prompt). **Batas keamanan
(tetap):** `.env`/rahasia/kunci/DB/skrip-deploy/`.git`/`.venv` DIBLOKIR tulis; anti prompt-injection
(agen tolak instruksi tulis-kode aneh dari DATA). Config divalidasi & di-clamp; berlaku live
lintas-proses (web ↔ monitor).

## Telegram (opsional)

1. Buat bot via [@BotFather](https://t.me/BotFather) → dapat token.
2. Isi `TELEGRAM_BOT_TOKEN` di `.env`, jalankan `python -m src.telegram.bot`.
3. Kirim 1 pesan ke bot — ia membalas chat ID Anda kalau belum diotorisasi. Salin ke
   `TELEGRAM_ALLOWED_CHAT_IDS`, restart.

Tanpa token, bot no-op graceful — tak menghalangi web/dry-run.

---
Bukan nasihat keuangan. Dry-run/paper saja — tidak ada dana nyata. Lihat `agents/SOUL.md`.
