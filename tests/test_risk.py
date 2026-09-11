from backend.risk.rules import OrderCandidate, RiskContext, check_order, edge_is_sufficient


def ctx(**overrides) -> RiskContext:
    base = dict(
        settled_cash=145.0,
        equity=145.0,
        open_position_count=0,
        held_qty={},
        orders_today=0,
        latest_prices={"AAPL": 100.0},
        bar_age_days={"AAPL": 0},
        kill_switch=False,
        mode="paper",
    )
    base.update(overrides)
    return RiskContext(**base)


def buy(notional=30.0, price=100.0) -> OrderCandidate:
    return OrderCandidate(symbol="AAPL", side="buy", notional=notional, signal_price=price)


def test_valid_buy_passes(settings):
    assert check_order(buy(), ctx(), settings).ok


def test_kill_switch_blocks(settings):
    result = check_order(buy(), ctx(kill_switch=True), settings)
    assert not result.ok
    assert "kill_switch_active" in result.reasons


def test_stopped_mode_blocks(settings):
    assert not check_order(buy(), ctx(mode="stopped"), settings).ok


def test_max_order_value(settings):
    result = check_order(buy(notional=150.0), ctx(settled_cash=1000.0, equity=1000.0), settings)
    assert not result.ok
    assert any(r.startswith("max_order_value_exceeded") for r in result.reasons)


def test_insufficient_settled_cash(settings):
    result = check_order(buy(notional=95.0), ctx(settled_cash=50.0), settings)
    assert not result.ok
    assert any(r.startswith("insufficient_settled_cash") for r in result.reasons)


def test_cash_buffer_reserved(settings):
    # 145 * 0.95 = 137.75, så 140 skal afvises selv om cash er 145.
    result = check_order(
        buy(notional=140.0), ctx(settled_cash=145.0, equity=1000.0), settings
    )
    assert any(r.startswith("insufficient_settled_cash") for r in result.reasons)


def test_max_positions(settings):
    result = check_order(buy(), ctx(open_position_count=4), settings)
    assert not result.ok
    assert any(r.startswith("max_positions_reached") for r in result.reasons)


def test_daily_order_limit(settings):
    result = check_order(buy(), ctx(orders_today=10), settings)
    assert not result.ok
    assert any(r.startswith("daily_order_limit") for r in result.reasons)


def test_stale_data_blocks(settings):
    result = check_order(buy(), ctx(bar_age_days={"AAPL": 9}), settings)
    assert not result.ok
    assert any(r.startswith("stale_data") for r in result.reasons)


def test_missing_data_blocks(settings):
    result = check_order(buy(), ctx(bar_age_days={}), settings)
    assert "no_market_data" in result.reasons


def test_price_sanity(settings):
    result = check_order(buy(price=100.0), ctx(latest_prices={"AAPL": 150.0}), settings)
    assert not result.ok
    assert any(r.startswith("price_sanity") for r in result.reasons)


def test_sell_without_position_blocked(settings):
    candidate = OrderCandidate(symbol="AAPL", side="sell", notional=30.0, signal_price=100.0, qty=1.0)
    result = check_order(candidate, ctx(), settings)
    assert "no_position_to_sell" in result.reasons


def test_sell_more_than_held_blocked(settings):
    candidate = OrderCandidate(symbol="AAPL", side="sell", notional=300.0, signal_price=100.0, qty=3.0)
    result = check_order(candidate, ctx(held_qty={"AAPL": 1.0}), settings)
    assert any(r.startswith("sell_exceeds_position") for r in result.reasons)


def test_edge_must_exceed_costs(settings):
    required = settings.roundtrip_cost_pct() + settings.min_edge_margin_pct
    assert not edge_is_sufficient(required * 0.5, settings)
    assert edge_is_sufficient(required * 2, settings)
