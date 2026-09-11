from backend.strategies.base import Strategy, StrategySignal
from backend.strategies.breakout import BreakoutStrategy
from backend.strategies.mean_reversion import MeanReversionStrategy
from backend.strategies.momentum import MomentumStrategy

ALL_STRATEGIES: dict[str, type[Strategy]] = {
    MomentumStrategy.name: MomentumStrategy,
    MeanReversionStrategy.name: MeanReversionStrategy,
    BreakoutStrategy.name: BreakoutStrategy,
}

__all__ = [
    "Strategy",
    "StrategySignal",
    "MomentumStrategy",
    "MeanReversionStrategy",
    "BreakoutStrategy",
    "ALL_STRATEGIES",
]
