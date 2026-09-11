# Product Requirements Document

## AutoTrader MVP, selvhostet og automatiseret aktiehandel

Status: MVP specifikation, revision 2
Platform: Selvhostet Linux server, Docker
Primær bruger: Én privat bruger
Startkapital: Cirka 1.000 DKK
Primært mål: Maksimere forventet nettoafkast på kort horisont gennem automatiseret handel
Risikoprofil: Høj risikovillighed, men ingen gearing og ingen mulighed for negativ saldo i MVP

---

## 1. Produktvision

AutoTrader er en lille, selvhostet webapplikation, der automatisk analyserer finansielle instrumenter, identificerer kortsigtede handelsmuligheder og køber og sælger via en broker API uden brugerens løbende involvering.

Systemet kører kontinuerligt på en Linux hjemmeserver.

Målet er ikke at garantere profit, det er ikke muligt. Målet er at bygge et system, der systematisk forsøger at finde positiv forventet værdi efter spreads, kurtage og øvrige handelsomkostninger.

MVP prioriterer:

1. Enkelhed
2. Automatisering
3. Realistisk test
4. Lave handelsomkostninger
5. Hurtig feedback
6. Kontrolleret overgang fra paper til live
7. Mulighed for senere udvidelse

---

## 2. Problem

Brugeren ønsker at forsøge at skabe afkast på en mindre kapital, men ønsker ikke selv løbende at:

- overvåge markeder
- screene aktier
- analysere signaler
- beslutte køb og salg
- placere ordrer
- overvåge åbne positioner
- føre statistik over strategier

Systemet automatiserer denne proces så langt som praktisk muligt.

---

## 3. Succeskriterier

Det vigtigste økonomiske KPI er nettoafkast efter alle handelsomkostninger.

Sekundære KPI'er:

- antal handler
- win rate
- gennemsnitlig gevinst og gennemsnitligt tab
- profit factor
- expectancy pr. handel
- maksimal drawdown
- Sharpe og Sortino som diagnostiske mål
- omsætning
- spread og slippage
- kurtage og gebyrer
- performance pr. strategi
- performance relativt til en simpel benchmark, fx buy and hold af et bredt indeks

Systemet må ikke optimere efter win rate alene. En strategi med fx 40 procent vindende handler kan være bedre end en strategi med 70 procent, hvis forholdet mellem gevinst og tab giver højere forventet nettoafkast.

---

## 4. Kapital

MVP designes omkring cirka 1.000 DKK i startkapital.

Det giver en særlig begrænsning. Handelsomkostninger, spreads og valutaveksling kan være meget betydelige relativt til porteføljen. Derfor skal systemet prioritere instrumenter og brokerfunktionalitet, der understøtter små positioner og helst fractional shares.

Strategien må ikke generere handler alene for at være aktiv. Hvis forventet edge ikke vurderes til at overstige de forventede omkostninger, skal systemet gøre ingenting. Cash er en gyldig position.

Omkostningsmodellen skal være eksplicit i koden. Før hver handel beregnes et estimat for samlede omkostninger, spread, kurtage, veksling og forventet slippage, og handlen gennemføres kun, hvis det forventede signal overstiger dette estimat med en konfigurerbar margin.

---

## 5. Marked og instrumentunivers

MVP er ikke bundet til danske aktier.

Instrumentunivers vælges ud fra:

- brokerens API
- lave handelsomkostninger
- likviditet
- spread
- understøttelse af fractional shares
- adgang til markedsdata
- ordreudførelse
- mulighed for paper trading

Amerikanske aktier er det mest realistiske univers for MVP, fordi det er der, fractional shares, kommissionsfri handel og gode paper trading API'er findes.

Systemet skal ikke antage, at flere markeder automatisk er bedre. V1 har ét relativt begrænset handelsunivers, fx 20 til 50 likvide, velkendte instrumenter, defineret i konfiguration.

---

## 6. Regulatoriske og praktiske rammer

Dette afsnit er nyt i forhold til revision 1 og dækker forhold, der reelt begrænser designet.

### Pattern Day Trader reglen

Amerikanske marginkonti under 25.000 USD må maksimalt lave 3 day trades pr. 5 handelsdage. MVP bruger derfor en cash konto. En cash konto er ikke omfattet af PDT reglen, men har settlement på T+1, så provenu fra et salg kan først genbruges dagen efter. Trading enginen skal modellere settled og unsettled cash separat, og strategierne skal designes med denne begrænsning for øje. Det peger naturligt mod swing trading med holdetid på en eller flere dage frem for intradag handel.

### Valuta

Kapitalen er i DKK, men universet handles sandsynligvis i USD. Systemet skal registrere vekselomkostninger som en handelsomkostning og rapportere P/L i DKK. Valutakursudsving mellem DKK og USD accepteres som en del af risikoen i MVP og afdækkes ikke.

### Skat

Gevinster er skattepligtige som aktieindkomst i Danmark, og en udenlandsk broker indberetter ikke automatisk til Skattestyrelsen. Systemet skal derfor kunne eksportere en komplet handelshistorik med tidspunkter, priser, gebyrer og valutakurser, så årsopgørelsen kan laves manuelt eller med et eksternt værktøj. Bemærk at visse ETF'er lagerbeskattes, hvilket taler for at holde universet til enkeltaktier i MVP.

### Markedstider

Det amerikanske marked er åbent 15.30 til 22.00 dansk normaltid. Al scheduling internt i systemet foregår i UTC, og markedets tidszone og helligdagskalender hentes fra brokerens API frem for at blive hardcodet.

---

## 7. Broker

MVP understøtter én broker.

### Krav

Must have:

- dokumenteret API
- programmatisk ordreafgivelse
- paper trading eller realistisk simulationsmulighed
- positions og balance API
- ordrehistorik
- stabil autentifikation
- små positioner
- tilgængelig for privatpersoner bosat i Danmark

Strongly preferred:

- fractional shares
- lave eller ingen minimumsgebyrer
- streaming eller realtidskurser
- gode Python biblioteker
- samme API model for både paper og live konto

### Anbefaling

Primær kandidat er Alpaca. Den opfylder alle krav, kommissionsfri handel i amerikanske aktier, fractional shares, et førsteklasses paper trading miljø, samme REST og websocket API for paper og live, et officielt Python SDK og gratis markedsdata i et omfang, der rækker til MVP. Tilgængelighed for danske kunder skal verificeres som første skridt i milestone 5.

Fallback er Interactive Brokers, som med sikkerhed er tilgængelig i Danmark og understøtter fractional shares, men har et markant mere komplekst API og et mindre rent paper setup.

Broker adapteren abstraheres bag et internt interface, så en anden broker senere kan implementeres uden at omskrive strategierne. Interfacet dækker mindst: hent konto, hent positioner, hent ordrer, placer ordre, annuller ordre, hent markedsdata, hent markedskalender.

---

## 8. Handelsfilosofi

MVP forsøger ikke at forudsige aktiemarkedet med en stor AI model.

Den anvender simple, testbare og reproducerbare kvantitative regler. Kompleksitet accepteres kun, hvis den kan demonstrere bedre resultater out of sample.

V1 starter derfor med flere simple strategifamilier.

---

## 9. Strategier

MVP implementerer tre strategifamilier.

### A. Momentum

Finder likvide instrumenter med stærk relativ kortsigtet prisudvikling.

Mulige signaler:

- rate of change
- relative strength
- volume confirmation
- relation mellem glidende gennemsnit
- breakout

### B. Mean Reversion

Finder kortsigtede ekstreme bevægelser, hvor historiske data indikerer sandsynlighed for normalisering.

Mulige signaler:

- RSI
- afstand fra glidende gennemsnit
- Bollinger eller z score lignende afvigelser
- kortsigtede overextensions

### C. Breakout og trend

Forsøger at udnytte fortsættelse efter brud på relevante prisniveauer.

Mulige signaler:

- rolling high
- volatilitet
- volumen
- trendfilter

Alle konkrete regler og parametre skal være konfigurerbare, og hver strategi implementerer samme interface: givet markedsdata og nuværende positioner, returner en liste af signaler med retning, styrke og begrundelse.

Strategierne arbejder på daglige eller timebaserede bars, ikke tick data, jf. cash kontoens settlement begrænsning.

---

## 10. Strategy Competition

Strategier evalueres separat.

Systemet registrerer for hver strategi:

- signaler
- handler
- bruttoresultat
- omkostninger
- nettoresultat
- drawdown
- expectancy
- profit factor

MVP må gerne deaktivere en strategi, der ikke længere opfylder definerede performancekrav. Der skal dog være minimumskrav til datamængden, fx mindst 30 handler, så systemet ikke skifter strategi på baggrund af få tilfældige handler. Deaktivering logges som system event og vises i dashboardet.

---

## 11. Backtesting

Ingen strategi må gå direkte fra idé til live trading.

Pipeline:

Strategy → Backtest → Out of sample test → Paper trading → Live

Backtesting skal inkludere realistiske antagelser om:

- spread
- broker fees
- slippage
- valutaveksling
- markedsåbning og lukning
- utilgængelige priser
- ordreudførelse
- settlement, dvs. at solgt provenu først er tilgængeligt næste handelsdag

Backtests skal så vidt muligt undgå:

- look ahead bias
- survivorship bias
- data leakage
- parameter overfitting

Historiske resultater må aldrig præsenteres som garanti for fremtidigt afkast.

Backtesteren genbruger samme strategikode som live enginen. Der må ikke findes to implementeringer af samme strategi.

---

## 12. Walk forward validering

Data opdeles tidsmæssigt.

Eksempel:

Training → Validation → Test

Parametre må optimeres på tidligere data, men den endelige evaluering skal foretages på data, som optimeringen ikke har set.

Senere versioner kan implementere egentlig rullende walk forward optimering.

---

## 13. Paper Trading

Paper trading er obligatorisk før live trading.

MVP gate:

- mindst 10 handelsdage
- mindst 30 eksekverbare signaler eller handler, så strategien beviseligt producerer nok aktivitet
- ingen kritiske systemfejl
- ingen dublerede ordrer
- korrekt positionsafstemning
- realistisk registrering af omkostninger
- alle risikoregler fungerer

Profit i paper trading er ikke alene et krav for teknisk godkendelse, fordi den korte testperiode statistisk kan være misvisende. Der er en særskilt teknisk readiness vurdering og en strategy performance vurdering, og begge vises som checklister i dashboardet.

Live trading aktiveres manuelt første gang.

---

## 14. Live Trading

Når live mode er aktiveret, kører systemet automatisk.

Flow:

Market data
↓
Universe filter
↓
Strategy signals
↓
Signal ranking
↓
Risk checks
↓
Position sizing
↓
Order manager
↓
Broker API
↓
Execution verification
↓
Database

Brugeren behøver ikke godkende individuelle handler.

---

## 15. Position sizing

Kapitalen er lille, så position sizing er enkel.

Systemet må aldrig placere en ordre, der overstiger tilgængelig settled cash.

MVP understøtter ikke:

- margin
- gearing
- short selling
- optionshandel
- lån

Positioner dimensioneres efter tilgængelig kapital og strategi, fx ligelig fordeling over maksimalt antal samtidige positioner. Der reserveres en lille cash buffer, fx 5 procent, til gebyrer og afrunding.

---

## 16. Risikostyring

Høj risikovillighed betyder ikke fravær af tekniske sikkerhedsregler. MVP skal beskytte mod katastrofale softwarefejl.

Hard limits, alle konfigurerbare, men med sikre defaults:

- ingen gearing
- ingen negativ cash
- maksimalt 100 procent af den dedikerede kapital må eksponeres
- maksimal ordrestørrelse
- maksimalt antal samtidige positioner
- duplicate order protection via klientgenererede idempotensnøgler, se afsnit 24
- stale data protection, ingen ordrer på data ældre end en konfigurerbar grænse
- API sanity checks, fx afvis en pris der afviger mere end x procent fra seneste kendte pris
- daily order limit
- global kill switch

Derudover kan hver strategi definere exits, eksempelvis stop loss, trailing stop, tidsbaseret exit eller signalskifte. Exits håndhæves af enginen, ikke af broker ordretyper alene, så de også virker i paper mode.

Alle risikoregler skal have unit tests. Det er den del af systemet, hvor fejl er dyrest.

---

## 17. Kill Switch

Dashboardet har en tydelig knap: STOP TRADING.

Funktionen skal:

1. deaktivere nye handler øjeblikkeligt
2. annullere åbne ikke eksekverede ordrer
3. lade brugeren vælge, om eksisterende positioner beholdes eller lukkes

Kill switch status gemmes persistent i databasen. En servergenstart må aldrig utilsigtet genaktivere handel. Genaktivering kræver eksplicit brugerhandling i dashboardet.

---

## 18. Trading Engine

Trading enginen kører som en separat backend service og er ikke afhængig af, at browseren er åben.

Den skal:

- hente markedsdata
- beregne indikatorer
- evaluere strategier
- generere signaler
- kontrollere risiko
- sende ordrer
- kontrollere execution
- opdatere positioner
- logge beslutninger
- håndtere fejl

Enginen kører som en scheduler loop, fx et hovedcyklus pr. bar interval, plus hændelsesdrevne opgaver som ordreopfølgning og reconciliation.

---

## 19. Dashboard

Webinterfacet holdes minimalistisk.

### Overview

- Portfolio Value
- Today's P/L
- Total P/L
- Cash, opdelt i settled og unsettled
- Market Exposure
- Mode: PAPER, LIVE eller STOPPED

### Open Positions

Symbol, Position, Entry, Current, P/L, Strategy

### Recent Trades

Seneste handler med tidspunkt, instrument, køb eller salg, pris, størrelse, strategi og resultat.

### Strategy Performance

Performance for hver aktiv strategi.

### System Health

Se afsnit 27.

---

## 20. Trade Explainability

Enhver handel skal kunne forklares bagefter.

Eksempel:

BUY XYZ

Strategy: Momentum
Signal time: 14:35 UTC
Price: 42.12
Position: 180 DKK

Reason:

- 20 period breakout
- positive relative momentum
- volume threshold satisfied
- estimated transaction cost acceptable
- risk checks passed

Begrundelsen gemmes struktureret sammen med signalet, så den kan vises i dashboardet og bruges til debugging og til at afgøre, om strategien fungerer som tiltænkt.

---

## 21. Database

MVP anvender PostgreSQL.

Centrale tabeller:

- market_data, historiske markedsdata
- signals, alle genererede signaler, også dem der ikke bliver handlet, inkl. struktureret begrundelse
- orders, alle ordreforespørgsler med klientgenereret idempotensnøgle, unik constraint
- executions, broker bekræftede executions
- positions, aktuelle og historiske positioner
- strategies, strategikonfiguration
- strategy_metrics, performance data
- system_events, fejl, genstarter, API problemer, kill switch ændringer mv.
- app_state, persistent systemtilstand som mode og kill switch

Migrationsværktøj, fx Alembic, anvendes fra dag ét.

---

## 22. Teknologistack

### Backend

Python og FastAPI. Python vælges pga. det stærke økosystem omkring finansielle data, statistik og backtesting.

### Trading og data

- pandas
- NumPy
- broker SDK, ved Alpaca er det alpaca-py
- egen enkel backtester frem for et stort framework, fordi backtesteren skal dele strategikode med live enginen, jf. afsnit 11

Biblioteksvalg holdes minimalt.

### Frontend

Server renderet UI med FastAPI, Jinja2 og HTMX som udgangspunkt, fordi det reducerer udviklingstid og kompleksitet markant for et single user dashboard. React tages kun i brug, hvis dashboardet senere vokser ud over det. MVP prioriterer funktion over frontend kompleksitet.

### Database

PostgreSQL.

### Deployment

Docker Compose.

---

## 23. Projektstruktur og Docker

Forslag:

```
autotrader/
├── backend/
│   ├── api/
│   ├── broker/
│   ├── strategies/
│   ├── trading/
│   ├── risk/
│   ├── backtest/
│   ├── data/
│   └── web/          # templates og statiske filer ved server renderet UI
├── migrations/
├── tests/
├── docker-compose.yml
├── .env.example
└── README.md
```

Services:

- backend, API og UI
- trading-worker
- postgres

Scheduler ligger i trading-worker i MVP frem for at introducere ekstra infrastruktur. `.env` holdes ude af git, kun `.env.example` committes.

---

## 24. Serverdrift og idempotens

Systemet skal:

- starte automatisk efter reboot
- genstarte efter crash
- gemme state persistent
- tåle midlertidigt internetudfald
- genetablere broker forbindelsen
- kontrollere faktisk broker state efter genstart

Docker Compose anvender restart policies.

En genstart må ikke føre til, at gamle signaler automatisk sendes som nye ordrer. Det sikres konkret ved:

1. Hver ordre får en klientgenereret idempotensnøgle, der sendes til brokeren som client order id og gemmes med unik constraint i databasen.
2. Efter genstart afstemmes åbne ordrer mod brokeren, før enginen genoptager normal drift.
3. Signaler har en kort gyldighedsperiode og eksekveres aldrig efter udløb.

---

## 25. Reconciliation

Brokerens data er source of truth for faktiske penge og positioner.

Trading enginen sammenligner regelmæssigt, mindst ved opstart og fx hver time i markedstid:

Local state ↔ Broker state

Ved alvorlig uoverensstemmelse:

STOP NEW TRADING

Systemet logger problemet, sender notifikation og kræver manuel intervention. Dette reducerer risikoen for fx dobbelte positioner efter crash.

---

## 26. Sikkerhed

- Broker credentials gemmes aldrig i source code eller frontend.
- Secrets gemmes via environment variabler eller Docker secrets.
- API keys logges aldrig.
- Webappen beskyttes som minimum med authentication.
- Live og paper credentials holdes fysisk adskilt i konfigurationen, og live keys kan kun aktiveres eksplicit.

Hvis dashboardet skal kunne tilgås uden for hjemmenetværket, sker det gennem VPN, fx WireGuard eller Tailscale, frem for at eksponere trading dashboardet direkte på internettet.

---

## 27. Monitoring

Systemet logger:

- process health
- market data status
- broker connectivity
- strategy execution
- orders
- broker responses
- exceptions
- reconciliation
- P/L

Dashboardet viser SYSTEM HEALTH med fx:

- Trading Engine: OK
- Broker: Connected
- Market Data: Current
- Database: OK
- Last Strategy Run: timestamp

---

## 28. Notifikationer

MVP sender notifikation ved kritiske hændelser, fx via en simpel kanal som Telegram bot, Pushover eller e-mail:

- live trading startet eller stoppet
- ordre afvist
- broker disconnected
- reconciliation mismatch
- trading engine crash
- kill switch aktiveret

Normal handel kræver ikke brugerinteraktion og notificerer ikke.

---

## 29. Hvad MVP bevidst IKKE indeholder

For at forhindre scope explosion udelades:

- LLM baseret aktieudvælgelse
- autonom AI agent
- automatisk genereret produktionskode
- reinforcement learning
- optionsstrategier
- gearing
- short selling
- high frequency trading
- sociale sentiment modeller
- automatisk nyhedshandel
- flere brokers
- mobilapp
- multi user
- avancerede porteføljemodeller
- valutaafdækning

De funktioner kan vurderes senere.

---

## 30. Fase 2, Strategy Lab

Når MVP har fungeret stabilt, kan en separat Strategy Lab udvikles.

Den kan automatisk:

1. generere strategikandidater
2. variere parametre
3. backteste
4. foretage walk forward validering
5. sammenligne kandidater
6. paper trade kandidater
7. rangere dem

En ny strategi må aldrig få direkte adgang til live kapital alene fordi den har en imponerende backtest.

Promotion pipeline:

Candidate → Validated → Paper → Eligible → Live

---

## 31. Fase 3, Adaptive Allocation

Systemet kan senere justere kapitalfordelingen mellem godkendte strategier.

Eksempel:

Momentum 50 procent, Mean Reversion 20 procent, Breakout 30 procent.

Fordelingen kan ændres efter dokumenteret out of sample eller live performance og markedsregime. Dette implementeres først, når datamængden er stor nok til at gøre vurderingen meningsfuld.

---

## 32. MVP Acceptance Criteria

Produktet betragtes som teknisk MVP færdigt, når:

- det kan installeres med Docker Compose på Linux
- systemet starter automatisk
- broker kan forbindes
- markedsdata kan indlæses
- mindst tre strategier kan køres
- strategier kan backtestes
- omkostninger inkl. valutaveksling indgår i backtests
- paper trading fungerer automatisk
- ordrer og executions registreres korrekt
- ordrer er idempotente, API fejl skaber ikke dublerede handler
- positioner kan reconciles mod broker
- dashboard viser kapital, P/L, positioner og handler
- hver handel kan spores til et signal med struktureret begrundelse
- kill switch fungerer og overlever genstart
- systemet kan genstarte sikkert
- paper og live mode er tydeligt adskilt
- live trading kan først aktiveres efter bestået paper gate
- handelshistorik kan eksporteres til skattebrug

---

## 33. Foreslået udviklingsrækkefølge

### Milestone 1, Foundation
Docker, FastAPI, PostgreSQL, migrationer, konfiguration og simpel web UI med login.

### Milestone 2, Data
Verificér brokeradgang fra Danmark. Market data ingestion og historisk database.

### Milestone 3, Strategy Engine
Implementér de tre simple strategifamilier bag et fælles interface.

### Milestone 4, Backtester
Realistiske backtests inklusive omkostninger, settlement og out of sample validering.

### Milestone 5, Broker
Broker adapter og paper trading.

### Milestone 6, Automation
24/7 worker, scheduler, execution management, idempotente ordrer og reconciliation.

### Milestone 7, Dashboard
Portfolio, trades, strategies, logs og system health.

### Milestone 8, Safety
Kill switch, duplicate protection, stale data protection, restart recovery og notifikationer.

### Milestone 9, Paper Validation
Kør systemet kontinuerligt i mindst 10 handelsdage og ret execution og driftsfejl.

### Milestone 10, Small Live Deployment
Aktivér live mode med den dedikerede kapital.

---

## 34. Den vigtigste designregel

Systemet skal være simpelt nok til, at vi kan afgøre, hvorfor det tjener eller taber penge.

Med cirka 1.000 DKK er første mål ikke at bygge verdens mest avancerede trading AI. Første mål er at bevise hele kæden:

Data → Signal → Decision → Order → Execution → Result

Hvis denne pipeline fungerer stabilt, og mindst én strategi efter realistiske omkostninger viser lovende resultater out of sample, i paper og i live, har MVP skabt fundamentet for en langt mere avanceret version.

---

## 35. Endelig produktdefinition

AutoTrader MVP er en single user, selvhostet og fuldautomatisk trading webapp til en Linux server.

Den anvender et lille antal systematiske kortsigtede strategier, tester dem på historiske data og paper data og kan efter godkendelse automatisk handle en mindre live kapital gennem en broker API.

Produktet optimeres mod nettoafkast efter omkostninger, mens hårde tekniske sikkerhedsregler forhindrer gearing, negativ saldo, dublerede ordrer og ukontrolleret handel.

Arkitekturen holdes bevidst simpel, men modulær nok til senere at understøtte automatisk strategiudvikling og adaptiv kapitalallokering.

---

## 36. Åbne beslutninger

Disse afklares tidligt i implementeringen:

1. Er Alpaca tilgængelig for privatpersoner bosat i Danmark. Hvis ikke, falder valget på Interactive Brokers, og milestone 5 vokser tilsvarende.
2. Bar interval for strategierne, dagligt eller timebaseret. Anbefaling er dagligt i V1, det passer bedst til cash kontoens settlement og minimerer datakrav.
3. Notifikationskanal, Telegram, Pushover eller e-mail.
4. Om paper trading skal bruge brokerens paper miljø alene eller suppleres af egen simulering med mere konservative fills. Anbefaling er brokerens paper miljø i MVP.
