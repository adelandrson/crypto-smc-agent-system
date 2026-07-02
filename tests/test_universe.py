"""Test src/smc/universe.py pure logic (_exclude_reason, _tier) — no network."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.smc import universe


def test_exclude_stablecoin_by_tag():
    assert universe._exclude_reason({"symbol": "USDT", "tags": ["stablecoin"]}) == "stablecoin"


def test_exclude_stablecoin_by_denylist():
    assert universe._exclude_reason({"symbol": "FDUSD", "tags": []}) == "stablecoin"


def test_exclude_gold_index_tag():
    r = universe._exclude_reason({"symbol": "PAXG", "tags": ["tokenized-gold"]})
    assert r == "tokenized-gold"


def test_exclude_derivative_denylist():
    assert universe._exclude_reason({"symbol": "WBTC", "tags": []}) == "derivative"


def test_no_exclusion_for_major():
    assert universe._exclude_reason({"symbol": "BTC", "tags": ["mineable", "pow"]}) is None


def test_tier_thresholds():
    assert universe._tier(2_000_000_000) == "S"
    assert universe._tier(500_000_000) == "A"
    assert universe._tier(80_000_000) == "B"
    assert universe._tier(15_000_000) == "C"
    assert universe._tier(1_000_000) is None   # below tier C -> unranked
    assert universe._tier(None) is None
