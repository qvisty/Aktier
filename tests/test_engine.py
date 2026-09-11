from sqlalchemy import select

from backend.models import Order, Position, Signal
from backend.state import activate_kill_switch, get_marker, set_mode
from backend.trading.engine import TradingEngine
from tests.fakes import FakeBroker, make_df, rising_series


def make_engine(session, settings, cash: float = 145.0):
    settings = settings.model_copy(update={"universe": "UPUP,FLAT"})
    broker = FakeBroker(
        bars={
            "UPUP": make_df(rising_series(70)),
            "FLAT": make_df([100.0] * 70),
        },
        cash=cash,
    )
    return TradingEngine(session, broker, settings), broker


def test_cycle_ingests_generates_and_trades(session, settings):
    engine, broker = make_engine(session, settings)
    engine.cycle()

    signals = session.execute(select(Signal)).scalars().all()
    assert any(s.symbol == "UPUP" and s.side == "buy" for s in signals)
    assert all(s.symbol != "FLAT" or s.side != "buy" for s in signals)

    orders = session.execute(select(Order)).scalars().all()
    assert len(orders) == 1
    assert orders[0].symbol == "UPUP"
    assert orders[0].status == "filled"
    assert orders[0].signal_id is not None

    position = session.execute(select(Position).where(Position.status == "open")).scalar_one()
    assert position.symbol == "UPUP"
    assert position.strategy == "momentum"


def test_cycle_runs_signals_once_per_day(session, settings):
    engine, broker = make_engine(session, settings)
    engine.cycle()
    first_count = len(session.execute(select(Order)).scalars().all())
    engine.cycle()
    assert len(session.execute(select(Order)).scalars().all()) == first_count


def test_kill_switch_blocks_new_orders(session, settings):
    activate_kill_switch(session, "test")
    engine, broker = make_engine(session, settings)
    engine.cycle()
    assert session.execute(select(Order)).scalars().all() == []
    skipped = [s for s in session.execute(select(Signal)).scalars() if s.status == "skipped"]
    assert skipped
    assert any("kill_switch_active" in (s.skip_reason or "") for s in skipped)


def test_stopped_mode_does_nothing(session, settings):
    set_mode(session, "stopped")
    engine, broker = make_engine(session, settings)
    engine.cycle()
    assert session.execute(select(Signal)).scalars().all() == []
    assert get_marker(session, "last_signal_run_date") == ""


def test_closed_market_skips_signal_run(session, settings):
    engine, broker = make_engine(session, settings)
    broker.market_open = False
    engine.cycle()
    assert session.execute(select(Signal)).scalars().all() == []


def test_trade_is_explainable(session, settings):
    engine, broker = make_engine(session, settings)
    engine.cycle()
    order = session.execute(select(Order)).scalars().one()
    signal = session.get(Signal, order.signal_id)
    assert signal.reason["rule"] == "momentum_entry"
    assert signal.status == "executed"
    assert signal.strategy == "momentum"


def test_signals_skipped_when_no_capacity(session, settings):
    engine, broker = make_engine(session, settings, cash=0.5)
    engine.cycle()
    assert session.execute(select(Order)).scalars().all() == []
    skipped = [s for s in session.execute(select(Signal)).scalars() if s.status == "skipped"]
    assert any(s.skip_reason == "no_capacity" for s in skipped)


def test_stop_loss_exit_generated(session, settings):
    engine, broker = make_engine(session, settings)
    engine.cycle()
    position = session.execute(select(Position).where(Position.status == "open")).scalar_one()

    # Kursen falder 20 pct under entry, næste kørsel skal risk exit sælge.
    # Både brokerens data og den lagrede bar opdateres, enginen læser fra databasen.
    crashed = position.avg_entry_price * 0.8
    df = broker.bars["UPUP"]
    df.iloc[-1, df.columns.get_loc("close")] = crashed
    from backend.models import MarketData
    from backend.state import set_marker

    row = (
        session.execute(
            select(MarketData)
            .where(MarketData.symbol == "UPUP")
            .order_by(MarketData.bar_date.desc())
        )
        .scalars()
        .first()
    )
    row.close = crashed
    session.commit()

    set_marker(session, "last_signal_run_date", "")
    engine.cycle()

    session.refresh(position)
    assert position.status == "closed"
    sells = [
        o
        for o in session.execute(select(Order)).scalars()
        if o.side == "sell" and o.strategy == "risk_exit"
    ]
    assert len(sells) == 1
