import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from backend.models import Execution, Order, Position
from backend.trading.orders import poll_open_orders, submit_order
from tests.fakes import FakeBroker, make_df, rising_series


def make_broker() -> FakeBroker:
    return FakeBroker(bars={"AAPL": make_df(rising_series(70))})


def test_successful_order_records_fill_and_position(session):
    broker = make_broker()
    order = submit_order(session, broker, symbol="AAPL", side="buy", notional=30.0, strategy="momentum")
    assert order.status == "filled"
    assert order.broker_order_id is not None
    executions = session.execute(select(Execution)).scalars().all()
    assert len(executions) == 1
    position = session.execute(select(Position).where(Position.status == "open")).scalar_one()
    assert position.symbol == "AAPL"
    assert position.qty > 0


def test_client_order_id_unique_constraint(session):
    session.add(Order(client_order_id="dup", symbol="AAPL", side="buy"))
    session.commit()
    session.add(Order(client_order_id="dup", symbol="AAPL", side="buy"))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_lost_submit_marks_error_without_duplicate(session):
    broker = make_broker()
    broker.fail_submit_mode = "lost"
    order = submit_order(session, broker, symbol="AAPL", side="buy", notional=30.0)
    assert order.status == "error"
    assert len(broker.orders) == 0
    assert session.execute(select(Position)).scalars().all() == []


def test_received_submit_recovers_via_client_order_id(session):
    # Brokeren modtog ordren, men svaret gik tabt. Ordren skal genfindes,
    # ikke sendes igen.
    broker = make_broker()
    broker.fail_submit_mode = "received"
    order = submit_order(session, broker, symbol="AAPL", side="buy", notional=30.0)
    assert order.status == "filled"
    assert len(broker.orders) == 1
    executions = session.execute(select(Execution)).scalars().all()
    assert len(executions) == 1


def test_poll_does_not_duplicate_executions(session):
    broker = make_broker()
    order = submit_order(session, broker, symbol="AAPL", side="buy", notional=30.0)
    assert order.status == "filled"
    poll_open_orders(session, broker)
    poll_open_orders(session, broker)
    executions = session.execute(select(Execution)).scalars().all()
    assert len(executions) == 1


def test_sell_closes_position_with_realized_pnl(session):
    broker = make_broker()
    submit_order(session, broker, symbol="AAPL", side="buy", notional=30.0)
    position = session.execute(select(Position).where(Position.status == "open")).scalar_one()
    submit_order(session, broker, symbol="AAPL", side="sell", qty=position.qty)
    session.refresh(position)
    assert position.status == "closed"
    assert position.qty == 0.0
