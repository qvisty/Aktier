"""Samler data til dashboardet, jf. PRD afsnit 19."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.broker.base import Broker, BrokerError
from backend.models import Execution, Order, Position, Signal, SystemEvent
from backend.state import get_marker, get_mode, kill_switch_active, kill_switch_reason


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def build_overview(session: Session, broker: Broker | None) -> dict:
    mode = get_mode(session)
    killed = kill_switch_active(session)

    account = None
    broker_connected = False
    latest_prices: dict[str, float] = {}
    open_positions = session.execute(
        select(Position).where(Position.status == "open")
    ).scalars().all()

    if broker is not None:
        try:
            account = broker.get_account()
            broker_connected = True
            if open_positions:
                latest_prices = broker.get_latest_prices([p.symbol for p in open_positions])
        except BrokerError:
            broker_connected = False

    positions_view = []
    exposure = 0.0
    for p in open_positions:
        current = latest_prices.get(p.symbol, p.avg_entry_price)
        market_value = p.qty * current
        exposure += market_value
        positions_view.append(
            {
                "symbol": p.symbol,
                "qty": round(p.qty, 4),
                "entry": round(p.avg_entry_price, 2),
                "current": round(current, 2),
                "pnl": round((current - p.avg_entry_price) * p.qty, 2),
                "pnl_pct": round((current / p.avg_entry_price - 1) * 100, 2)
                if p.avg_entry_price
                else 0.0,
                "strategy": p.strategy,
                "opened_at": p.opened_at,
            }
        )

    recent_trades = session.execute(
        select(Execution, Order)
        .join(Order, Execution.order_id == Order.id)
        .order_by(Execution.filled_at.desc())
        .limit(20)
    ).all()
    trades_view = [
        {
            "filled_at": e.filled_at,
            "symbol": o.symbol,
            "side": o.side,
            "price": round(e.filled_avg_price, 2),
            "qty": round(e.filled_qty, 4),
            "strategy": o.strategy,
        }
        for e, o in recent_trades
    ]

    strategy_perf = []
    rows = session.execute(
        select(
            Position.strategy,
            func.count(Position.id),
            func.sum(Position.realized_pnl),
        )
        .where(Position.status == "closed")
        .group_by(Position.strategy)
    ).all()
    for strategy, count, pnl in rows:
        wins = session.scalar(
            select(func.count(Position.id)).where(
                Position.status == "closed",
                Position.strategy == strategy,
                Position.realized_pnl > 0,
            )
        ) or 0
        gross_win = session.scalar(
            select(func.sum(Position.realized_pnl)).where(
                Position.status == "closed",
                Position.strategy == strategy,
                Position.realized_pnl > 0,
            )
        ) or 0.0
        gross_loss = -(
            session.scalar(
                select(func.sum(Position.realized_pnl)).where(
                    Position.status == "closed",
                    Position.strategy == strategy,
                    Position.realized_pnl <= 0,
                )
            )
            or 0.0
        )
        strategy_perf.append(
            {
                "strategy": strategy or "ukendt",
                "closed_trades": count,
                "wins": wins,
                "win_rate": round(wins / count * 100, 1) if count else 0.0,
                "profit_factor": round(gross_win / gross_loss, 2) if gross_loss > 0 else None,
                "expectancy": round((pnl or 0.0) / count, 2) if count else 0.0,
                "net_pnl": round(pnl or 0.0, 2),
                "gate_target": 30,
                "gate_pct": min(100, round(count / 30 * 100)),
            }
        )

    recent_signals = session.execute(
        select(Signal).order_by(Signal.created_at.desc()).limit(15)
    ).scalars().all()

    recent_events = session.execute(
        select(SystemEvent).order_by(SystemEvent.ts.desc()).limit(15)
    ).scalars().all()

    critical_24h = session.scalar(
        select(func.count(SystemEvent.id)).where(
            SystemEvent.level == "critical", SystemEvent.ts >= _utcnow() - timedelta(hours=24)
        )
    )

    today_start = _utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    todays_pnl = session.scalar(
        select(func.sum(Position.realized_pnl)).where(
            Position.status == "closed", Position.closed_at >= today_start
        )
    )
    total_realized = session.scalar(
        select(func.sum(Position.realized_pnl)).where(Position.status == "closed")
    )
    unrealized = sum(p["pnl"] for p in positions_view)

    equity = account.equity if account else exposure
    cash = account.cash if account else 0.0
    settled = account.settled_cash if account else 0.0

    gate = paper_gate_status(session)

    return {
        "mode": "STOPPED" if killed or mode == "stopped" else mode.upper(),
        "raw_mode": mode,
        "kill_switch": killed,
        "kill_reason": kill_switch_reason(session),
        "portfolio_value": round(equity, 2),
        "cash": round(cash, 2),
        "settled_cash": round(settled, 2),
        "exposure": round(exposure, 2),
        "exposure_pct": round(exposure / equity * 100, 1) if equity else 0.0,
        "todays_pnl": round((todays_pnl or 0.0) + unrealized, 2),
        "total_pnl": round((total_realized or 0.0) + unrealized, 2),
        "positions": positions_view,
        "trades": trades_view,
        "strategy_perf": strategy_perf,
        "signals": recent_signals,
        "events": recent_events,
        "health": {
            "broker_connected": broker_connected,
            "critical_events_24h": critical_24h or 0,
            "last_strategy_run": get_marker(session, "last_strategy_run") or "aldrig",
            "last_reconciliation": get_marker(session, "last_reconciliation") or "aldrig",
            "database_ok": True,
        },
        "paper_gate": gate,
    }


def paper_gate_status(session: Session) -> dict:
    """Teknisk readiness før live, jf. PRD afsnit 13."""
    distinct_days = session.scalar(
        select(func.count(func.distinct(func.date(Order.created_at))))
    ) or 0
    executed = session.scalar(
        select(func.count(Execution.id))
    ) or 0
    critical_10d = session.scalar(
        select(func.count(SystemEvent.id)).where(
            SystemEvent.level == "critical",
            SystemEvent.ts >= _utcnow() - timedelta(days=10),
        )
    ) or 0
    checks = {
        "mindst_10_handelsdage": distinct_days >= 10,
        "mindst_30_handler": executed >= 30,
        "ingen_kritiske_fejl_10_dage": critical_10d == 0,
    }
    return {"checks": checks, "passed": all(checks.values()), "days": distinct_days, "executions": executed}
