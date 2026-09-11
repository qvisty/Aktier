"""FakeBroker til tests. Market ordrer fyldes øjeblikkeligt til seneste kurs."""

import uuid
from datetime import date, timedelta

import pandas as pd

from backend.broker.base import (
    Bar,
    Broker,
    BrokerAccount,
    BrokerError,
    BrokerOrder,
    BrokerPosition,
    MarketClock,
    OrderRequest,
)


def make_df(closes, volumes=None, opens=None, highs=None, lows=None, end: date | None = None):
    n = len(closes)
    end = end or date.today()
    dates = pd.bdate_range(end=pd.Timestamp(end), periods=n)
    closes = list(map(float, closes))
    return pd.DataFrame(
        {
            "open": opens or closes,
            "high": highs or closes,
            "low": lows or closes,
            "close": closes,
            "volume": volumes or [1_000_000.0] * n,
        },
        index=dates,
    )


class FakeBroker(Broker):
    def __init__(self, bars: dict[str, pd.DataFrame] | None = None, cash: float = 145.0):
        self.bars = bars or {}
        self.cash = cash
        self.equity = cash
        self.positions: dict[str, BrokerPosition] = {}
        self.orders: dict[str, BrokerOrder] = {}  # nøgle: client_order_id
        self.market_open = True
        self.fail_submit_mode: str | None = None  # None / "lost" / "received"
        self.submit_calls = 0

    # --- interface ---

    def get_account(self) -> BrokerAccount:
        return BrokerAccount(cash=self.cash, settled_cash=self.cash, equity=self.equity)

    def get_positions(self) -> list[BrokerPosition]:
        return list(self.positions.values())

    def get_open_orders(self) -> list[BrokerOrder]:
        return [o for o in self.orders.values() if o.status in ("accepted", "new")]

    def get_order_by_client_id(self, client_order_id: str) -> BrokerOrder | None:
        return self.orders.get(client_order_id)

    def submit_order(self, request: OrderRequest) -> BrokerOrder:
        self.submit_calls += 1
        if self.fail_submit_mode == "lost":
            raise BrokerError("connection reset (ordren nåede ikke frem)")
        if request.client_order_id in self.orders:
            return self.orders[request.client_order_id]
        price = self.last_price(request.symbol)
        qty = request.qty if request.qty is not None else request.notional / price
        order = BrokerOrder(
            id=uuid.uuid4().hex,
            client_order_id=request.client_order_id,
            symbol=request.symbol,
            side=request.side,
            status="filled",
            qty=request.qty,
            notional=request.notional,
            filled_qty=qty,
            filled_avg_price=price,
        )
        self.orders[request.client_order_id] = order
        self._apply_fill(order)
        if self.fail_submit_mode == "received":
            raise BrokerError("timeout (ordren nåede frem, men svaret gik tabt)")
        return order

    def cancel_order(self, broker_order_id: str) -> None:
        for order in self.orders.values():
            if order.id == broker_order_id and order.status not in ("filled",):
                order.status = "canceled"

    def get_daily_bars(self, symbols, start, end) -> dict[str, list[Bar]]:
        result = {}
        for symbol in symbols:
            df = self.bars.get(symbol)
            if df is None:
                continue
            result[symbol] = [
                Bar(
                    symbol=symbol,
                    bar_date=idx.date(),
                    open=row["open"],
                    high=row["high"],
                    low=row["low"],
                    close=row["close"],
                    volume=row["volume"],
                )
                for idx, row in df.iterrows()
                if start <= idx.date() <= end
            ]
        return result

    def get_latest_prices(self, symbols) -> dict[str, float]:
        return {s: self.last_price(s) for s in symbols if s in self.bars}

    def get_clock(self) -> MarketClock:
        return MarketClock(is_open=self.market_open)

    # --- hjælpere ---

    def last_price(self, symbol: str) -> float:
        return float(self.bars[symbol]["close"].iloc[-1])

    def _apply_fill(self, order: BrokerOrder) -> None:
        value = order.filled_qty * order.filled_avg_price
        if order.side == "buy":
            self.cash -= value
            pos = self.positions.get(order.symbol)
            if pos is None:
                self.positions[order.symbol] = BrokerPosition(
                    symbol=order.symbol,
                    qty=order.filled_qty,
                    avg_entry_price=order.filled_avg_price,
                    current_price=order.filled_avg_price,
                    market_value=value,
                )
            else:
                pos.qty += order.filled_qty
        else:
            self.cash += value
            pos = self.positions.get(order.symbol)
            if pos is not None:
                pos.qty -= order.filled_qty
                if pos.qty <= 1e-9:
                    del self.positions[order.symbol]


def rising_series(n: int = 70, start: float = 100.0, daily: float = 1.006) -> list[float]:
    return [start * daily**i for i in range(n)]
