"""Valgfri historisk datakilde via yfinance til backtests.

Gør det muligt at backteste uden broker nøgler. Live handel bruger
altid brokerens data. yfinance er en valgfri afhængighed.
"""

from datetime import date

import pandas as pd


def fetch_daily_bars(symbols: list[str], start: date, end: date) -> dict[str, pd.DataFrame]:
    try:
        import yfinance as yf
    except ImportError as exc:
        raise RuntimeError(
            "yfinance er ikke installeret. Kør: pip install yfinance"
        ) from exc

    result: dict[str, pd.DataFrame] = {}
    data = yf.download(
        symbols, start=start.isoformat(), end=end.isoformat(), group_by="ticker",
        auto_adjust=True, progress=False, threads=True,
    )
    for symbol in symbols:
        try:
            df = data[symbol] if len(symbols) > 1 else data
        except KeyError:
            continue
        df = df.rename(
            columns={"Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume"}
        )[["open", "high", "low", "close", "volume"]].dropna()
        if not df.empty:
            result[symbol] = df
    return result
