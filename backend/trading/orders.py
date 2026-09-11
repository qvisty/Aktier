"""Ordrehåndtering med idempotens, jf. PRD afsnit 24.

Hver ordre får et klientgenereret client_order_id, der gemmes med unik
constraint FØR den sendes til brokeren. Fejler kaldet mod brokeren,
slås ordren op på client_order_id, før der konkluderes noget.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.broker.base import Broker, BrokerError, BrokerOrder, OrderRequest
from backend.events import record_event
from backend.models import Execution, Order, Position, Signal


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def orders_created_today(session: Session) -> int:
    today_start = _utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    return int(
        session.scalar(select(func.count(Order.id)).where(Order.created_at >= today_start)) or 0
    )


def submit_order(
    session: Session,
    broker: Broker,
    *,
    symbol: str,
    side: str,
    notional: float | None = None,
    qty: float | None = None,
    strategy: str = "",
    signal_id: int | None = None,
) -> Order:
    order = Order(
        client_order_id=f"at-{uuid.uuid4().hex}",
        signal_id=signal_id,
        symbol=symbol,
        side=side,
        qty=qty,
        notional=notional,
        strategy=strategy,
        status="pending",
    )
    session.add(order)
    session.commit()

    request = OrderRequest(
        symbol=symbol, side=side, qty=qty, notional=notional, client_order_id=order.client_order_id
    )
    try:
        broker_order = broker.submit_order(request)
    except BrokerError as exc:
        # Netværksfejl betyder ikke nødvendigvis, at ordren ikke blev modtaget.
        existing = _safe_lookup(broker, order.client_order_id)
        if existing is not None:
            _apply_broker_order(session, order, existing)
            record_event(
                session,
                "order_recovered",
                f"Ordre {order.client_order_id} fandtes hos broker efter fejl",
                level="warning",
                details={"error": str(exc)},
            )
        else:
            order.status = "error"
            order.error = str(exc)[:255]
            session.commit()
            record_event(
                session,
                "order_error",
                f"Ordre {symbol} {side} fejlede: {exc}",
                level="warning",
                notify=True,
            )
        return order

    _apply_broker_order(session, order, broker_order)
    return order


def _safe_lookup(broker: Broker, client_order_id: str) -> BrokerOrder | None:
    try:
        return broker.get_order_by_client_id(client_order_id)
    except BrokerError:
        return None


def _apply_broker_order(session: Session, order: Order, broker_order: BrokerOrder) -> None:
    order.broker_order_id = broker_order.id
    order.status = _map_status(broker_order.status)
    session.commit()
    if order.status == "filled":
        record_fill(session, order, broker_order)


def _map_status(broker_status: str) -> str:
    mapping = {
        "new": "submitted",
        "accepted": "submitted",
        "pending_new": "submitted",
        "partially_filled": "submitted",
        "filled": "filled",
        "canceled": "canceled",
        "expired": "canceled",
        "rejected": "rejected",
    }
    return mapping.get(broker_status, "submitted")


def poll_open_orders(session: Session, broker: Broker) -> int:
    """Opdater lokale ordrer, der endnu ikke er endeligt afgjort. Returnerer antal fills."""
    open_orders = (
        session.execute(select(Order).where(Order.status.in_(["pending", "submitted"])))
        .scalars()
        .all()
    )
    fills = 0
    for order in open_orders:
        broker_order = _safe_lookup(broker, order.client_order_id)
        if broker_order is None:
            continue
        previous = order.status
        _apply_broker_order(session, order, broker_order)
        if order.status == "filled" and previous != "filled":
            fills += 1
        if order.status == "rejected":
            record_event(
                session,
                "order_rejected",
                f"Ordre {order.symbol} {order.side} afvist af broker",
                level="warning",
                notify=True,
            )
    return fills


def record_fill(session: Session, order: Order, broker_order: BrokerOrder) -> None:
    existing = session.scalar(select(Execution).where(Execution.order_id == order.id))
    if existing is not None:
        return
    execution = Execution(
        order_id=order.id,
        filled_qty=broker_order.filled_qty,
        filled_avg_price=broker_order.filled_avg_price,
        filled_at=broker_order.filled_at.replace(tzinfo=None)
        if broker_order.filled_at
        else _utcnow(),
    )
    session.add(execution)
    _update_position(session, order, broker_order)
    if order.signal_id:
        signal = session.get(Signal, order.signal_id)
        if signal is not None:
            signal.status = "executed"
    session.commit()


def _update_position(session: Session, order: Order, broker_order: BrokerOrder) -> None:
    position = session.scalar(
        select(Position).where(Position.symbol == order.symbol, Position.status == "open")
    )
    qty = broker_order.filled_qty
    price = broker_order.filled_avg_price
    if order.side == "buy":
        if position is None:
            session.add(
                Position(
                    symbol=order.symbol, qty=qty, avg_entry_price=price, strategy=order.strategy
                )
            )
        else:
            total_cost = position.qty * position.avg_entry_price + qty * price
            position.qty += qty
            position.avg_entry_price = total_cost / position.qty if position.qty > 0 else price
    else:
        if position is None:
            return
        realized = (price - position.avg_entry_price) * min(qty, position.qty)
        position.realized_pnl += realized
        position.qty -= qty
        if position.qty <= 1e-9:
            position.qty = 0.0
            position.status = "closed"
            position.closed_at = _utcnow()


def cancel_all_open_orders(session: Session, broker: Broker) -> int:
    """Annuller alle åbne ordrer hos broker og lokalt. Bruges af kill switch."""
    count = 0
    try:
        for broker_order in broker.get_open_orders():
            try:
                broker.cancel_order(broker_order.id)
                count += 1
            except BrokerError:
                pass
    except BrokerError:
        pass
    open_orders = (
        session.execute(select(Order).where(Order.status.in_(["pending", "submitted"])))
        .scalars()
        .all()
    )
    for order in open_orders:
        order.status = "canceled"
    session.commit()
    return count
