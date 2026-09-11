"""Persistent applikationstilstand: mode, kill switch og engine markører.

Kill switch og mode gemmes i databasen, så en genstart aldrig
utilsigtet genaktiverer handel, jf. PRD afsnit 17.
"""

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from backend.models import AppState

MODE_PAPER = "paper"
MODE_LIVE = "live"
MODE_STOPPED = "stopped"


def _get(session: Session, key: str) -> dict:
    row = session.get(AppState, key)
    return dict(row.value) if row else {}


def _set(session: Session, key: str, value: dict) -> None:
    row = session.get(AppState, key)
    if row is None:
        row = AppState(key=key, value=value)
        session.add(row)
    else:
        row.value = value
    session.commit()


def get_mode(session: Session) -> str:
    return _get(session, "mode").get("mode", MODE_PAPER)


def set_mode(session: Session, mode: str) -> None:
    if mode not in (MODE_PAPER, MODE_LIVE, MODE_STOPPED):
        raise ValueError(f"Ukendt mode: {mode}")
    _set(session, "mode", {"mode": mode, "changed_at": _now()})


def kill_switch_active(session: Session) -> bool:
    return bool(_get(session, "kill_switch").get("active", False))


def kill_switch_reason(session: Session) -> str:
    return _get(session, "kill_switch").get("reason", "")


def activate_kill_switch(session: Session, reason: str) -> None:
    _set(session, "kill_switch", {"active": True, "reason": reason, "changed_at": _now()})


def deactivate_kill_switch(session: Session) -> None:
    _set(session, "kill_switch", {"active": False, "reason": "", "changed_at": _now()})


def get_marker(session: Session, key: str) -> str:
    return _get(session, key).get("value", "")


def set_marker(session: Session, key: str, value: str) -> None:
    _set(session, key, {"value": value, "changed_at": _now()})


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
