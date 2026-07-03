# crypto-smc-agent-system ◈

**Sistem agen trading kripto otonom** berbasis **Smart Money Concepts (SMC)** — Fair Value Gap +
Fibonacci/Order Block/struktur BOS-CHoCH, dipadu Open Interest, Funding Rate & Long/Short Ratio
menjadi satu **confluence score deterministik (−4..+4)**. Dilengkapi **5 agen LLM** (chat website +
Telegram), **dashboard web real-time**, dan **broker dry-run** yang mensimulasikan seluruh siklus
order (entry fleksibel · SL/TP berbasis struktur · funding fee · leverage · margin).

> ⚠️ **DRY-RUN / PAPER SELAMANYA (mode saat ini).** Tidak ada API key bursa, tidak ada order nyata,
> tidak ada dana tersentuh. Tujuannya memvalidasi metodologi secara jujur sebelum (kelak) naik ke
> testnet lalu mainnet lewat gerbang berfase.

---

## Daftar isi
1. [Apa yang dibangun](#1-apa-yang-dibangun)
2. [Kenapa dibangun](#2-kenapa-dibangun)
3. [Bagaimana dibangun](#3-bagaimana-dibangun)
4. [Bagaimana sistem bekerja (pipeline)](#4-bagaimana-sistem-bekerja-pipeline)
5. [Metodologi trading (detail)](#5-metodologi-trading-detail)
6. [Fitur](#6-fitur)
7. [Keunggulan](#7-keunggulan)
8. [Arsitektur & struktur kode](#8-arsitektur--struktur-kode)
9. [Roster agen](#9-roster-agen)
10. [Halaman web](#10-halaman-web)
11. [Instalasi & menjalankan](#11-instalasi--menjalankan)
12. [Konfigurasi & wewenang agen](#12-konfigurasi--wewenang-agen)
13. [Telegram](#13-telegram)
14. [Pengujian](#14-pengujian)
15. [Keamanan & batasan](#15-keamanan--batasan)
16. [Peta jalan ke uang-asli](#16-peta-jalan-ke-uang-asli)

---

## 1. Apa yang dibangun

Sebuah **platform trading agentik** yang, untuk setiap koin di semesta pilihannya, menghitung sebuah
skor keyakinan (**confluence**) dari beberapa "kaki" analisis independen, lalu — bila skornya cukup
kuat dan lolos semua filter — **membuka posisi simulasi** dengan manajemen risiko penuh (SL/TP
berbasis struktur, leverage, funding). Semua keputusan trading **deterministik** (bukan hasil LLM);
LLM hanya dipakai untuk **menjelaskan, meringkas, dan mengoperasikan** sistem lewat chat.

Dua gaya trading berjalan berdampingan:
- **Scalp** — timeframe 5m, hold menit–jam, 1 TP tutup 100%, leverage 15–30×.
- **Swing** — timeframe 4h, hold hari–minggu, 1–3 TP dinamis, leverage 8–15×.

## 2. Kenapa dibangun

- **Pendekatan pattern-screening (win-rate & akurasi buruk) tidak ditambal, tapi dibandingkan.**
  Sistem ini adalah **pembanding independen** dengan metodologi berbeda total (SMC), supaya bisa
  diukur *apples-to-apples* mana yang lebih baik — bukan menebak.
- **Kejujuran metrik di atas ilusi win-rate.** Metodologi SMC di sini punya *hit-rate* sinyal sering
  **< 50%**, TAPI **ekspektasi positif** karena rasio risk:reward. Karena itu **metrik utama =
  expectancy-R & ROI**, bukan win-rate mentah. Banyak `skip` itu **normal & sehat**.
- **Determinisme = bisa diaudit & direproduksi.** Keputusan entry/exit tidak bergantung pada LLM yang
  bisa berubah-ubah; setiap trade bisa ditelusuri ke angka confluence yang sama.
- **Aman dulu, uang belakangan.** Dry-run penuh dulu; jalur ke testnet lalu mainnet diatur bertahap
  dengan kriteria lulus terukur (lihat [§16](#16-peta-jalan-ke-uang-asli)).

## 3. Bagaimana dibangun

| Lapisan | Teknologi | Catatan |
|---|---|---|
| **Engine analisis** | Python **stdlib murni** (tanpa dependensi) | FVG, swing/Fib/OB, indikator — deterministik, tiap engine punya test sendiri |
| **Confluence & keputusan** | Python | Gabung engine → skor −4..+4 → `decide()` (entry/SL/TP/leverage) |
| **Broker dry-run** | SQLAlchemy + SQLite | Siklus pending→fill→kelola, funding, fee, slippage — DB-backed lintas-proses |
| **Data pasar** | REST publik Binance (candle/OI/FR/LSR) + **CoinMarketCap** (semesta) | Analisa & data **tanpa API key**; CMC pakai key untuk daftar koin |
| **Web** | **FastAPI** + Uvicorn, SSE | Dashboard + chat streaming |
| **Agen** | LLM tool-calling (OpenAI-compatible) | 5 persona, wewenang berjenjang |
| **Telegram** | long-polling (`requests`) | Satu otak, dua pintu masuk (web + Telegram) |

Prinsip rekayasa: **engine analisis nol-dependensi & teruji**, **keputusan trading terpisah dari LLM**,
**data publik dulu** (key hanya untuk hal yang wajib).

## 4. Bagaimana sistem bekerja (pipeline)

```
                    ┌─────────────────────────────────────────────┐
   CoinMarketCap →  │ 1. SEMESTA (universe.py)                     │
                    │    mcap ≥ $300M · exclude stablecoin/gold/   │
                    │    derivative · tradable Binance perp        │
                    │    → tier TERPISAH scalp & swing (S/A/B/C)   │
                    └──────────────────┬──────────────────────────┘
                                       │ tiap koin, per gaya
                    ┌──────────────────▼──────────────────────────┐
   Binance REST  →  │ 2. DATA per simbol                          │
   (publik)         │    candle (putusan di candle TERTUTUP) +    │
                    │    OI · Funding · LSR · taker-volume        │
                    └──────────────────┬──────────────────────────┘
                    ┌──────────────────▼──────────────────────────┐
                    │ 3. CONFLUENCE (−4..+4)                       │
                    │    FVG + Fibonacci/OB/BOS-CHoCH + OI + FR    │
                    │    + booster A+: liquidity sweep · CVD ·     │
                    │      MTF divergence · RSI quality            │
                    └──────────────────┬──────────────────────────┘
                    ┌──────────────────▼──────────────────────────┐
                    │ 4. GERBANG & FILTER                          │
                    │    |score| ≥ 2 · disiplin zona (long=disc./  │
                    │    short=prem.) · anti-ranging · volume OK · │
                    │    LSR kontrarian · GERBANG FUNDING          │
                    └──────────────────┬──────────────────────────┘
                    ┌──────────────────▼──────────────────────────┐
                    │ 5. RENCANA TRADE (decide)                    │
                    │    entry FLEKSIBEL (market bila di zona,     │
                    │    limit bila retest) · SL struktur ·        │
                    │    qty dari risk% · leverage dari kerapatan  │
                    │    SL · TP dari Volatility+ATR & struktur    │
                    └──────────────────┬──────────────────────────┘
                    ┌──────────────────▼──────────────────────────┐
                    │ 6. BROKER DRY-RUN (arena.py)                 │
                    │    pending→fill-on-touch→kelola INTRA-BAR    │
                    │    (SL/TP saat harga menyentuh) · funding    │
                    │    fee · fee taker · slippage · evolusi SL   │
                    └──────────────────┬──────────────────────────┘
                    ┌──────────────────▼──────────────────────────┐
                    │ 7. DASHBOARD + AGEN                          │
                    │    posisi · harga terkini · unrealized PnL · │
                    │    harga TP · funding · ROI/expectancy ·     │
                    │    chat (web + Telegram)                     │
                    └─────────────────────────────────────────────┘
```

**Loop operasional** (`monitor`, tiap ~20 dtk): kelola posisi terbuka & pending → pindai semesta →
buka posisi baru bila ada sinyal. Dashboard **refresh tiap 1 detik** (harga terkini di-cache 3 dtk
di server agar tak membanjiri Binance).

### Detail penting yang menentukan kejujuran hasil
- **Putusan ENTRY di candle TERTUTUP.** Candle berjalan punya volume/OHLC parsial → bisa membias
  filter volume & menyebabkan repaint. Semua analisa entry memakai candle yang sudah selesai.
- **Manajemen SL/TP INTRA-BAR.** Order SL/TP itu order tersimpan yang tereksekusi *begitu harga
  menyentuhnya*, tak menunggu candle tutup. Karena itu manajemen posisi memakai high/low bar berjalan
  (timeframe gaya: scalp 5m, swing 4h) — mencegah bias optimistik "SL terlewat".

## 5. Metodologi trading (detail)

**Confluence score (−4..+4)** = FVG + Fibonacci + Open Interest + Funding Rate. Sinyal hanya
dipertimbangkan bila **|score| ≥ 2** (`full_strong`). Booster A+ (overlap Fib×FVG, retest Order Block,
**liquidity sweep/EQH-EQL**, **MTF divergence**, **RSI quality 0–100**) mempertajam kualitas tanpa
mengubah rentang skor.

**Filter SKIP (semua wajib lolos):**
- Disiplin zona: **long hanya di discount, short hanya di premium**.
- Anti-*ranging* (vol_state), anti *volume anomaly* (volume di bawah rata-rata).
- LSR kontrarian: crowd ekstrem melawan arah → veto.
- **Gerbang funding**: bila posisi akan **MEMBAYAR** funding yang tinggi (adverse), entry ditolak —
  ada dua ambang: **absolut** (> 0.1%/8j → tolak) dan **relatif** (estimasi biaya funding selama hold
  > 35% dari jarak profit ke TP1). Funding yang **DITERIMA** (menguntungkan posisi) tak pernah memblokir.
- **Lapis anti crime-pump/dump** (koin **tier A ke bawah**): pembeda utama (riset data nyata) =
  **rasio spike volume 90 hari** = `peak_$vol / median_baseline_$vol`. Rally ORGANIK/legit (good-news
  & adopsi: Pyth/Near/Aave/HBAR ≤~**10×**) vs **MANIPULASI** (Manta/LAB/Rave ≥~**30×**) — ambang **15×**
  (pemisahan bersih) + safety mcap-ceiling $5B (koin raksasa sulit dimanipulasi). Pump-macro dinilai di
  **1D (90 hari)**, distribusi-final lintas TF **1D→4h→1h→15m** (yang cepat spt Manta ketangkap di TF
  halus). Aksi:
  - **BLOKIR LONG** selama harga masih di puncak pump.
  - **SHORT hanya bila DISTRIBUSI FINAL** — dinilai **multi-timeframe (1D→4h→1h→15m)** karena crime-pump
    ada yang lambat (LAB/Rave/OM) & sangat cepat (Manta): TF halus menangkap yang cepat lebih awal.
    Dua syarat: (1) harga **sideways di atas** (high berkelompok) + **beberapa wick-rejection atas**;
    (2) **local-peak volume** di tengah sideways (lebih tinggi dari tetangga kiri-kanan — **bukan**
    volume tertinggi keseluruhan) pada candle wick-rejection. **SL = wick tertinggi saat sideways**
    (local); **TP 100% ≈ ≤1% di atas harga pra-pump**. **ENTRY:** market di area sideways bila **RR ≥
    1:3**; bila harga sudah di bawah floor RR-1:3 → **skip** (telat). *(Long diblokir di semua kasus
    pump; short hanya pada setup RR≥3 — pump yang dump seketika seperti Manta: long diblokir, short di-skip.)*

**Entry FLEKSIBEL** — harga kini **sudah di zona** (FVG/OB/OTE) → **market**; belum → **limit** di
retest zona (pending → terisi saat pullback / batal bila TTL habis atau harga kabur).

**Risiko & sizing:**
- **SL berbasis STRUKTUR** (di luar FVG/swing + buffer), tak pernah dilebarkan.
- **Ukuran dari risk%** (bukan leverage): scalp 0.5% · swing 1% ekuitas per trade.
- **Leverage dari kerapatan SL**: scalp 15–30× · swing 8–15× (SL rapat → mendekati batas atas).
  Leverage **tak** menaikkan risiko per-trade — hanya menentukan margin yang dikomit.
- **Margin-cap** (scalp 1.5% · swing 3.5% ekuitas) membatasi over-commit di leverage tinggi.
- **Maks 10 posisi** per gaya (agregat: scalp ≤5% risiko/15% margin; swing ≤10%/35%).

**Take-profit:**
- **Scalp = SATU TP tutup 100%** di 2R (main cepat, tanpa staging).
- **Swing = 1–3 TP** — *jumlah* dari **Volatility State + ATR** (trending/breakout→3, mixed→2,
  ranging→1); *penempatan level* dari **STRUKTUR** (pool likuiditas lawan / opposing Order Block /
  Fibonacci extension), fallback R-multiple bila struktur kurang.
- **Evolusi SL**: BE setelah TP1 → lock-TP1 setelah TP2 → trailing.

**Funding fee disimulasikan** (long bayar saat rate>0, short menerima; akrual proporsional per 8 jam)
dan masuk ke PnL — supaya expectancy mencerminkan biaya nyata perp.

## 6. Fitur

- **Confluence deterministik −4..+4** dari 3 engine SMC + sentimen derivatif.
- **Semesta CMC dinamis** ≥$300M dengan **tier terpisah scalp/swing** (S/A/B/C), refresh 24 jam.
- **Entry fleksibel** market/limit + siklus limit-order penuh (pending→fill→cancel).
- **TP adaptif**: scalp 1×100%, swing 1–3 dinamis, level dari struktur pasar.
- **Gerbang funding** untuk menghindari funding rate tinggi yang menggerus PnL.
- **Deteksi crime-pump/dump** koin tier rendah (baseline volume kecil → spike): blokir long di puncak,
  cari short saat distribusi selesai dengan target harga pra-pump.
- **Simulasi realistis**: fee taker, slippage, **funding fee**, evolusi SL, manajemen intra-bar.
- **Dashboard live** (refresh 1 dtk): harga terkini, **unrealized PnL**, harga TP eksplisit, margin
  $/% dari equity, notional (×leverage), funding rate & fee.
- **ROI per gaya** (total termasuk posisi terbuka + realized dari trade tutup) + **expectancy-R** &
  win-rate — metrik jujur, bukan cuma WR.
- **5 agen LLM** dengan tool-calling (analisa, sentimen, dry-run, evaluasi) di web & Telegram.
- **Wewenang agen 3 mode** (tanpa/menengah/penuh) yang dikontrol admin.
- **Panel admin** ber-password: mode otoritas, model LLM, kunci rahasia, parameter metodologi.
- **Format angka rapi**: harga 5/4 angka penting, quantity dipadatkan, funding & % jelas.

## 7. Keunggulan

- **Keputusan trading DETERMINISTIK & teruji** — bisa diaudit, direproduksi, tak "halusinasi" LLM.
- **Metrik jujur (expectancy-R + ROI)** — tak menjual ilusi win-rate tinggi.
- **Sadar-funding** — menolak trade yang funding-nya akan memakan profit (jarang ada di sistem lain).
- **Berbasis struktur, bukan % hafalan** — SL & TP mengikuti likuiditas/OB/Fib nyata pasar.
- **Anti-repaint di entry, realistis di eksekusi** — putusan pada candle tertutup, tapi SL/TP dieksekusi
  intra-bar seperti order nyata (tak ada bias optimistik).
- **Nol dependensi di jantungnya** — engine pure-stdlib, mudah dipindah & di-embed.
- **Aman-dulu** — dry-run permanen, tanpa kunci withdraw, secret di `.env`, wewenang agen berjenjang.
- **Data publik** — analisa & sinyal tak butuh API key bursa.

## 8. Arsitektur & struktur kode

```
src/
├── engines/                # 3 engine SMC (stdlib murni) + test masing-masing
│   ├── fvg/                #   Fair Value Gap
│   ├── sfib/               #   swing/Fibonacci/Order Block/BOS-CHoCH + liquidity sweep
│   └── ind/                #   RSI/ADX/ATR/Bollinger/volume-z + RSI-quality + MTF divergence
├── smc/
│   ├── confluence.py       # gabung engine → skor −4..+4 + booster A+
│   ├── decide.py           # rencana trade (entry/SL/TP/leverage) + GROUPS config per gaya
│   ├── risk.py             # sizing, SL struktur, TP struktur, leverage, funding fee & gate
│   ├── arena.py            # broker dry-run DB-backed (pending/fill/kelola/step/monitor/summary)
│   ├── universe.py         # semesta CMC + tier terpisah scalp/swing
│   ├── sentiment.py        # agregasi OI/Funding/LSR/CVD
│   ├── config_store.py     # parameter metodologi yang bisa disetel (divalidasi & di-clamp)
│   └── admin_settings.py   # mode wewenang agen (agent-write-blocked)
├── storage/models.py       # Token(+tier,24h), DryRunTrade(+funding), DryRunFill, Signal, ChatSession
├── agents/roster.py        # 5 agen: persona, tool per-agen, filter tool per-mode-otoritas
├── llm/{client,skills}.py  # klien LLM + registry skill (analisa/status/config/ops)
├── web/{app.py,static/}    # FastAPI (chat SSE + /api/*) + UI (dark, gauge confluence, kartu posisi)
└── telegram/bot.py         # jembatan Telegram (opsional)
agents/*.md                 # konstitusi agen: IDENTITY/SOUL/AGENTS/MEMORY/TASKS/USER
tests/ + src/engines/tests_*/# 131 test (engine + confluence + broker + universe + config + agen)
```

## 9. Roster agen

| Agen | Peran |
|---|---|
| **Orin** (Orchestrator) | Koordinasi, chat website & Telegram, sintesis jawaban |
| **Vega** (Struktur & Imbalance) | FVG + Fibonacci/OTE + Order Block + BOS/CHoCH |
| **Arka** (Sentimen Derivatif) | Open Interest + Funding Rate + LSR + momentum/volatilitas |
| **Wira** (Eksekutor Dry-Run) | Sizing, SL struktur, TP (scalp single/swing 1–3), entry fleksibel, leverage |
| **Bayu** (Evaluator) | Expectancy-R & ROI jujur (bukan win-rate mentah), universe/tier |

Semua keputusan trading tetap deterministik di kode; agen memberi analisa, ringkasan & operasi.

## 10. Halaman web

- **Analisa** — rincian confluence per koin (FVG/Fib/OB/zona + sentimen), skor gauge.
- **Sinyal** — kandidat scalp & swing yang lolos `|score| ≥ 2`.
- **Universe** — daftar tier S/A/B/C dengan **% naik/turun 24 jam**, mcap, volume.
- **Agent** — dashboard dry-run: **ROI total & realized per gaya**, expectancy, posisi terbuka
  (harga terkini, unrealized PnL, harga TP, margin/notional, funding), pending, riwayat.
- **Admin** — ber-password: mode wewenang agen, model LLM, kunci rahasia, parameter metodologi.

## 11. Instalasi & menjalankan

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env            # isi minimal CMC_API_KEY (+ LLM & Telegram bila dipakai)

.venv/bin/python -m src.smc.universe               # bangun semesta pertama kali
.venv/bin/uvicorn src.web.app:app --host 127.0.0.1 --port 8002   # web + API

# (opsional) loop dry-run otomatis:
.venv/bin/python -m src.smc.arena monitor --interval=20
```

Buka `http://127.0.0.1:8002`. Sistem berjalan penuh **tanpa API key bursa** (data publik); CMC key
untuk semesta.

## 12. Konfigurasi & wewenang agen

**Parameter metodologi** (di-clamp ke rentang aman, bisa disetel via panel Admin atau chat saat mode
mengizinkan): gerbang `min_abs_score`, on/off tiap filter SKIP & disiplin zona, leverage/risk/margin/
timeframe/TTL per gaya, `max_open`, sumber data (perp/spot), **ambang gerbang funding**.

**Wewenang agen — 3 mode (disetel admin, default `none`):**

| Mode | Agen boleh |
|---|---|
| 🔒 **none** *(default)* | HANYA observasi & analisa. Tak mengubah apa pun |
| ⚙️ **medium** | + setel **parameter** metodologi + operasi dry-run |
| 🔓 **full** | + edit **KODE** (`write_source`/`run_tests` di `src/`\|`tests/`, berlaku live) |

Mode disimpan terpisah (`admin_settings.json`, **agen tak bisa menaikkan otoritasnya sendiri** — hanya
admin/manusia). Batas keamanan tetap: `.env`/rahasia/kunci/DB/`.git`/`.venv` **diblokir tulis**;
anti-prompt-injection (agen menolak instruksi tulis-kode dari data eksternal).

Password admin = `ADMIN_TOKEN` di `.env` runtime.

## 13. Telegram

1. Buat bot via [@BotFather](https://t.me/BotFather) → dapat token.
2. Isi `TELEGRAM_BOT_TOKEN` di `.env`, jalankan `python -m src.telegram.bot` (atau lewat service).
3. Kirim 1 pesan; bot membalas chat ID-mu bila belum diotorisasi. Salin ke
   `TELEGRAM_ALLOWED_CHAT_IDS`, restart.

Bot memakai **otak yang sama** dengan chat website. Tanpa token, bot no-op (tak mengganggu web).

## 14. Pengujian

```bash
python3 -m pytest src/engines/tests_fvg src/engines/tests_sfib src/engines/tests_ind tests/ -q
# 131 test hijau — engine (FVG/swing-fib/indikator) + confluence + broker (pending/fill/kelola/
# TP staging/SL evolution/funding) + universe/tier + config + agen/authority
```

Setiap engine punya test isolasinya; broker & keputusan diuji dengan SQLite in-memory tanpa network.
Prinsip: **hijau berarti perilaku nyata bekerja** — bukan test dilemahkan.

## 15. Keamanan & batasan

- **Dry-run/paper permanen** (mode ini): tanpa order nyata, tanpa dana, tanpa kunci trading.
- **Tanpa withdraw**: kalaupun kelak ke bursa nyata, izin API wajib **trade-only, tanpa withdraw**.
- **Secret di `.env`** (di-`.gitignore`): `.env`, `*.db`, `.venv`, log, `admin_settings.json` tak
  pernah di-commit.
- **Fill = simulasi** (fee taker + slippage + funding) — perkiraan, bukan eksekusi nyata; validasi
  akhir tetap di testnet bursa.
- **Hit-rate sinyal < 50%** *by design* — nilai dipanen dari R:R (expectancy), bukan frekuensi menang.
  Kumpulkan ≥ 20–30 trade sebelum menilai.

## 16. Peta jalan ke uang-asli

Bertahap dengan kriteria lulus terukur, **venue-agnostik** (Binance / Bybit / Hyperliquid = pilihan
pengguna):

```
Dry-run (kini) → Walk-forward/OOS → Dry-run forward panjang → TESTNET bursa-pilihan
              → Mainnet canary (kecil) → Scale-up
```

Naik level hanya setelah gerbang terpenuhi **dan** sign-off manusia. Selama itu, metrik jujur
(expectancy-R, ROI, distribusi R) jadi penentu — bukan satu-dua trade beruntung.

---

**Bukan nasihat keuangan.** Dry-run/paper saja — tidak ada dana nyata yang dipertaruhkan. Lihat
`agents/SOUL.md` untuk prinsip & karakter sistem.
