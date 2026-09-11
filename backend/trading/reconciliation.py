"""Afstemning mod broker, jf. PRD afsnit 25. Brokeren er source of truth."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.broker.base import Broker, BrokerError
from backend.events import record_event
from backend.models import Position
from backend.state import activate_kill_switch

QTY_TOLERANCE = 1e-6


def reconcile(session: Session, broker: Broker) -> bool:
    """Sammenlign lokale åbne positioner med brokerens. Returnerer True hvis ok.

    Ved alvorlig uoverensstemmelse aktiveres kill switch, og der kræves
    manuel intervention.
    """
    try:
        broker_positions = {p.symbol: p.qty for p in broker.get_positions()}
    except BrokerError as exc:
        record_event(
            session, "reconciliation_skipped", f"Broker utilgængelig: {exc}", level="warning"
        )
        return True

    local_positions = {
        p.symbol: p.qty
        for p in session.execute(select(Position).where(Position.status == "open")).scalars()
    }

    mismatches = []
    for symbol in set(broker_positions) | set(local_positions):
        broker_qty = broker_positions.get(symbol, 0.0)
        local_qty = local_positions.get(symbol, 0.0)
        if abs(broker_qty - local_qty) > QTY_TOLERANCE:
            mismatches.append({"symbol": symbol, "broker_qty": broker_qty, "local_qty": local_qty})

    if mismatches:
        activate_kill_switch(session, "reconciliation_mismatch")
        record_event(
            session,
            "reconciliation_mismatch",
            f"Uoverensstemmelse mellem lokal og broker state for {len(mismatches)} symboler. "
            "Ny handel er stoppet og kræver manuel intervention.",
            level="critical",
            details={"mismatches": mismatches},
            notify=True,
        )
        return False

    record_event(session, "reconciliation_ok", "Positioner afstemt mod broker")
    return True
