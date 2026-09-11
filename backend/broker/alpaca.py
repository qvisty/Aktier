"""Alpaca broker adapter via REST.

Bruger httpx direkte frem for alpaca-py for at holde afhængighederne små
og gøre adapteren let at teste med en mock transport.
"""

from datetime import date, datetime

import httpx

from backend.broker.base import (
    Bar,
    Broker,
    BrokerAccount,
    BrokerError,
    BrokerOrder,
    BrokerPosition,
    MarketClock,
    OrderRequest,
)


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class AlpacaBroker(Broker):
    def __init__(
        self,
        api_key: str,
        api_secret: str,
        trading_url: str,
        data_url: str,
        client: httpx.Client | None = None,
    ):
        self.trading_url = trading_url.rstrip("/")
        self.data_url = data_url.rstrip("/")
        headers = {
            "APCA-API-KEY-ID": api_key,
            "APCA-API-SECRET-KEY": api_secret,
            "Accept": "application/json",
        }
        self.client = client or httpx.Client(headers=headers, timeout=30.0)
        if client is not None:
            self.client.headers.update(headers)

    def _request(self, method: str, url: str, **kwargs) -> httpx.Response:
        try:
            resp = self.client.request(method, url, **kwargs)
        except httpx.HTTPError as exc:
            raise BrokerError(f"Netværksfejl mod broker: {exc}") from exc
        if resp.status_code == 404:
            return resp
        if resp.status_code >= 400:
            raise BrokerError(f"Broker svarede {resp.status_code}: {resp.text[:300]}")
        return resp

    def get_account(self) -> BrokerAccount:
        data = self._request("GET", f"{self.trading_url}/v2/account").json()
        cash = float(data["cash"])
        # Alpaca eksponerer ikke settled cash direkte. For en cash konto er
        # non_marginable_buying_power det nærmeste udtryk for anvendelige midler.
        settled = float(data.get("non_marginable_buying_power") or cash)
        return BrokerAccount(
            cash=cash,
            settled_cash=min(cash, settled),
            equity=float(data["equity"]),
            currency=data.get("currency", "USD"),
        )

    def get_positions(self) -> list[BrokerPosition]:
        data = self._request("GET", f"{self.trading_url}/v2/positions").json()
        return [
            BrokerPosition(
                symbol=p["symbol"],
                qty=float(p["qty"]),
                avg_entry_price=float(p["avg_entry_price"]),
                current_price=float(p.get("current_price") or 0.0),
                market_value=float(p.get("market_value") or 0.0),
            )
            for p in data
        ]

    def get_open_orders(self) -> list[BrokerOrder]:
        data = self._request(
            "GET", f"{self.trading_url}/v2/orders", params={"status": "open", "limit": 500}
        ).json()
        return [self._to_order(o) for o in data]

    def get_order_by_client_id(self, client_order_id: str) -> BrokerOrder | None:
        resp = self._request(
            "GET",
            f"{self.trading_url}/v2/orders:by_client_order_id",
            params={"client_order_id": client_order_id},
        )
        if resp.status_code == 404:
            return None
        return self._to_order(resp.json())

    def submit_order(self, request: OrderRequest) -> BrokerOrder:
        payload: dict = {
            "symbol": request.symbol,
            "side": request.side,
            "type": "market",
            "time_in_force": "day",
            "client_order_id": request.client_order_id,
        }
        if request.notional is not None:
            payload["notional"] = str(round(request.notional, 2))
        else:
            payload["qty"] = str(request.qty)
        data = self._request("POST", f"{self.trading_url}/v2/orders", json=payload).json()
        return self._to_order(data)

    def cancel_order(self, broker_order_id: str) -> None:
        self._request("DELETE", f"{self.trading_url}/v2/orders/{broker_order_id}")

    def get_daily_bars(self, symbols: list[str], start: date, end: date) -> dict[str, list[Bar]]:
        result: dict[str, list[Bar]] = {s: [] for s in symbols}
        params = {
            "symbols": ",".join(symbols),
            "timeframe": "1Day",
            "start": start.isoformat(),
            "end": end.isoformat(),
            "adjustment": "split",
            "feed": "iex",
            "limit": 10000,
        }
        page_token = None
        while True:
            if page_token:
                params["page_token"] = page_token
            data = self._request("GET", f"{self.data_url}/v2/stocks/bars", params=params).json()
            for symbol, bars in (data.get("bars") or {}).items():
                for b in bars:
                    result.setdefault(symbol, []).append(
                        Bar(
                            symbol=symbol,
                            bar_date=_parse_dt(b["t"]).date(),
                            open=float(b["o"]),
                            high=float(b["h"]),
                            low=float(b["l"]),
                            close=float(b["c"]),
                            volume=float(b["v"]),
                        )
                    )
            page_token = data.get("next_page_token")
            if not page_token:
                break
        return result

    def get_latest_prices(self, symbols: list[str]) -> dict[str, float]:
        data = self._request(
            "GET",
            f"{self.data_url}/v2/stocks/trades/latest",
            params={"symbols": ",".join(symbols), "feed": "iex"},
        ).json()
        return {s: float(t["p"]) for s, t in (data.get("trades") or {}).items()}

    def get_clock(self) -> MarketClock:
        data = self._request("GET", f"{self.trading_url}/v2/clock").json()
        return MarketClock(
            is_open=bool(data["is_open"]),
            next_open=_parse_dt(data.get("next_open")),
            next_close=_parse_dt(data.get("next_close")),
        )

    def _to_order(self, o: dict) -> BrokerOrder:
        return BrokerOrder(
            id=o["id"],
            client_order_id=o.get("client_order_id", ""),
            symbol=o["symbol"],
            side=o["side"],
            status=o["status"],
            qty=float(o["qty"]) if o.get("qty") else None,
            notional=float(o["notional"]) if o.get("notional") else None,
            filled_qty=float(o.get("filled_qty") or 0.0),
            filled_avg_price=float(o.get("filled_avg_price") or 0.0),
            submitted_at=_parse_dt(o.get("submitted_at")),
            filled_at=_parse_dt(o.get("filled_at")),
        )


def make_broker_from_settings(settings, mode: str) -> AlpacaBroker | None:
    """Byg broker for det aktuelle mode. Live keys bruges kun i live mode."""
    if mode == "live":
        if not settings.allow_live_trading:
            raise BrokerError("Live mode kræver ALLOW_LIVE_TRADING=true i konfigurationen")
        key, secret, url = settings.alpaca_live_key, settings.alpaca_live_secret, settings.alpaca_live_url
    else:
        key, secret, url = settings.alpaca_paper_key, settings.alpaca_paper_secret, settings.alpaca_paper_url
    if not key or not secret:
        return None
    return AlpacaBroker(key, secret, url, settings.alpaca_data_url)
