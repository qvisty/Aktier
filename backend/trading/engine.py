"""Trading engine, jf. PRD afsnit 14 og 18.

Flow pr. cyklus:
market data → strategisignaler → ranking → risk checks → sizing →
ordrer → execution opfølgning → database. Signalgenerering kører én
gang pr. handelsdag, mens fills og reconciliation følges løbende.
"""

import logging
from datetime import date, datetime, timedelta, timezone

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.broker.base import Broker, BrokerError
from backend.config import Settings
from backend.events import record_event
from backend.models import MarketData, Order, Position, Signal
from backend.risk.rules import OrderCandidate, RiskContext, check_order, edge_is_sufficient
from backend.state import MODE_STOPPED, get_mode, kill_switch_active, get_marker, set_marker
from backend.strategies import ALL_STRATEGIES
from backend.strategies.base import HeldPosition, Strategy
from backend.trading import orders as order_manager
from backend.trading.reconciliation import reconcile
from backend.trading.sizing import position_notional

log = logging.getLogger("autotrader.engine")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class TradingEngine:
    def __init__(self, session: Session, broker: Broker, settings: Settings, strategies: list[Strategy] | None = None):
        self.session = session
        self.broker = broker
        self.settings = settings
        self.strategies = strategies if strategies is not None else [cls() for cls in ALL_STRATEGIES.values()]

    # --- Datahåndtering ---

    def ingest_market_data(self, today: date | None = None) -> int:
        today = today or _utcnow().date()
        start = today - timedelta(days=self.settings.history_days)
        symbols = self.settings.universe_symbols()
        bars = self.broker.get_daily_bars(symbols, start, today)
        inserted = 0
        for symbol, symbol_bars in bars.items():
            existing_dates = {
                d
                for (d,) in self.session.execute(
                    select(MarketData.bar_date).where(
                        MarketData.symbol == symbol, MarketData.bar_date >= start
                    )
                )
            }
            for bar in symbol_bars:
                if bar.bar_date in existing_dates:
                    continue
                self.session.add(
                    MarketData(
                        symbol=symbol,
                        bar_date=bar.bar_date,
                        open=bar.open,
                        high=bar.high,
                        low=bar.low,
                        close=bar.close,
                        volume=bar.volume,
                    )
                )
                inserted += 1
        self.session.commit()
        return inserted

    def load_bars(self) -> dict[str, pd.DataFrame]:
        symbols = self.settings.universe_symbols()
        cutoff = _utcnow().date() - timedelta(days=self.settings.history_days)
        result: dict[str, pd.DataFrame] = {}
        for symbol in symbols:
            rows = self.session.execute(
                select(MarketData)
                .where(MarketData.symbol == symbol, MarketData.bar_date >= cutoff)
                .order_by(MarketData.bar_date)
            ).scalars().all()
            if not rows:
                continue
            result[symbol] = pd.DataFrame(
                {
                    "open": [r.open for r in rows],
                    "high": [r.high for r in rows],
                    "low": [r.low for r in rows],
                    "close": [r.close for r in rows],
                    "volume": [r.volume for r in rows],
                },
                index=pd.to_datetime([r.bar_date for r in rows]),
            )
        return result

    def open_positions(self) -> dict[str, Position]:
        rows = self.session.execute(
            select(Position).where(Position.status == "open")
        ).scalars().all()
        return {p.symbol: p for p in rows}

    # --- Hovedcyklus ---

    def cycle(self) -> None:
        mode = get_mode(self.session)
        if mode == MODE_STOPPED:
            return

        try:
            order_manager.poll_open_orders(self.session, self.broker)
        except BrokerError as exc:
            record_event(self.session, "broker_error", f"Fill opfølgning fejlede: {exc}", level="warning")

        self._maybe_reconcile()

        today = _utcnow().date().isoformat()
        if get_marker(self.session, "last_signal_run_date") == today:
            return
        try:
            clock = self.broker.get_clock()
        except BrokerError as exc:
            record_event(self.session, "broker_error", f"Clock kald fejlede: {exc}", level="warning")
            return
        if not clock.is_open:
            return

        try:
            self.ingest_market_data()
        except BrokerError as exc:
            record_event(self.session, "data_error", f"Data ingestion fejlede: {exc}", level="warning")
            return

        self.run_signals()
        set_marker(self.session, "last_signal_run_date", today)
        set_marker(self.session, "last_strategy_run", _utcnow().isoformat())

    def _maybe_reconcile(self) -> None:
        marker = get_marker(self.session, "last_reconciliation")
        if marker:
            last = datetime.fromisoformat(marker)
            if _utcnow() - last < timedelta(hours=1):
                return
        reconcile(self.session, self.broker)
        set_marker(self.session, "last_reconciliation", _utcnow().isoformat())

    # --- Signaler og ordrer ---

    def run_signals(self) -> list[Order]:
        bars = self.load_bars()
        positions = self.open_positions()
        held = {
            symbol: HeldPosition(
                symbol=symbol,
                qty=p.qty,
                avg_entry_price=p.avg_entry_price,
                strategy=p.strategy,
                holding_days=(_utcnow() - p.opened_at).days,
            )
            for symbol, p in positions.items()
        }

        signals = self._risk_exit_signals(bars, held)
        for strategy in self.strategies:
            try:
                signals.extend(strategy.generate(bars, held))
            except Exception as exc:  # en strategifejl må ikke stoppe de andre
                record_event(
                    self.session,
                    "strategy_error",
                    f"Strategi {strategy.name} fejlede: {exc}",
                    level="warning",
                )

        persisted = self._persist_signals(signals)
        return self._execute_signals(persisted, bars, positions)

    def _risk_exit_signals(
        self, bars: dict[str, pd.DataFrame], held: dict[str, HeldPosition]
    ) -> list:
        from backend.strategies.base import StrategySignal

        signals = []
        for symbol, pos in held.items():
            df = bars.get(symbol)
            if df is None or df.empty:
                continue
            price = float(df["close"].iloc[-1])
            loss_pct = 1.0 - price / pos.avg_entry_price if pos.avg_entry_price > 0 else 0.0
            if loss_pct >= self.settings.stop_loss_pct:
                signals.append(
                    StrategySignal(
                        symbol=symbol,
                        side="sell",
                        strength=10.0 + loss_pct,
                        price=price,
                        strategy="risk_exit",
                        reason={
                            "rule": "stop_loss",
                            "loss_pct": round(loss_pct, 4),
                            "entry": pos.avg_entry_price,
                            "price": price,
                        },
                    )
                )
            elif pos.holding_days >= self.settings.max_holding_days:
                signals.append(
                    StrategySignal(
                        symbol=symbol,
                        side="sell",
                        strength=10.0,
                        price=price,
                        strategy="risk_exit",
                        reason={"rule": "max_holding_days", "holding_days": pos.holding_days},
                    )
                )
        return signals

    def _persist_signals(self, signals) -> list[Signal]:
        rows = []
        expires = _utcnow() + timedelta(minutes=self.settings.signal_ttl_minutes)
        for s in signals:
            row = Signal(
                strategy=s.strategy,
                symbol=s.symbol,
                side=s.side,
                strength=s.strength,
                price=s.price,
                reason=s.reason,
                expires_at=expires,
            )
            self.session.add(row)
            rows.append(row)
        self.session.commit()
        return rows

    def _execute_signals(
        self,
        signals: list[Signal],
        bars: dict[str, pd.DataFrame],
        positions: dict[str, Position],
    ) -> list[Order]:
        try:
            account = self.broker.get_account()
        except BrokerError as exc:
            record_event(self.session, "broker_error", f"Konto kald fejlede: {exc}", level="warning")
            for s in signals:
                s.status = "skipped"
                s.skip_reason = "broker_unavailable"
            self.session.commit()
            return []

        try:
            latest_prices = self.broker.get_latest_prices(list(bars.keys()))
        except BrokerError:
            latest_prices = {s: float(df["close"].iloc[-1]) for s, df in bars.items() if not df.empty}

        today = _utcnow().date()
        bar_age = {
            s: (today - df.index[-1].date()).days for s, df in bars.items() if not df.empty
        }
        pending_symbols = {
            o.symbol
            for o in self.session.execute(
                select(Order).where(Order.status.in_(["pending", "submitted"]))
            ).scalars()
        }

        ctx = RiskContext(
            settled_cash=account.settled_cash,
            equity=account.equity,
            open_position_count=len(positions),
            held_qty={s: p.qty for s, p in positions.items()},
            orders_today=order_manager.orders_created_today(self.session),
            latest_prices=latest_prices,
            bar_age_days=bar_age,
            kill_switch=kill_switch_active(self.session),
            mode=get_mode(self.session),
        )

        submitted: list[Order] = []
        seen_symbols: set[str] = set()
        # Salg altid før køb, så settled cash frigives korrekt, og
        # risk exits har højeste styrke.
        ordered = sorted(signals, key=lambda s: (s.side != "sell", -s.strength))
        for signal in ordered:
            if signal.symbol in seen_symbols or signal.symbol in pending_symbols:
                signal.status = "skipped"
                signal.skip_reason = "duplicate_symbol"
                continue

            if signal.side == "buy":
                if not edge_is_sufficient(signal.strength, self.settings):
                    signal.status = "skipped"
                    signal.skip_reason = "edge_below_costs"
                    continue
                notional = position_notional(
                    ctx.settled_cash, ctx.equity, ctx.open_position_count, self.settings
                )
                if notional <= 0:
                    signal.status = "skipped"
                    signal.skip_reason = "no_capacity"
                    continue
                candidate = OrderCandidate(
                    symbol=signal.symbol, side="buy", notional=notional, signal_price=signal.price
                )
            else:
                position = positions.get(signal.symbol)
                if position is None:
                    signal.status = "skipped"
                    signal.skip_reason = "no_position"
                    continue
                candidate = OrderCandidate(
                    symbol=signal.symbol,
                    side="sell",
                    notional=position.qty * signal.price,
                    signal_price=signal.price,
                    qty=position.qty,
                )

            result = check_order(candidate, ctx, self.settings)
            if not result.ok:
                signal.status = "skipped"
                signal.skip_reason = ",".join(result.reasons)[:255]
                continue

            order = order_manager.submit_order(
                self.session,
                self.broker,
                symbol=candidate.symbol,
                side=candidate.side,
                notional=candidate.notional if candidate.side == "buy" else None,
                qty=candidate.qty if candidate.side == "sell" else None,
                strategy=signal.strategy,
                signal_id=signal.id,
            )
            submitted.append(order)
            seen_symbols.add(signal.symbol)
            ctx.orders_today += 1
            if candidate.side == "buy":
                ctx.settled_cash -= candidate.notional
                ctx.open_position_count += 1

        self.session.commit()
        try:
            order_manager.poll_open_orders(self.session, self.broker)
        except BrokerError:
            pass
        return submitted
