"""System events og notifikationer, jf. PRD afsnit 27 og 28."""

import logging

import httpx
from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.models import SystemEvent

log = logging.getLogger("autotrader")


def record_event(
    session: Session,
    kind: str,
    message: str,
    level: str = "info",
    details: dict | None = None,
    notify: bool = False,
) -> None:
    session.add(SystemEvent(kind=kind, message=message, level=level, details=details or {}))
    session.commit()
    log.log(
        logging.CRITICAL if level == "critical" else logging.WARNING if level == "warning" else logging.INFO,
        "%s: %s",
        kind,
        message,
    )
    if notify or level == "critical":
        send_notification(f"[AutoTrader] {kind}: {message}")


def send_notification(text: str) -> bool:
    settings = get_settings()
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        return False
    try:
        httpx.post(
            f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage",
            json={"chat_id": settings.telegram_chat_id, "text": text},
            timeout=10.0,
        )
        return True
    except httpx.HTTPError:
        log.warning("Kunne ikke sende Telegram notifikation")
        return False
