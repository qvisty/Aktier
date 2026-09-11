import pandas as pd

from backend.strategies.base import HeldPosition, Strategy, StrategySignal
from backend.strategies.indicators import rsi, zscore


class MeanReversionStrategy(Strategy):
    name = "mean_reversion"
    default_params = {
        "rsi_window": 14,
        "rsi_buy": 30.0,
        "rsi_exit": 55.0,
        "zscore_window": 20,
        "zscore_buy": -2.0,
        "zscore_exit": 0.0,
    }

    def min_bars(self) -> int:
        return max(int(self.params["rsi_window"]), int(self.params["zscore_window"])) + 10

    def evaluate(
        self, symbol: str, df: pd.DataFrame, held: HeldPosition | None
    ) -> StrategySignal | None:
        p = self.params
        close = df["close"]
        price = float(close.iloc[-1])
        rsi_now = float(rsi(close, int(p["rsi_window"])).iloc[-1])
        z_now = float(zscore(close, int(p["zscore_window"])).iloc[-1])

        if held is not None:
            if rsi_now >= p["rsi_exit"] or z_now >= p["zscore_exit"]:
                return StrategySignal(
                    symbol=symbol,
                    side="sell",
                    strength=abs(z_now),
                    price=price,
                    strategy=self.name,
                    reason={
                        "rule": "mean_reversion_exit",
                        "rsi": round(rsi_now, 2),
                        "zscore": round(z_now, 2),
                    },
                )
            return None

        if rsi_now <= p["rsi_buy"] and z_now <= p["zscore_buy"]:
            return StrategySignal(
                symbol=symbol,
                side="buy",
                strength=abs(z_now),
                price=price,
                strategy=self.name,
                reason={
                    "rule": "mean_reversion_entry",
                    "rsi": round(rsi_now, 2),
                    "rsi_buy_threshold": p["rsi_buy"],
                    "zscore": round(z_now, 2),
                    "zscore_buy_threshold": p["zscore_buy"],
                },
            )
        return None
