# AutoTrader

Selvhostet og automatiseret trading webapp til én privat bruger. Produktkravene er beskrevet i [PRD.md](PRD.md).

Systemet handler et lille univers af amerikanske aktier via Alpaca med tre simple strategifamilier, momentum, mean reversion og breakout. Det kører paper trading, indtil paper gaten er bestået, og live mode aktiveres manuelt.

## Kom i gang

1. Opret en gratis konto hos [Alpaca](https://alpaca.markets) og hent paper API nøgler.
2. Kopiér `.env.example` til `.env` og udfyld nøgler og adgangskoder.
3. Start det hele:

```bash
docker compose up -d --build
```

Dashboardet kører derefter på `http://serverens-ip:8000`. Trading workeren kører i baggrunden og genstarter automatisk efter reboot via Docker restart policies.

## Services

| Service | Rolle |
|---|---|
| backend | FastAPI web dashboard med login |
| trading-worker | 24/7 engine, data, signaler, ordrer, reconciliation |
| postgres | Database |

## Backtest

```bash
# Fra databasen, efter at workeren har hentet data
python -m backend.backtest.run --source db --days 365

# Uden broker nøgler via Yahoo Finance (kræver pip install yfinance)
python -m backend.backtest.run --source yahoo --days 365

# Med out of sample split
python -m backend.backtest.run --source yahoo --days 730 --oos-split 0.3

# Én strategi ad gangen
python -m backend.backtest.run --source yahoo --strategy momentum
```

Backtesteren deler strategikode med live enginen og modellerer spread, slippage, gebyrer og T+1 settlement.

## Sikkerhedsregler

- Kill switch i dashboardet stopper al ny handel og annullerer åbne ordrer. Status gemmes i databasen og overlever genstart.
- Ordrer er idempotente via klientgenererede client order ids med unik constraint.
- Positioner afstemmes mod brokeren ved opstart og løbende. Ved uoverensstemmelse stoppes ny handel automatisk.
- Live mode kræver bestået paper gate, `ALLOW_LIVE_TRADING=true` og manuel aktivering i dashboardet.
- Ingen margin, gearing eller short selling.

## Udvikling

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest
```

Migrationer håndteres med Alembic og køres automatisk ved containerstart. Ny migration efter modelændringer:

```bash
alembic revision --autogenerate -m "beskrivelse"
```

## Adgang udefra

Eksponér ikke dashboardet direkte på internettet. Brug VPN, fx WireGuard eller Tailscale, hvis det skal kunne tilgås uden for hjemmenetværket.
