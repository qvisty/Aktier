import pandas as pd

from backend.strategies.base import HeldPosition, Strategy, StrategySignal
from backend.strategies.indicators import sma


class BreakoutStrategy(Strategy):
    name = "breakout"
    default_params = {
        "breakout_window": 20,
        "exit_window": 10,
        "volume_window": 20,
        "min_volume_ratio": 1.5,
        "trend_window": 50,
    }

    def min_bars(self) -> int:
        return int(self.params["trend_window"]) + 5

    def evaluate(
        self, symbol: str, df: pd.DataFrame, held: HeldPosition | None
    ) -> StrategySignal | None:
        p = self.params
        close = df["close"]
        price = float(close.iloc[-1])

        if held is not None:
            exit_low = float(df["low"].iloc[:-1].tail(int(p["exit_window"])).min())
            if price < exit_low:
                return StrategySignal(
                    symbol=symbol,
                    side="sell",
                    strength=1.0,
                    price=price,
                    strategy=self.name,
                    reason={
                        "rule": "breakout_exit",
                        "price": price,
                        "rolling_low": round(exit_low, 4),
                        "exit_window": p["exit_window"],
                    },
                )
            return None

        prior_high = float(df["high"].iloc[:-1].tail(int(p["breakout_window"])).max())
        trend_ma = float(sma(close, int(p["trend_window"])).iloc[-1])
        vol_base = float(df["volume"].rolling(int(p["volume_window"])).mean().iloc[-1])
        vol_today = float(df["volume"].iloc[-1])
        volume_ratio = vol_today / vol_base if vol_base > 0 else 0.0

        if price > prior_high and price > trend_ma and volume_ratio >= p["min_volume_ratio"]:
            strength = price / prior_high - 1.0
            return StrategySignal(
                symbol=symbol,
                side="buy",
                strength=strength,
                price=price,
                strategy=self.name,
                reason={
                    "rule": "breakout_entry",
                    "breakout_window": p["breakout_window"],
                    "prior_high": round(prior_high, 4),
                    "price": price,
                    "volume_ratio": round(volume_ratio, 2),
                    "price_above_trend_ma": True,
                },
            )
        return None
