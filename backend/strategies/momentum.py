import pandas as pd

from backend.strategies.base import HeldPosition, Strategy, StrategySignal
from backend.strategies.indicators import roc, sma


class MomentumStrategy(Strategy):
    name = "momentum"
    default_params = {
        "roc_window": 20,
        "min_roc": 0.05,
        "trend_window": 50,
        "exit_ma_window": 20,
        "volume_window": 20,
        "volume_recent": 5,
        "min_volume_ratio": 1.0,
    }

    def min_bars(self) -> int:
        return int(self.params["trend_window"]) + 5

    def evaluate(
        self, symbol: str, df: pd.DataFrame, held: HeldPosition | None
    ) -> StrategySignal | None:
        p = self.params
        close = df["close"]
        price = float(close.iloc[-1])
        momentum = float(roc(close, int(p["roc_window"])).iloc[-1])
        trend_ma = float(sma(close, int(p["trend_window"])).iloc[-1])
        exit_ma = float(sma(close, int(p["exit_ma_window"])).iloc[-1])
        vol_recent = float(df["volume"].tail(int(p["volume_recent"])).mean())
        vol_base = float(df["volume"].rolling(int(p["volume_window"])).mean().iloc[-1])
        volume_ratio = vol_recent / vol_base if vol_base > 0 else 0.0

        if held is not None:
            if price < exit_ma or momentum < 0:
                return StrategySignal(
                    symbol=symbol,
                    side="sell",
                    strength=abs(momentum),
                    price=price,
                    strategy=self.name,
                    reason={
                        "rule": "momentum_exit",
                        "price": price,
                        "exit_ma": round(exit_ma, 4),
                        "roc": round(momentum, 4),
                    },
                )
            return None

        if momentum >= p["min_roc"] and price > trend_ma and volume_ratio >= p["min_volume_ratio"]:
            return StrategySignal(
                symbol=symbol,
                side="buy",
                strength=momentum,
                price=price,
                strategy=self.name,
                reason={
                    "rule": "momentum_entry",
                    "roc_window": p["roc_window"],
                    "roc": round(momentum, 4),
                    "price_above_trend_ma": True,
                    "trend_ma": round(trend_ma, 4),
                    "volume_ratio": round(volume_ratio, 2),
                },
            )
        return None
