"""Broker interface, jf. PRD afsnit 7. Alle beløb er i kontoens valuta (USD)."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime


@dataclass
class BrokerAccount:
    cash: float
    settled_cash: float
    equity: float
    currency: str = "USD"


@dataclass
class BrokerPosition:
    symbol: str
    qty: float
    avg_entry_price: float
    current_price: float
    market_value: float


@dataclass
class BrokerOrder:
    id: str
    client_order_id: str
    symbol: str
    side: str  # buy / sell
    status: str  # accepted / filled / partially_filled / canceled / rejected / expired
    qty: float | None = None
    notional: float | None = None
    filled_qty: float = 0.0
    filled_avg_price: float = 0.0
    submitted_at: datetime | None = None
    filled_at: datetime | None = None


@dataclass
class Bar:
    symbol: str
    bar_date: date
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass
class MarketClock:
    is_open: bool
    next_open: datetime | None = None
    next_close: datetime | None = None


@dataclass
class OrderRequest:
    symbol: str
    side: str
    client_order_id: str
    qty: float | None = None
    notional: float | None = None
    extra: dict = field(default_factory=dict)


class BrokerError(Exception):
    pass


class Broker(ABC):
    """Abstrakt broker. Strategier og engine kender kun dette interface."""

    @abstractmethod
    def get_account(self) -> BrokerAccount: ...

    @abstractmethod
    def get_positions(self) -> list[BrokerPosition]: ...

    @abstractmethod
    def get_open_orders(self) -> list[BrokerOrder]: ...

    @abstractmethod
    def get_order_by_client_id(self, client_order_id: str) -> BrokerOrder | None: ...

    @abstractmethod
    def submit_order(self, request: OrderRequest) -> BrokerOrder: ...

    @abstractmethod
    def cancel_order(self, broker_order_id: str) -> None: ...

    @abstractmethod
    def get_daily_bars(self, symbols: list[str], start: date, end: date) -> dict[str, list[Bar]]: ...

    @abstractmethod
    def get_latest_prices(self, symbols: list[str]) -> dict[str, float]: ...

    @abstractmethod
    def get_clock(self) -> MarketClock: ...
