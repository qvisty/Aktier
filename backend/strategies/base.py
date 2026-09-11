"""Fælles strategiinterface, jf. PRD afsnit 9.

Samme strategikode bruges af både backtester og live engine.
En strategi ser kun bars til og med beslutningsdagen. Kolonner:
open, high, low, close, volume, indekseret på dato, stigende.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import pandas as pd


@dataclass
class HeldPosition:
    symbol: str
    qty: float
    avg_entry_price: float
    strategy: str
    holding_days: int = 0


@dataclass
class StrategySignal:
    symbol: str
    side: str  # buy / sell
    strength: float
    price: float
    strategy: str
    reason: dict = field(default_factory=dict)


class Strategy(ABC):
    name: str = "base"
    default_params: dict = {}

    def __init__(self, params: dict | None = None):
        self.params = {**self.default_params, **(params or {})}

    def generate(
        self, bars: dict[str, pd.DataFrame], positions: dict[str, HeldPosition]
    ) -> list[StrategySignal]:
        signals: list[StrategySignal] = []
        min_bars = self.min_bars()
        for symbol, df in bars.items():
            if df is None or len(df) < min_bars:
                continue
            held = positions.get(symbol)
            if held is not None and held.strategy not in ("", self.name):
                # En anden strategi ejer positionen, rør den ikke.
                held = None
                sig = self.evaluate(symbol, df, None)
            else:
                sig = self.evaluate(symbol, df, held)
            if sig is not None:
                if sig.side == "buy" and symbol in positions:
                    continue
                if sig.side == "sell" and held is None:
                    continue
                signals.append(sig)
        return signals

    @abstractmethod
    def evaluate(
        self, symbol: str, df: pd.DataFrame, held: HeldPosition | None
    ) -> StrategySignal | None: ...

    def min_bars(self) -> int:
        return 60
