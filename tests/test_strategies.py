from backend.strategies import BreakoutStrategy, MeanReversionStrategy, MomentumStrategy
from backend.strategies.base import HeldPosition
from tests.fakes import make_df, rising_series


def test_momentum_buys_rising_series():
    df = make_df(rising_series(70))
    signals = MomentumStrategy().generate({"XYZ": df}, {})
    assert len(signals) == 1
    sig = signals[0]
    assert sig.side == "buy"
    assert sig.strategy == "momentum"
    assert sig.reason["rule"] == "momentum_entry"
    assert sig.strength > 0.05


def test_momentum_ignores_flat_series():
    df = make_df([100.0] * 70)
    assert MomentumStrategy().generate({"XYZ": df}, {}) == []


def test_momentum_sells_when_trend_breaks():
    closes = rising_series(60) + [100.0, 95.0, 90.0, 85.0, 80.0]
    df = make_df(closes)
    held = {"XYZ": HeldPosition(symbol="XYZ", qty=1.0, avg_entry_price=100.0, strategy="momentum")}
    signals = MomentumStrategy().generate({"XYZ": df}, held)
    assert len(signals) == 1
    assert signals[0].side == "sell"


def test_momentum_does_not_buy_when_already_held():
    df = make_df(rising_series(70))
    held = {"XYZ": HeldPosition(symbol="XYZ", qty=1.0, avg_entry_price=100.0, strategy="momentum")}
    signals = MomentumStrategy().generate({"XYZ": df}, held)
    # En stigende serie giver ikke exit, og køb er blokeret, når positionen findes.
    assert all(s.side != "buy" for s in signals)


def test_mean_reversion_buys_oversold():
    closes = [100.0] * 40 + [99.0, 97.0, 95.0, 92.0, 89.0, 86.0]
    df = make_df(closes)
    signals = MeanReversionStrategy().generate({"XYZ": df}, {})
    assert len(signals) == 1
    sig = signals[0]
    assert sig.side == "buy"
    assert sig.reason["rule"] == "mean_reversion_entry"
    assert sig.reason["rsi"] < 30
    assert sig.reason["zscore"] < -2


def test_mean_reversion_exits_after_normalization():
    closes = [100.0] * 40 + [90.0, 92.0, 95.0, 98.0, 100.0, 101.0]
    df = make_df(closes)
    held = {"XYZ": HeldPosition(symbol="XYZ", qty=1.0, avg_entry_price=90.0, strategy="mean_reversion")}
    signals = MeanReversionStrategy().generate({"XYZ": df}, held)
    assert len(signals) == 1
    assert signals[0].side == "sell"


def test_breakout_buys_on_new_high_with_volume():
    closes = [100.0] * 60 + [106.0]
    volumes = [1_000_000.0] * 60 + [2_500_000.0]
    df = make_df(closes, volumes=volumes)
    signals = BreakoutStrategy().generate({"XYZ": df}, {})
    assert len(signals) == 1
    sig = signals[0]
    assert sig.side == "buy"
    assert sig.reason["rule"] == "breakout_entry"


def test_breakout_requires_volume():
    closes = [100.0] * 60 + [106.0]
    df = make_df(closes)  # konstant volumen, ratio 1.0 < 1.5
    assert BreakoutStrategy().generate({"XYZ": df}, {}) == []


def test_strategy_skips_symbols_with_too_little_data():
    df = make_df([100.0] * 10)
    assert MomentumStrategy().generate({"XYZ": df}, {}) == []


def test_strategy_does_not_touch_other_strategys_position():
    closes = rising_series(60) + [100.0, 95.0, 90.0, 85.0, 80.0]
    df = make_df(closes)
    held = {"XYZ": HeldPosition(symbol="XYZ", qty=1.0, avg_entry_price=100.0, strategy="breakout")}
    signals = MomentumStrategy().generate({"XYZ": df}, held)
    assert all(s.side != "sell" for s in signals)
