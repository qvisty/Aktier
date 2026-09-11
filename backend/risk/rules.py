"""Hard limits, jf. PRD afsnit 16. Alle checks skal bestå, før en ordre sendes."""

from dataclasses import dataclass, field

from backend.config import Settings


@dataclass
class OrderCandidate:
    symbol: str
    side: str  # buy / sell
    notional: float  # USD værdi af ordren
    signal_price: float
    qty: float | None = None  # sat ved salg


@dataclass
class RiskContext:
    settled_cash: float
    equity: float
    open_position_count: int
    held_qty: dict[str, float] = field(default_factory=dict)
    orders_today: int = 0
    latest_prices: dict[str, float] = field(default_factory=dict)
    bar_age_days: dict[str, int] = field(default_factory=dict)
    kill_switch: bool = False
    mode: str = "paper"


@dataclass
class RiskResult:
    ok: bool
    reasons: list[str] = field(default_factory=list)

    def fail(self, reason: str) -> None:
        self.ok = False
        self.reasons.append(reason)


def check_order(candidate: OrderCandidate, ctx: RiskContext, settings: Settings) -> RiskResult:
    result = RiskResult(ok=True)

    if ctx.kill_switch:
        result.fail("kill_switch_active")
    if ctx.mode == "stopped":
        result.fail("mode_stopped")
    if candidate.side not in ("buy", "sell"):
        result.fail(f"invalid_side:{candidate.side}")
    if candidate.notional <= 0:
        result.fail("non_positive_notional")
    if candidate.notional > settings.max_order_value_usd:
        result.fail(
            f"max_order_value_exceeded:{candidate.notional:.2f}>{settings.max_order_value_usd:.2f}"
        )
    if ctx.orders_today >= settings.max_daily_orders:
        result.fail(f"daily_order_limit_reached:{ctx.orders_today}")

    age = ctx.bar_age_days.get(candidate.symbol)
    if age is None:
        result.fail("no_market_data")
    elif age > settings.max_bar_age_days:
        result.fail(f"stale_data:{age}d")

    latest = ctx.latest_prices.get(candidate.symbol)
    if latest is not None and latest > 0 and candidate.signal_price > 0:
        deviation_pct = abs(latest - candidate.signal_price) / candidate.signal_price * 100.0
        if deviation_pct > settings.price_sanity_max_deviation_pct:
            result.fail(f"price_sanity:{deviation_pct:.1f}pct_deviation")

    if candidate.side == "buy":
        investable = ctx.settled_cash * (1.0 - settings.cash_buffer_pct)
        if candidate.notional > investable:
            result.fail(f"insufficient_settled_cash:{candidate.notional:.2f}>{investable:.2f}")
        if ctx.open_position_count >= settings.max_positions:
            result.fail(f"max_positions_reached:{ctx.open_position_count}")
        if candidate.notional > ctx.equity:
            result.fail("exceeds_total_capital")

    if candidate.side == "sell":
        held = ctx.held_qty.get(candidate.symbol, 0.0)
        if held <= 0:
            result.fail("no_position_to_sell")
        elif candidate.qty is not None and candidate.qty > held * 1.0001:
            result.fail(f"sell_exceeds_position:{candidate.qty}>{held}")

    return result


def edge_is_sufficient(expected_edge_pct: float, settings: Settings) -> bool:
    """Handlen gennemføres kun, hvis forventet edge overstiger omkostninger plus margin."""
    required = settings.roundtrip_cost_pct() + settings.min_edge_margin_pct
    return expected_edge_pct >= required
