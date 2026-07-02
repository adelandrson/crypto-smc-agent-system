"""Konfigurasi terpusat — crypto-smc-agent-system. Semua diambil dari .env."""
import os

from dotenv import load_dotenv

load_dotenv()

# --- API keys ---
CMC_API_KEY = os.getenv("CMC_API_KEY", "")

# --- Storage ---
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///crypto_smc.db")

# --- LLM (OpenAI-compatible). DEFAULT KOSONG: diisi via .env. ---
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "")
LLM_MODEL_ORCH = os.getenv("LLM_MODEL_ORCH", "")
LLM_MODEL_LIGHT = os.getenv("LLM_MODEL_LIGHT", "")

# --- Admin panel web (kosong = admin nonaktif) ---
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")

# --- Telegram bridge (kosong = bot tidak start, lihat src/telegram/bot.py) ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_ALLOWED_CHAT_IDS = {c.strip() for c in os.getenv("TELEGRAM_ALLOWED_CHAT_IDS", "").split(",") if c.strip()}

# --- Universe: CEX (Binance) mcap >= $300M, exclude stablecoin/gold-index/derivative ---
MARKETCAP_FLOOR = int(os.getenv("MARKETCAP_FLOOR", "300000000"))

# --- Denylist stablecoin (pelengkap tag CMC) — sama persis dgn crypto-trader-agent-system ---
STABLECOIN_DENYLIST = {
    "USDT", "USDC", "DAI", "FDUSD", "TUSD", "USDE", "PYUSD", "USDS",
    "CRVUSD", "GHO", "USDD", "FRAX", "LUSD", "USDP", "BUSD", "SUSD",
}

# --- Tag CMC yang dikecualikan (termasuk tokenized-gold = "GOLD index") ---
EXCLUDED_TAGS = {
    "wrapped-tokens",
    "liquid-staking-derivatives",
    "liquid-staking",
    "tokenized-gold",
    "tokenized-assets",
    "tokenized-stock",
}
# Jaring pengaman bila tag CMC tidak lengkap.
DERIVATIVE_DENYLIST = {
    "WETH", "WBTC", "WBETH", "WSTETH", "STETH", "WEETH", "CBBTC",
    "AETHWETH", "RETH", "CBETH", "PAXG", "XAUT", "EZETH", "RSETH",
}
FIAT_MARKERS = ("USD", "EUR", "GBP", "JPY", "CNY")
PEG_PRICE_LOW = 0.95
PEG_PRICE_HIGH = 1.05

# --- Tier volume 24h (S/A/B/C) — heuristik awal, tunable ---
TIER_THRESHOLDS = {"S": 1_000_000_000, "A": 200_000_000, "B": 50_000_000, "C": 10_000_000}
