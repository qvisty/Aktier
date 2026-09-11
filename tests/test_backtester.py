from backend.backtest.backtester import Backtester
from backend.strategies import MomentumStrategy
from tests.fakes import make_df, rising_series


def rise_then_fall(n_rise=65, n_fall=15):
    closes = rising_series(n_rise)
    top = closes[-1]
    closes += [top * (0.97**i) for i in range(1, n_fall + 1)]
    return closes


def test_backtest_produces_closed_trades_with_costs(settings):
    bars = {"XYZ": make_df(rise_then_fall())}
    result = Backtester(settings, [MomentumStrategy()], initial_cash=145.0).run(bars)
    closed = [t for t in result.trades if t.exit_date is not None]
    assert closed, "Forventede mindst én lukket handel"
    assert all(t.costs > 0 for t in closed)
    assert result.total_costs > 0


def test_no_look_ahead_entry_at_next_open(settings):
    bars = {"XYZ": make_df(rise_then_fall())}
    df = bars["XYZ"]
    result = Backtester(settings, [MomentumStrategy()], initial_cash=145.0).run(bars)
    trade = result.trades[0]
    # Entry skal ske til åbningskursen på entry dagen, aldrig samme dags close.
    assert trade.entry_price == float(df.loc[trade.entry_date, "open"])
    assert trade.entry_date in df.index


def test_equity_curve_and_drawdown(settings):
    bars = {"XYZ": make_df(rise_then_fall())}
    result = Backtester(settings, [MomentumStrategy()], initial_cash=145.0).run(bars)
    assert len(result.equity_curve) > 0
    assert 0.0 <= result.max_drawdown_pct <= 1.0
    assert result.final_equity > 0


def test_never_exceeds_capital(settings):
    # Fire stigende symboler, engine må maksimalt åbne max_positions positioner
    # og aldrig gå i negativ cash.
    bars = {
        sym: make_df(rising_series(80, start=50.0 + i * 10))
        for i, sym in enumerate(["AA", "BB", "CC", "DD", "EE"])
    }
    result = Backtester(settings, [MomentumStrategy()], initial_cash=145.0).run(bars)
    assert (result.equity_curve > 0).all()
    open_trades = [t for t in result.trades if t.exit_date is None]
    assert len(open_trades) <= settings.max_positions


def test_summary_has_kpis(settings):
    bars = {"XYZ": make_df(rise_then_fall())}
    summary = Backtester(settings, [MomentumStrategy()], initial_cash=145.0).run(bars).summary()
    for key in ("net_return_pct", "trades", "total_costs", "max_drawdown_pct", "win_rate_pct", "profit_factor", "expectancy"):
        assert key in summary
