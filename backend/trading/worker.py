"""24/7 trading worker, jf. PRD afsnit 18 og 23. Kør: python -m backend.trading.worker"""

import logging
import time

from backend.broker.alpaca import make_broker_from_settings
from backend.config import get_settings
from backend.db import get_session
from backend.events import record_event
from backend.models import Order
from backend.state import get_mode
from backend.trading.engine import TradingEngine
from backend.trading.reconciliation import reconcile

from sqlalchemy import select

log = logging.getLogger("autotrader.worker")


def startup_recovery() -> None:
    """Efter genstart: afstem åbne ordrer og positioner, før drift genoptages."""
    settings = get_settings()
    session = get_session()
    try:
        mode = get_mode(session)
        broker = make_broker_from_settings(settings, mode)
        if broker is None:
            record_event(session, "startup", "Worker startet uden broker konfiguration", level="warning")
            return
        record_event(session, "startup", f"Worker startet i mode={mode}")
        from backend.trading import orders as order_manager

        order_manager.poll_open_orders(session, broker)
        stale = session.execute(
            select(Order).where(Order.status == "pending")
        ).scalars().all()
        for order in stale:
            found = broker.get_order_by_client_id(order.client_order_id)
            if found is None:
                order.status = "error"
                order.error = "not_found_at_broker_after_restart"
        session.commit()
        reconcile(session, broker)
    finally:
        session.close()


def run_forever() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    settings = get_settings()
    startup_recovery()
    while True:
        session = get_session()
        try:
            mode = get_mode(session)
            broker = make_broker_from_settings(settings, mode)
            if broker is not None:
                engine = TradingEngine(session, broker, settings)
                engine.cycle()
        except Exception as exc:
            log.exception("Ubehandlet fejl i engine cyklus")
            try:
                record_event(
                    session,
                    "engine_crash",
                    f"Ubehandlet fejl i engine cyklus: {exc}",
                    level="critical",
                    notify=True,
                )
            except Exception:
                pass
        finally:
            session.close()
        time.sleep(settings.engine_interval_seconds)


if __name__ == "__main__":
    run_forever()
