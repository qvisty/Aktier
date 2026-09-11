"""FastAPI applikation med server renderet dashboard, jf. PRD afsnit 19 og 22."""

import hmac
from pathlib import Path

from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from backend import state
from backend.broker.alpaca import make_broker_from_settings
from backend.broker.base import BrokerError
from backend.config import get_settings
from backend.db import get_session
from backend.events import record_event
from backend.api.dashboard_data import build_overview, paper_gate_status
from backend.trading.orders import cancel_all_open_orders, submit_order

app = FastAPI(title="AutoTrader")
app.add_middleware(SessionMiddleware, secret_key=get_settings().secret_key)

templates = Jinja2Templates(directory=str(Path(__file__).parent / "web" / "templates"))


def is_authenticated(request: Request) -> bool:
    return bool(request.session.get("authenticated"))


def require_auth(request: Request):
    if not is_authenticated(request):
        return RedirectResponse("/login", status_code=302)
    return None


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html", {"error": None})


@app.post("/login")
def login(request: Request, password: str = Form(...)):
    settings = get_settings()
    if hmac.compare_digest(password, settings.dashboard_password):
        request.session["authenticated"] = True
        return RedirectResponse("/", status_code=302)
    return templates.TemplateResponse(
        request, "login.html", {"error": "Forkert adgangskode"}, status_code=401
    )


@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=302)


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    redirect = require_auth(request)
    if redirect:
        return redirect
    settings = get_settings()
    session = get_session()
    try:
        mode = state.get_mode(session)
        try:
            broker = make_broker_from_settings(settings, mode)
        except BrokerError:
            broker = None
        data = build_overview(session, broker)
        return templates.TemplateResponse(request, "dashboard.html", {"d": data})
    finally:
        session.close()


@app.post("/kill-switch")
def kill_switch(request: Request, close_positions: str = Form("")):
    redirect = require_auth(request)
    if redirect:
        return redirect
    settings = get_settings()
    session = get_session()
    try:
        state.activate_kill_switch(session, "manual")
        mode = state.get_mode(session)
        try:
            broker = make_broker_from_settings(settings, mode)
        except BrokerError:
            broker = None
        canceled = 0
        if broker is not None:
            canceled = cancel_all_open_orders(session, broker)
            if close_positions == "yes":
                for p in broker.get_positions():
                    if p.qty > 0:
                        submit_order(
                            session, broker, symbol=p.symbol, side="sell", qty=p.qty,
                            strategy="kill_switch",
                        )
        record_event(
            session,
            "kill_switch",
            f"Kill switch aktiveret manuelt, {canceled} åbne ordrer annulleret",
            level="critical",
            notify=True,
        )
        return RedirectResponse("/", status_code=302)
    finally:
        session.close()


@app.post("/resume")
def resume(request: Request):
    redirect = require_auth(request)
    if redirect:
        return redirect
    session = get_session()
    try:
        state.deactivate_kill_switch(session)
        record_event(session, "kill_switch", "Kill switch deaktiveret manuelt", notify=True)
        return RedirectResponse("/", status_code=302)
    finally:
        session.close()


@app.post("/mode")
def set_mode(request: Request, mode: str = Form(...)):
    redirect = require_auth(request)
    if redirect:
        return redirect
    settings = get_settings()
    session = get_session()
    try:
        if mode == "live":
            if not settings.allow_live_trading:
                record_event(
                    session, "mode_denied",
                    "Live mode afvist, ALLOW_LIVE_TRADING er ikke sat", level="warning",
                )
                return RedirectResponse("/", status_code=302)
            gate = paper_gate_status(session)
            if not gate["passed"]:
                record_event(
                    session, "mode_denied",
                    "Live mode afvist, paper gate er ikke bestået", level="warning",
                )
                return RedirectResponse("/", status_code=302)
        state.set_mode(session, mode)
        record_event(session, "mode_change", f"Mode ændret til {mode}", notify=True)
        return RedirectResponse("/", status_code=302)
    finally:
        session.close()


@app.get("/health")
def health():
    session = get_session()
    try:
        return JSONResponse(
            {
                "status": "ok",
                "mode": state.get_mode(session),
                "kill_switch": state.kill_switch_active(session),
            }
        )
    finally:
        session.close()
