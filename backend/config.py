"""Applikationskonfiguration læst fra environment og .env."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Infrastruktur
    database_url: str = "sqlite:///./autotrader.db"
    secret_key: str = "change-me"
    dashboard_password: str = "change-me"

    # Broker (Alpaca). Paper og live keys holdes adskilt.
    alpaca_paper_key: str = ""
    alpaca_paper_secret: str = ""
    alpaca_live_key: str = ""
    alpaca_live_secret: str = ""
    alpaca_paper_url: str = "https://paper-api.alpaca.markets"
    alpaca_live_url: str = "https://api.alpaca.markets"
    alpaca_data_url: str = "https://data.alpaca.markets"
    # Live handel kræver både denne flag og mode=live i databasen.
    allow_live_trading: bool = False

    # Univers og engine
    universe: str = "AAPL,MSFT,NVDA,AMZN,GOOGL,META,TSLA,AMD,JPM,V,KO,PEP,DIS,NKE,INTC,CSCO,XOM,WMT,PFE,BA"
    engine_interval_seconds: int = 300
    history_days: int = 150
    signal_ttl_minutes: int = 120

    # Position sizing
    cash_buffer_pct: float = 0.05
    max_positions: int = 4

    # Hard limits (risiko)
    max_order_value_usd: float = 100.0
    max_daily_orders: int = 10
    max_bar_age_days: int = 5
    price_sanity_max_deviation_pct: float = 20.0

    # Exits håndhævet af enginen
    stop_loss_pct: float = 0.07
    max_holding_days: int = 15

    # Omkostningsmodel (bruges i backtest og i edge vurdering)
    cost_fixed_per_order_usd: float = 0.0
    cost_spread_pct: float = 0.0005
    cost_slippage_pct: float = 0.0005
    # Minimum forventet edge ud over omkostninger før en handel gennemføres.
    min_edge_margin_pct: float = 0.002

    # Notifikationer (Telegram, valgfrit)
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    def universe_symbols(self) -> list[str]:
        return [s.strip().upper() for s in self.universe.split(",") if s.strip()]

    def roundtrip_cost_pct(self) -> float:
        """Estimeret samlet omkostning i procent for køb plus salg."""
        return 2 * (self.cost_spread_pct + self.cost_slippage_pct)


@lru_cache
def get_settings() -> Settings:
    return Settings()
