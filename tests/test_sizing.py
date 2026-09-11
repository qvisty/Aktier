from backend.trading.sizing import position_notional


def test_equal_weight_target(settings):
    # equity 145, buffer 5 pct, 4 positioner: 145*0.95/4 = 34.44
    notional = position_notional(145.0, 145.0, 0, settings)
    assert abs(notional - 34.44) < 0.01


def test_limited_by_settled_cash(settings):
    notional = position_notional(10.0, 145.0, 0, settings)
    assert notional <= 10.0 * 0.95 + 1e-9


def test_limited_by_max_order_value(settings):
    notional = position_notional(10_000.0, 10_000.0, 0, settings)
    assert notional == settings.max_order_value_usd


def test_no_slots_left(settings):
    assert position_notional(145.0, 145.0, 4, settings) == 0.0


def test_dust_returns_zero(settings):
    assert position_notional(0.5, 0.5, 0, settings) == 0.0
