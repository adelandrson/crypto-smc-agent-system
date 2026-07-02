"""Parity & correctness on cached real Binance OHLC snapshots (tests/data/).

The engine is checked against an INDEPENDENT brute-force oracle written here
from scratch — if they agree on real market data, the engine faithfully
implements the FVG spec. Skipped automatically if the data snapshot is absent.
"""

from pathlib import Path

import pytest

from fvg import Config, compute, load_csv, normalize_bars

DATA = Path(__file__).resolve().parent / "data"
# A representative subset across symbols and timeframes (keeps the suite fast).
SUBSET = ["BTCUSDT_1h.csv", "ETHUSDT_15m.csv", "SOLUSDT_4h.csv", "BNBUSDT_5m.csv"]


def _available():
    return [DATA / name for name in SUBSET if (DATA / name).exists()]


def _oracle(bars, enable_inverse=True):
    """Independent naive detection + mitigation + inverse (threshold=none)."""
    n = len(bars)
    H = [b.high for b in bars]
    L = [b.low for b in bars]
    C = [b.close for b in bars]

    def resolve(direction, top, bottom, formed):
        mit = fil = inv = None
        for j in range(formed + 1, n):
            if direction == "bullish":
                touched, far, through = L[j] <= top, L[j] <= bottom, C[j] < bottom
            else:
                touched, far, through = H[j] >= bottom, H[j] >= top, C[j] > top
            if touched and mit is None:
                mit = j
            if far and fil is None:
                fil = j
            if through:
                inv = j
                break
        return mit, fil, inv

    gaps = set()
    for i in range(2, n):
        if L[i] > H[i - 2]:
            d, top, bottom = "bullish", L[i], H[i - 2]
        elif H[i] < L[i - 2]:
            d, top, bottom = "bearish", L[i - 2], H[i]
        else:
            continue
        m, f, v = resolve(d, top, bottom, i)
        gaps.add((d, round(top, 8), round(bottom, 8), i, m, f, v, False))
        if enable_inverse and v is not None:
            od = "bearish" if d == "bullish" else "bullish"
            m2, f2, v2 = resolve(od, top, bottom, v)
            gaps.add((od, round(top, 8), round(bottom, 8), v, m2, f2, v2, True))
    return gaps


def _engine(bars_input):
    _, base, _, _ = compute(
        bars_input, Config(threshold_mode="none", mitigation_mode="wick")
    )
    return {
        (f.direction.value, round(f.top, 8), round(f.bottom, 8), f.formed_index,
         f.mitigated_index, f.filled_index, f.invalidated_index, f.is_inverse)
        for f in base
    }


@pytest.mark.parametrize("path", _available(), ids=lambda p: p.stem)
def test_engine_matches_oracle_on_real_data(path):
    bars = load_csv(str(path))
    assert len(bars) > 100
    assert _engine(load_csv(str(path))) == _oracle(bars), f"divergence on {path.stem}"


@pytest.mark.parametrize("path", _available(), ids=lambda p: p.stem)
def test_state_invariants_on_real_data(path):
    bars_input = load_csv(str(path))
    _, base, _, _ = compute(bars_input, Config(threshold_mode="none"))
    for f in base:
        assert f.top > f.bottom
        if f.filled_index is not None and f.mitigated_index is not None:
            assert f.mitigated_index <= f.filled_index
        if f.invalidated_index is not None and f.mitigated_index is not None:
            assert f.mitigated_index <= f.invalidated_index


def test_detection_is_causal_on_real_data():
    """A gap formed at bar i must be detectable from bars[:i+1] alone."""
    paths = _available()
    if not paths:
        pytest.skip("no real-data snapshot available")
    bars_input = load_csv(str(paths[0]))[:300]  # slice keeps the recompute cheap
    cfg = Config(threshold_mode="none")
    _, base, _, _ = compute(bars_input, cfg)
    for f in base:
        if f.is_inverse:
            continue
        _, pbase, _, _ = compute(bars_input[: f.formed_index + 1], cfg)
        assert any(
            (not p.is_inverse)
            and p.formed_index == f.formed_index
            and abs(p.top - f.top) < 1e-9
            and abs(p.bottom - f.bottom) < 1e-9
            for p in pbase
        ), f"gap at {f.formed_index} not causal"


def test_calibrated_default_reduces_noise():
    """The calibrated default (atr/0.25) must keep fewer gaps than raw none."""
    paths = _available()
    if not paths:
        pytest.skip("no real-data snapshot available")
    bars_input = load_csv(str(paths[0]))
    _, raw, _, _ = compute(bars_input, Config(threshold_mode="none"))
    _, filt, _, _ = compute(bars_input, Config())  # defaults = atr/0.25
    raw_base = [f for f in raw if not f.is_inverse]
    filt_base = [f for f in filt if not f.is_inverse]
    assert 0 < len(filt_base) < len(raw_base)
