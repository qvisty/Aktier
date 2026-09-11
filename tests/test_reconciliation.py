from backend.models import Position
from backend.state import kill_switch_active
from backend.trading.reconciliation import reconcile
from tests.fakes import FakeBroker, make_df, rising_series


def test_matching_state_passes(session):
    broker = FakeBroker(bars={"AAPL": make_df(rising_series(70))})
    assert reconcile(session, broker) is True
    assert not kill_switch_active(session)


def test_mismatch_halts_trading(session):
    broker = FakeBroker(bars={"AAPL": make_df(rising_series(70))})
    session.add(Position(symbol="AAPL", qty=2.0, avg_entry_price=100.0, strategy="momentum"))
    session.commit()
    assert reconcile(session, broker) is False
    assert kill_switch_active(session)


def test_kill_switch_survives_restart(session):
    broker = FakeBroker(bars={"AAPL": make_df(rising_series(70))})
    session.add(Position(symbol="AAPL", qty=2.0, avg_entry_price=100.0, strategy="momentum"))
    session.commit()
    reconcile(session, broker)
    # En ny session mod samme database simulerer en genstart.
    assert kill_switch_active(session)
