# Opsætning trin for trin

Guiden fører dig fra nul til kørende paper trading og senere live.

## Trin 1. Merge pull requesten

Gå til https://github.com/qvisty/Aktier/pull/1, klik "Ready for review" og derefter "Merge pull request", så koden lander på main.

## Trin 2. Forbered serveren

Du skal bruge en Linux server med Docker og Docker Compose.

```bash
# Installér Docker (Debian/Ubuntu), officiel vejledning:
# https://docs.docker.com/engine/install/
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
# Log ud og ind igen, så gruppen slår igennem.
docker --version && docker compose version
```

## Trin 3. Opret Alpaca konto og hent paper nøgler

1. Gå til https://app.alpaca.markets/signup og opret en konto. Vælg Trading API kontotypen. Alpaca tager kunder fra mange lande uden for USA, men bekræft under oprettelsen, at Danmark er understøttet. Er det ikke tilfældet, så sig til, så bygger jeg en Interactive Brokers adapter i stedet.
2. Log ind på https://app.alpaca.markets og skift til Paper Trading i menuen øverst til venstre (ikonet med to pile).
3. På paper oversigten, https://app.alpaca.markets/paper/dashboard/overview, finder du boksen "API Keys" i højre side. Klik "Generate New Keys" og gem både key og secret med det samme, secret vises kun én gang.

Dokumentation: https://docs.alpaca.markets/docs/getting-started

## Trin 4. Hent koden og konfigurér

```bash
git clone https://github.com/qvisty/Aktier.git
cd Aktier
cp .env.example .env
nano .env
```

Udfyld i `.env`:

```
SECRET_KEY=<kør: openssl rand -hex 32>
DASHBOARD_PASSWORD=<vælg en stærk adgangskode>
POSTGRES_PASSWORD=<kør: openssl rand -hex 16>
ALPACA_PAPER_KEY=<fra trin 3>
ALPACA_PAPER_SECRET=<fra trin 3>
```

Lad live felterne stå tomme og `ALLOW_LIVE_TRADING=false` indtil videre.

## Trin 5. Start systemet

```bash
docker compose up -d --build
docker compose ps
docker compose logs -f trading-worker
```

Alle tre services skal stå som running, og workerens log skal vise "Worker startet i mode=paper".

## Trin 6. Åbn dashboardet

Gå til `http://<serverens-ip>:8000` i browseren og log ind med din DASHBOARD_PASSWORD. Tjek at System Health viser Broker Connected. Mode skal stå til PAPER.

Det amerikanske marked er åbent 15.30 til 22.00 dansk tid på hverdage, https://www.nyse.com/markets/hours-calendars. Uden for åbningstid sker der ingenting, det er forventet.

## Trin 7. Kør en backtest (valgfrit men anbefalet)

Efter et par dages drift har workeren hentet historik i databasen:

```bash
docker compose exec backend python -m backend.backtest.run --source db --days 365 --oos-split 0.3
```

Uden for Docker kan Yahoo bruges som kilde uden broker nøgler:

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m backend.backtest.run --source yahoo --days 730 --oos-split 0.3
```

## Trin 8. Telegram notifikationer (valgfrit)

1. Skriv til https://t.me/BotFather i Telegram, send `/newbot` og følg anvisningerne. Du får et bot token.
2. Skriv en besked til din nye bot, åbn derefter `https://api.telegram.org/bot<DIT_TOKEN>/getUpdates` i browseren og aflæs `chat.id`.
3. Sæt `TELEGRAM_BOT_TOKEN` og `TELEGRAM_CHAT_ID` i `.env` og kør `docker compose up -d`.

## Trin 9. Sikker adgang udefra (valgfrit)

Eksponér ikke port 8000 direkte på internettet. Installér Tailscale på server og telefon, https://tailscale.com/download, så kan du tilgå dashboardet sikkert via serverens Tailscale ip.

## Trin 10. Paper perioden

Lad systemet køre i mindst 10 handelsdage. Dashboardets "Paper gate" viser status på kravene: mindst 10 handelsdage, mindst 30 handler og ingen kritiske fejl. Hold øje med at handler har fornuftige begrundelser under "Seneste signaler", og at reconciliation står til ok.

## Trin 11. Gå live

Først når paper gaten er bestået og mindst én strategi ser fornuftig ud:

1. Indbetal den dedikerede kapital, cirka 1.000 DKK, cirka 145 USD, til Alpaca live kontoen. Bemærk vekselgebyr ved overførsel fra DKK.
2. Generér live API nøgler på https://app.alpaca.markets under Live Trading.
3. Sæt `ALPACA_LIVE_KEY`, `ALPACA_LIVE_SECRET` og `ALLOW_LIVE_TRADING=true` i `.env` og kør `docker compose up -d`.
4. Klik "Skift til LIVE" i dashboardet og bekræft.

STOP TRADING knappen stopper al ny handel øjeblikkeligt, og tilstanden overlever genstart.

## Skat

Systemet gemmer alle handler i databasen. Gevinster skal selvangives som aktieindkomst, en udenlandsk broker indberetter ikke automatisk. Se https://skat.dk under aktier og værdipapirer. Eksport til årsopgørelsen laves fra handelshistorikken.
