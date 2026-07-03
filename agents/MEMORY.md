# MEMORY — Profil & Parameter Persisten

Memori kerja sistem. Perbarui saat parameter/pelajaran berubah. Identitas & wewenang:
[IDENTITY.md](IDENTITY.md); persona: [SOUL.md](SOUL.md); cara kerja: [AGENTS.md](AGENTS.md);
loop & pagar: [TASKS.md](TASKS.md).

---

## Profil pemilik (per 2026-07-02)

```
Pemilik           : almadinahsantri@gmail.com
Tujuan sistem ini : PEMBANDING independen thd crypto-trader-agent-system — win-rate/akurasi
                    sinyal sistem itu buruk, jadi metodologi BERBEDA total diuji berdampingan
Gaya              : scalping & swing (dua-duanya aktif, dry-run/paper)
```

## Parameter risiko (REAL — penyesuaian eksplisit pemilik dari default metodologi sumber)

```
Risk per trade    : 1% (scalp) · 2% (swing) dari ekuitas — dari risk%, BUKAN dari leverage
Leverage          : scalp 15x-30x · swing 8x-15x        ← BEDA dari default sumber (10-20x/5-10x)
Max posisi        : 4 per gaya (scalp DAN swing masing-masing) ← naik dari default sumber (3)
Margin cap        : ~3% ekuitas (scalp) · ~7% ekuitas (swing) — cegah over-commit di leverage tinggi
Confluence gate   : |full_score| >= 2 (FVG+Fib+OI+FR) — TAK DIUBAH dari metodologi sumber
TP                : scalp SATU TP tutup 100% di 2R (main cepat) · swing 1-3 TP by Volatility State+ATR
                    (fraksi 100 / 50-50 / 40-35-25); LEVEL dari STRUKTUR (pool likuiditas/opposing OB/Fib ext)
Entry             : FLEKSIBEL — harga di zona (FVG/OB/OTE)=MARKET; di luar=LIMIT retest zona
Booster A+        : liquidity sweep · CVD per-candle divergence · MTF divergence · RSI quality 0-100
                    — TAK DIUBAH dari metodologi sumber
```

> ⚠️ **Catatan risiko jujur:** leverage scalp 15-30x + 4 posisi bersamaan = eksposur margin
> lebih tinggi dari default sumber. Margin-cap menahan ini (notional MENYUSUT bila kepentok
> cap, bukan melonggar). Risk per-trade tetap dari risk%, tidak pernah membesar karena leverage.

## Universe (BEDA total dari metodologi sumber — penyesuaian eksplisit)

```
Sumber            : CoinMarketCap listings/latest, mcap >= $300,000,000
Exclude           : stablecoin (tag+denylist), tokenized-gold ("GOLD index"), wrapped/liquid-
                    staking, derivative denylist — sama persis dgn crypto-trader-agent-system
Syarat tradable   : harus listed Binance PERPETUAL/USDT (data & simulasi dry-run keduanya Binance)
Tier              : TERPISAH per gaya (rank-percentile → kuartil S/A/B/C): scalp=0.4·mcap+0.6·vol ·
                    swing=0.6·mcap+0.4·vol (mcap≥$300M, tradable Binance perp, refresh 24 jam)
                    (bandingkan dgn metodologi sumber: cuma 5-10 pasangan tetap)
```

## Aturan yang tidak boleh dilupakan

- Entry tanpa SL = dilarang. SL tidak pernah dilebarkan menjauh dari harga.
- `|full_score| >= 2` baru trade; selain itu SKIP — dan itu keputusan SAH, bukan kegagalan.
- FVG hanya dari engine `src/engines/fvg`; struktur/Fib/OB hanya dari `src/engines/sfib`;
  momentum/vol hanya dari `src/engines/ind` — jangan taksir visual, jangan hitung ulang sendiri.
- Dry-run/paper SAJA — tidak ada eksekusi order nyata, selamanya (lihat IDENTITY.md).
- Reset data dry-run hanya lewat UI web dengan konfirmasi manusia — tidak lewat chat.

## Catatan pasar (diisi seiring waktu)

- _(kosong — akan diisi dari pengalaman dry-run nyata)_

## Jurnal pelajaran (template — isi setelah evaluasi berkala)

```
[tanggal] gaya | n trade | win-rate | expectancy-R | apa yang benar | apa yang salah | perbaikan
```

## Apa yang DISIMPAN ke sini ke depan

- Perubahan parameter risiko/leverage/universe/tier (kalau developer manusia menyetujui usulan).
- Pelajaran berulang dari evaluasi dry-run berkala.
- JANGAN simpan: kredensial (tak ada — sistem ini dry-run murni), data pasar mentah.
