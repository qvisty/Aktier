"""Position sizing, jf. PRD afsnit 15. Ligelig fordeling over max_positions."""

from backend.config import Settings


def position_notional(
    settled_cash: float, equity: float, open_position_count: int, settings: Settings
) -> float:
    """USD beløb for næste position. 0 hvis der ikke er plads eller midler."""
    slots_left = settings.max_positions - open_position_count
    if slots_left <= 0:
        return 0.0
    investable_cash = settled_cash * (1.0 - settings.cash_buffer_pct)
    target = equity * (1.0 - settings.cash_buffer_pct) / settings.max_positions
    notional = min(target, investable_cash, settings.max_order_value_usd)
    # Alpaca kræver mindst 1 USD for notional ordrer.
    if notional < 1.0:
        return 0.0
    return round(notional, 2)
