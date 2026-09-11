"""Backtester, jf. PRD afsnit 11.

Deler strategikode med live enginen. Ingen look ahead: signaler
beregnes på bars til og med dag t og eksekveres til åbningskursen
dag t+1 med spread, slippage og gebyrer. Settled cash modelleres
med T+1, provenu fra salg kan først bruges næste handelsdag.
"""

from dataclasses import dataclass, field

import pandas as pd

from backend.config import Settings
from backend.strategies.base import HeldPosition, Strategy


@dataclass
class BacktestTrade:
    symbol: str
    strategy: str
    entry_date: pd.Timestamp
    exit_date: pd.Timestamp | None
    entry_price: float
    exit_price: float | None
    qty: float
    costs: float
    net_pnl: float | None
    reason_entry: dict = field(default_factory=dict)
    reason_exit: dict = field(default_factory=dict)


@dataclass
class BacktestResult:
    initial_cash: float
    final_equity: float
    net_return_pct: float
    trades: list[BacktestTrade]
    equity_curve: pd.Series
    total_costs: float
    max_drawdown_pct: float
    win_rate: float
    profit_factor: float
    expectancy: float

    def summary(self) -> dict:
        return {
            "initial_cash": round(self.initial_cash, 2),
            "final_equity": round(self.final_equity, 2),
            "net_return_pct": round(self.net_return_pct * 100, 2),
            "trades": len([t for t in self.trades if t.exit_date is not None]),
            "total_costs": round(self.total_costs, 2),
            "max_drawdown_pct": round(self.max_drawdown_pct * 100, 2),
            "win_rate_pct": round(self.win_rate * 100, 1),
            "profit_factor": round(self.profit_factor, 2),
            "expectancy": round(self.expectancy, 4),
        }


@dataclass
class _OpenLot:
    symbol: str
    strategy: str
    qty: float
    entry_price: float
    entry_date: pd.Timestamp
    entry_costs: float
    reason: dict


class Backtester:
    def __init__(self, settings: Settings, strategies: list[Strategy], initial_cash: float = 145.0):
        self.settings = settings
        self.strategies = strategies
        self.initial_cash = initial_cash

    def _trade_cost(self, notional: float) -> float:
        s = self.settings
        return notional * (s.cost_spread_pct + s.cost_slippage_pct) + s.cost_fixed_per_order_usd

    def run(self, bars: dict[str, pd.DataFrame]) -> BacktestResult:
        all_dates = sorted({d for df in bars.values() for d in df.index})
        settled_cash = self.initial_cash
        pending_settlement = 0.0  # frigives næste handelsdag (T+1)
        open_lots: dict[str, _OpenLot] = {}
        trades: list[BacktestTrade] = []
        equity_points: dict[pd.Timestamp, float] = {}
        min_bars = max(s.min_bars() for s in self.strategies) if self.strategies else 60

        for i, today in enumerate(all_dates):
            settled_cash += pending_settlement
            pending_settlement = 0.0

            view = {
                symbol: df.loc[:today]
                for symbol, df in bars.items()
                if today in df.index and len(df.loc[:today]) >= min_bars
            }
            held = {
                symbol: HeldPosition(
                    symbol=symbol,
                    qty=lot.qty,
                    avg_entry_price=lot.entry_price,
                    strategy=lot.strategy,
                    holding_days=(today - lot.entry_date).days,
                )
                for symbol, lot in open_lots.items()
            }

            signals = self._risk_exits(view, open_lots, today)
            for strategy in self.strategies:
                signals.extend(strategy.generate(view, held))

            if i + 1 >= len(all_dates):
                # Sidste dag, ingen næste åbning at eksekvere til.
                equity_points[today] = self._mark_equity(
                    settled_cash + pending_settlement, open_lots, view
                )
                break
            next_date = all_dates[i + 1]

            seen: set[str] = set()
            for sig in sorted(signals, key=lambda s: (s.side != "sell", -s.strength)):
                if sig.symbol in seen:
                    continue
                df = bars.get(sig.symbol)
                if df is None or next_date not in df.index:
                    continue
                fill_price = float(df.loc[next_date, "open"])

                if sig.side == "sell" and sig.symbol in open_lots:
                    lot = open_lots.pop(sig.symbol)
                    proceeds = lot.qty * fill_price
                    cost = self._trade_cost(proceeds)
                    pending_settlement += proceeds - cost
                    net = proceeds - cost - lot.qty * lot.entry_price - lot.entry_costs
                    trades.append(
                        BacktestTrade(
                            symbol=lot.symbol,
                            strategy=lot.strategy,
                            entry_date=lot.entry_date,
                            exit_date=next_date,
                            entry_price=lot.entry_price,
                            exit_price=fill_price,
                            qty=lot.qty,
                            costs=lot.entry_costs + cost,
                            net_pnl=net,
                            reason_entry=lot.reason,
                            reason_exit=sig.reason,
                        )
                    )
                    seen.add(sig.symbol)
                elif sig.side == "buy" and sig.symbol not in open_lots:
                    if len(open_lots) >= self.settings.max_positions:
                        continue
                    equity = self._mark_equity(settled_cash + pending_settlement, open_lots, view)
                    notional = min(
                        equity * (1.0 - self.settings.cash_buffer_pct) / self.settings.max_positions,
                        settled_cash * (1.0 - self.settings.cash_buffer_pct),
                        self.settings.max_order_value_usd,
                    )
                    if notional < 1.0:
                        continue
                    cost = self._trade_cost(notional)
                    if notional + cost > settled_cash:
                        notional = settled_cash - cost
                        if notional < 1.0:
                            continue
                    qty = notional / fill_price
                    settled_cash -= notional + cost
                    open_lots[sig.symbol] = _OpenLot(
                        symbol=sig.symbol,
                        strategy=sig.strategy,
                        qty=qty,
                        entry_price=fill_price,
                        entry_date=next_date,
                        entry_costs=cost,
                        reason=sig.reason,
                    )
                    seen.add(sig.symbol)

            equity_points[today] = self._mark_equity(settled_cash + pending_settlement, open_lots, view)

        equity_curve = pd.Series(equity_points).sort_index()
        final_equity = float(equity_curve.iloc[-1]) if len(equity_curve) else self.initial_cash
        closed = [t for t in trades if t.net_pnl is not None]
        wins = [t for t in closed if t.net_pnl > 0]
        losses = [t for t in closed if t.net_pnl <= 0]
        gross_win = sum(t.net_pnl for t in wins)
        gross_loss = -sum(t.net_pnl for t in losses)
        return BacktestResult(
            initial_cash=self.initial_cash,
            final_equity=final_equity,
            net_return_pct=final_equity / self.initial_cash - 1.0,
            trades=trades,
            equity_curve=equity_curve,
            total_costs=sum(t.costs for t in trades),
            max_drawdown_pct=self._max_drawdown(equity_curve),
            win_rate=len(wins) / len(closed) if closed else 0.0,
            profit_factor=gross_win / gross_loss if gross_loss > 0 else float("inf") if gross_win > 0 else 0.0,
            expectancy=sum(t.net_pnl for t in closed) / len(closed) if closed else 0.0,
        )

    def _risk_exits(self, view: dict[str, pd.DataFrame], open_lots: dict[str, _OpenLot], today) -> list:
        from backend.strategies.base import StrategySignal

        signals = []
        for symbol, lot in open_lots.items():
            df = view.get(symbol)
            if df is None or df.empty:
                continue
            price = float(df["close"].iloc[-1])
            loss_pct = 1.0 - price / lot.entry_price
            holding_days = (today - lot.entry_date).days
            if loss_pct >= self.settings.stop_loss_pct:
                signals.append(
                    StrategySignal(
                        symbol=symbol,
                        side="sell",
                        strength=10.0 + loss_pct,
                        price=price,
                        strategy="risk_exit",
                        reason={"rule": "stop_loss", "loss_pct": round(loss_pct, 4)},
                    )
                )
            elif holding_days >= self.settings.max_holding_days:
                signals.append(
                    StrategySignal(
                        symbol=symbol,
                        side="sell",
                        strength=10.0,
                        price=price,
                        strategy="risk_exit",
                        reason={"rule": "max_holding_days", "holding_days": holding_days},
                    )
                )
        return signals

    @staticmethod
    def _mark_equity(cash: float, open_lots: dict[str, _OpenLot], view: dict[str, pd.DataFrame]) -> float:
        value = cash
        for symbol, lot in open_lots.items():
            df = view.get(symbol)
            price = float(df["close"].iloc[-1]) if df is not None and len(df) else lot.entry_price
            value += lot.qty * price
        return value

    @staticmethod
    def _max_drawdown(equity: pd.Series) -> float:
        if equity.empty:
            return 0.0
        running_max = equity.cummax()
        drawdown = 1.0 - equity / running_max
        return float(drawdown.max())
