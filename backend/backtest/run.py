"""Backtest CLI.

Eksempler:
  python -m backend.backtest.run --source yahoo --days 365
  python -m backend.backtest.run --source db --strategy momentum

Med --oos-split holdes den sidste andel af perioden ude som out of
sample, og resultatet rapporteres separat for de to perioder.
"""

import argparse
import json
from datetime import date, timedelta

import pandas as pd

from backend.config import get_settings
from backend.strategies import ALL_STRATEGIES


def load_bars_from_db(symbols: list[str], start: date) -> dict[str, pd.DataFrame]:
    from sqlalchemy import select

    from backend.db import get_session
    from backend.models import MarketData

    session = get_session()
    try:
        result: dict[str, pd.DataFrame] = {}
        for symbol in symbols:
            rows = session.execute(
                select(MarketData)
                .where(MarketData.symbol == symbol, MarketData.bar_date >= start)
                .order_by(MarketData.bar_date)
            ).scalars().all()
            if rows:
                result[symbol] = pd.DataFrame(
                    {
                        "open": [r.open for r in rows],
                        "high": [r.high for r in rows],
                        "low": [r.low for r in rows],
                        "close": [r.close for r in rows],
                        "volume": [r.volume for r in rows],
                    },
                    index=pd.to_datetime([r.bar_date for r in rows]),
                )
        return result
    finally:
        session.close()


def split_bars(bars: dict[str, pd.DataFrame], oos_fraction: float):
    all_dates = sorted({d for df in bars.values() for d in df.index})
    if not all_dates:
        return bars, {}
    split_idx = int(len(all_dates) * (1.0 - oos_fraction))
    split_date = all_dates[split_idx]
    in_sample = {s: df.loc[:split_date] for s, df in bars.items()}
    # Out of sample perioden får historik med, men handler kun efter split.
    return in_sample, {"split_date": split_date, "full": bars}


def main() -> None:
    parser = argparse.ArgumentParser(description="Kør backtest")
    parser.add_argument("--source", choices=["db", "yahoo"], default="db")
    parser.add_argument("--days", type=int, default=365)
    parser.add_argument("--cash", type=float, default=145.0, help="Startkapital i USD")
    parser.add_argument("--strategy", choices=[*ALL_STRATEGIES, "all"], default="all")
    parser.add_argument("--oos-split", type=float, default=0.0, help="Andel af perioden til out of sample, fx 0.3")
    args = parser.parse_args()

    settings = get_settings()
    symbols = settings.universe_symbols()
    start = date.today() - timedelta(days=args.days)

    if args.source == "yahoo":
        from backend.data.yahoo import fetch_daily_bars

        bars = fetch_daily_bars(symbols, start, date.today())
    else:
        bars = load_bars_from_db(symbols, start)

    if not bars:
        raise SystemExit("Ingen markedsdata fundet. Prøv --source yahoo eller kør data ingestion først.")

    strategies = (
        [cls() for cls in ALL_STRATEGIES.values()]
        if args.strategy == "all"
        else [ALL_STRATEGIES[args.strategy]()]
    )

    from backend.backtest.backtester import Backtester

    if args.oos_split > 0:
        all_dates = sorted({d for df in bars.values() for d in df.index})
        split_date = all_dates[int(len(all_dates) * (1.0 - args.oos_split))]
        in_bars = {s: df.loc[: split_date - pd.Timedelta(days=1)] for s, df in bars.items()}
        oos_bars = bars
        print(f"In sample til {split_date.date()}:")
        result = Backtester(settings, strategies, initial_cash=args.cash).run(in_bars)
        print(json.dumps(result.summary(), indent=2))
        print(f"Fuld periode inkl. out of sample efter {split_date.date()}:")
        result_oos = Backtester(settings, strategies, initial_cash=args.cash).run(oos_bars)
        print(json.dumps(result_oos.summary(), indent=2))
    else:
        result = Backtester(settings, strategies, initial_cash=args.cash).run(bars)
        print(json.dumps(result.summary(), indent=2))
        for trade in result.trades[-20:]:
            exit_price = f"{trade.exit_price:.2f}" if trade.exit_price else "open"
            print(
                f"{trade.entry_date.date()} {trade.symbol:6s} {trade.strategy:14s} "
                f"entry {trade.entry_price:.2f} exit {exit_price} "
                f"net {trade.net_pnl if trade.net_pnl is None else round(trade.net_pnl, 2)}"
            )


if __name__ == "__main__":
    main()
