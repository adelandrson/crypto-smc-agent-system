# USER — Siapa pemilik & operator sistem

## Profil
- **Peran:** trader/peneliti kripto independen yang membangun & mengoperasikan platform ini sendiri.
- **Bahasa:** Indonesia (default semua laporan & komunikasi). Istilah teknis boleh Inggris.
- **Gaya kerja:** otonom — ingin agent **menyelesaikan** pekerjaan end-to-end, bukan bertanya tiap langkah.
- **Konteks proyek ini:** membangun sistem PEMBANDING karena sistem sebelumnya (crypto-trader-
  agent-system, pattern-screening) punya win-rate/akurasi sinyal buruk — ingin tahu jujur apakah
  metodologi SMC/FVG berbeda total memberi hasil lebih baik.

## Yang dihargai user
- **Kejujuran brutal** soal apakah ada edge — termasuk jujur kalau expectancy tetap jelek di
  sistem BARU ini juga. Jangan pernah sajikan green-theatre.
- **Metodologi diporting APA ADANYA** dari sumber terverifikasi — penyesuaian hanya pada hal
  yang eksplisit diminta (universe, leverage, posisi max, risk-management), bukan bebas
  mengubah gerbang/logic keputusan.
- **Perbandingan yang bermakna** — sistem baru harus terasa independen (persona/suara beda),
  bukan reskin sistem lama.
- **Sistem yang benar-benar jalan** end-to-end, teruji (bukan cuma unit test — live smoke test).

## Preferensi teknis yang sudah ditetapkan
- Universe: CEX-listed (Binance) + mcap >= $300M; exclude stablecoin + gold-index + derivative.
- Dry-run/paper SELAMANYA — tidak ada rencana pindah eksekusi nyata untuk sistem ini.
- Berjalan BERDAMPINGAN dengan crypto-trader-agent-system (port terpisah, DB terpisah), bukan
  menggantikannya.
- Interaksi via website (chat widget) DAN Telegram — satu otak (roster+skills), dua pintu masuk.

## Batasan keamanan dari user
- Tidak ada kredensial bursa apa pun (dry-run murni) — tak ada yang perlu dirotasi di sisi itu.
- Token Telegram bot: simpan di `.env`, jangan pernah di kode/chat.

## Cara berkomunikasi dengan user
- Status ringkas setelah tiap fase kerja besar. Surface blocker lebih awal.
- Jujur soal ketidakpastian; jangan over-claim performa dry-run dengan sampel kecil.
