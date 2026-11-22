# Narrative OS v0.6 — persistent fundamental bias and regime transitions

## NEW in v0.6: Hold → challenge → switch (without price-noise whipsaws)

The Interdisciplinary Council now keeps a research-bias state **per focus ticker and
research horizon** in SQLite (`council_bias_states`). It does not reset to flat
because the latest 1-minute candle, a CSV refresh, or a news scan contradicts
its previous view.

1. Open **Interdisciplinary Council** and choose the ticker, horizon and
   unconventional research question. Generate the needed chart-CSV request.
2. Import the requested TradingView CSVs when you want updated cross-market
   context. News scans remain independent of chart refreshes.
3. Click **Re-run interdisciplinary analysis**. The stage-three report now shows
   **Sticky macro research state**, its provenance, challenger evidence, fast
   price context, whether the two disagree, and a dated transition history.
4. State progression: `unestablished` → `provisional` or `established` →
   `retained` / `provisional-held` → `challenged` → `switched`. An old bias can
   become `review-due`, **without** losing its recorded direction.
5. **To switch an evidence-established thesis automatically**, this research
   heuristic requires *new* opposing macro observations with total weighted
   support at least 2.4, spanning at least two distinct event groups and
   including an independently sourced structured release. The same evidence
   cannot be counted twice by rescanning or re-running a CSV. These numerical
   cutoffs are **configurable policy rules, not statistically calibrated
   thresholds or probabilities**. Cross-asset correlations and minute price
   changes can warn of a divergence but cannot trigger a switch by themselves.
6. With adequate cross-asset proxy evidence but insufficient verified macro
   data, the app can open a **provisional cross-market working hypothesis**.
   This is distinctly labelled as price-inferred, not a verified fundamental
   thesis. A material new macro observation can supersede that provisional
   state; a price-only reversal cannot.
7. Optional: **Adopt working hypothesis** lets you explicitly seed a bullish
   or bearish *user-defined, unverified* thesis with a written rationale. The
   origin is retained in the bias history and is never passed off as an AI
   conclusion or established economic fact. Later source evidence can update it.

**Scope limitations**: The existing narrative-impact mapping (higher real
rates/dollar, safe-haven demand, growth/easier policy) currently applies to
**gold**. The app avoids applying these gold-specific assumptions to GBP/JPY or
other asset classes. Unverified web headlines typically remain directionally
neutral, because they do not establish a measured surprise or causal mechanism;
therefore automatic bias establishment can still be unavailable until stronger
inputs arrive. Uploaded price data alone cannot verify a bullion shortage,
insurance disruption, or other physical-market event. AI synthesis (when
connected and authorised) is advisory and cannot silently override the held
macro state. This is an auditable research policy, **not validated predictive
performance or financial advice**.

Run `python -m pytest -q` from the app folder; 54 automated tests verify bias
persistence, challenges, switches, repeated-run idempotency, review ageing,
other-ticker safeguards, historical API state and the existing v0.5 features.
The frontend JS was syntax checked and exercised in Chromium using mocked API
responses (real browser navigation to localhost was blocked in this environment).
Actual TradingView CSV files and ChatGPT sign-in remain unverified end-to-end.

### Upgrade existing Windows installation

Close Narrative OS, extract the v0.6 ZIP, and copy **only your existing
`narrative.db`** from your earlier `narrative-os` folder into the new
`narrative-os` folder before starting it. Do not overwrite the previous folder
without backing up its database. Double-click `start-windows.bat`, then visit
`http://127.0.0.1:8000`. Existing tables migrate automatically; the new
`council_bias_states` table is added on startup.

---

# Previous v0.5 features — interdisciplinary council, adaptive ticker requests + manual CSV research


## NEW in v0.5 — Interdisciplinary Council (manual multi-ticker research)

Narrative OS now supports a **plan → collect → rerun → audit** workflow, with no
live TradingView connection or automated chart scraping:

1. Start the Windows app (`start-windows.bat`) and visit `http://127.0.0.1:8000`.
2. Open **Interdisciplinary Council** in the left sidebar.
3. Describe the question, e.g. *"Can marine insurance disruption cause oil and rates
   to move in a way that overrides gold safe-haven buying?"*; choose a research
   horizon (intraday = **1h**, swing = **4h**, macro = **1D**).
4. Click **Generate request list**. When you have successfully connected and
   authorised ChatGPT, you may opt into **Ask connected AI to select tickers**.
   Otherwise, the application uses a documented deterministic mechanism planner.
   This stage makes **no market-data requests**.
5. For each **required** ticker, open that exact symbol in TradingView, select
   the requested timeframe, load a sufficiently long **overlapping** chart history,
   select **Download chart data**, then upload its CSV in that row using **Import**.
   Context and optional tickers are marked separately. You do not provide your
   TradingView password or session cookies to Narrative OS.
6. Check the **READY**, **MISSING** or **STALE** status of each file. If needed,
   re-export a more recent window. Requirements include >=20 overlapping return
   observations; 100+ is better. Intraday/4-hour bars older than 96 hours are
   marked stale; daily bars older than 15 days are marked stale.
7. Click **Re-run interdisciplinary analysis**. It computes timestamp-aligned
   cross-instrument relationships, descriptive correlations and a one-bar lead/lag
   comparison. If any required CSV is missing, stale or insufficiently overlapping,
   the report stays **incomplete-data** and identifies the blocker.
8. If the required chart basket is complete and ChatGPT has been authorised,
   you can opt into **Ask connected AI to formulate interdisciplinary scenarios**.
   AI interprets the calculations, verified evidence available in the app, and
   missing cross-domain observations. If AI is unavailable or fails, the app
   retains the calculation-only conditional-scenario report.

**What the AI chooses:** A small, bounded selection of related instrument/ticker
and timeframe combinations. Candidate links include shipping insurance → oil →
inflation → yields → gold; collateral/liquidity → market funding; gold refinery/
delivery constraints → futures/ETF price comparisons; industry/labour → growth
expectations; geopolitics → risk hedging; and ETF/reserve demand. AI can propose
an **unverified novel causal link** with an explicit non-chart evidence requirement
and falsifier. It cannot claim to have proven such a link by price co-movement.

**Research discipline:** ETF *price* does not measure ETF *flows*, the nominal
Treasury yield is not the *real* Treasury yield, and futures prices do not
verify deliverable physical bullion quantities. For physical-gold shortage or
surplus claims, you still need external evidence of actual quantities,
obligations, net flows and timing. Short time samples, multi-hypothesis scans,
non-synchronous prices and regime changes can make correlations spurious.
Any bullish/bearish/flat outcome is a **conditional hypothesis, not a calibrated
probability, financial advice or an executable trading signal**. The software
cannot backtest accuracy or prove a predictive edge from a single upload.

**Data and access:** CSVs are stored in the application's local SQLite database;
old snapshots of each ticker/timeframe are limited to three entries. Research
runs and requests are stored in `council_plans` and `council_runs` tables in the
same database. Back up/copy your previous `narrative.db` into the new extracted
folder *before starting* to retain your previous research; the app creates the
new tables automatically. Honor TradingView's applicable export and reuse terms,
particularly for commercial sharing or automated redistribution. A ChatGPT login
and plan-usage permissions may not be available to every account or client; the
AI paths have not been authenticated against a real user account in this build.

**Implementation tests:** `python -m pytest -q` covers the importer, evidence
scoring, dynamic market-data requests, correlated/time-aligned calculations and
stateful HTTP workflow. The new research user interface was also rendered with
mocked API responses in Chromium. External source ingestion and actual ChatGPT
OAuth have not been exercised end-to-end in this environment.

---


Local-first XAU/USD research application. Scans public news searches and official
releases, accepts user-uploaded chart CSVs for dated gold/dollar/other market observations, compares retail
heuristics, institutional-style hypotheses and unconventional causal connections,
automatically scores each evidence item, and supports user-initiated AI research or opt-in AI refinement of new evidence.

## Quick start (Mac)

Requires Python 3.10+; an internet connection is needed for initial dependency installation and web news scans, not for local CSV imports. Extract the ZIP file and open the
`narrative-os` folder, then double-click `start-mac.command` (macOS may ask you to
approve the file under Privacy & Security), **or** open Terminal in that folder:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python run.py
```

Open **http://127.0.0.1:8000**. Leave Terminal running while using the app. To
stop the server, press Ctrl+C. The local SQLite database `narrative.db` is created
automatically and saves research across restarts.

Windows: double-click `start-windows.bat`, or use the corresponding Python venv
commands. Python 3.10+ is required.

## New in v0.3: automatic scoring (no subscription required)

Every newly ingested headline, economic announcement, market snapshot, and
user-entered note immediately receives an **explainable research assessment**:

| Dimension | Scale | Meaning |
|---|---|---|
| Source reliability | 0–5 | Provenance and source traceability. A 2/5 search headline has NOT had its factual claim checked; 5/5 may reflect official data, not causality. |
| Novelty | 0–5 | Whether a similar headline is already in local research, not a quantified information advantage. |
| Market significance | 0–5 | Apparent macro relevance to XAU/USD, not a price forecast. |
| Unconventional relevance | 0–5 | A plausible indirect or multidisciplinary transmission mechanism worth investigation. |
| Narrative impacts | −2 to +2 each | Evidence supporting/challenging rates pressure, safe-haven demand and growth slowdown scenarios. Zero means insufficient directional evidence. |

**Without ChatGPT:** the deterministic rule-based scorer is always available and
clearly labelled **Rule-based**. Unverified search headlines may look important,
but their **directional narrative impacts remain zero**. A directly observed
sufficient daily real-yield change may provisionally alter the rates *context*
by one point. A structured macro release with numeric actual and consensus can
score a provisional scenario, though the free BLS RSS feed does **not** supply
these consensus comparisons. All values are research annotations, **not
statistically calibrated probabilities or an automated trading signal**.

**With ChatGPT:** on **Data sources**, connect an eligible account and explicitly
opt in to automatic background AI. The app selects up to two high-priority
unreviewed source items each scan, requesting revised explanations and rating
reasons. AI cannot mark a headline as verified or assign nonzero directional
impacts to an unverified search-discovered headline. See the **Evidence
intelligence** panel to compare the four score dimensions, impact reasons,
source links and whether ratings are **AI-assisted**, **Rule-based**,
**Simulation**, or a **User override**.

To add original research, press **Add evidence**. Your notes will get the same
four default ratings; check **Manually override directional narrative impacts**
only if you wish to replace the neutral default with your own judgments.

**Upgrading from v0.2 on Windows:** close the old server. Unzip the new release,
then either copy `narrative.db` from your old `narrative-os` folder into the new
one *while both servers are stopped*, or replace the old application files
while keeping a backed-up `narrative.db`. Any existing evidence is given a
score explanation when the new app starts; manual impacts and the fictional
demo's values remain unchanged. Your ChatGPT credentials normally live in your
user profile outside the application folder.

## Use the app

1. **Live sources → Scan web** runs a parallel scan of public news discovery,
   BLS official release headlines, XAU/USD daily closes, DXY/dollar index daily
   closes and US Treasury 10-year daily TIPS real yields. In the **Data sources**
   page see failures, last scans and precise source limitations. The local server
   also scans every **15 minutes** while running (configurable in `.env`).
2. **Ask Narrative AI** lets you type a fresh question; the app then searches
   Google News RSS, gathers saved source-dated market snapshots and submits those
   to the connected model. It returns separate retail / institutional-style /
   unconventional views, competing explanations, contradictions, and unknowns.
3. **Data sources → Continue with ChatGPT** opens the official OpenAI OAuth page
   in your browser. Authenticate *there*, not in Narrative OS. Consent to **plan
   usage** separately. This is the documented **Sign in with ChatGPT** flow for
   eligible **local open-source applications**; you do not need to paste an API
   key. Availability and usage are subject to eligibility, account allowances
   and the OpenAI connection service. OAuth requires an Internet connection and
   **has not been independently end-to-end verified against a real account**.
4. Opt into **Background AI** on the same page *only if you want it*: the app
   will refine scores and interpretations for at most two high-priority
   unreviewed evidence items per scan. All items are already rule-scored. AI usage
   can consume your ChatGPT plan allowance. Disable anytime or disconnect.
5. **Evidence stream** shows each item's four explained evidence ratings, source,
   publication date, narrative impacts and conditional perspectives. **Connection library** displays research pathways,
   including shipping insurance, power consumption and Treasury auctions.
   **Historical replay** shows state changes using the locally recorded events.
6. **Demo replay** is a fully isolated fictional scenario. Nothing in it is
   represented as real economic news. Manual evidence can be added separately.

## Sources and their limitations

| Data | Retrieval | Timing and caution |
|---|---|---|
| Economic release announcements | BLS official RSS (`www.bls.gov/feed/bls_latest.rss`) | Official announcements; does not parse actual vs consensus figures |
| Economic/macro/general news | Search queries via Google News RSS | Search-discovered **headlines**, not verified complete reports or authoritative release tables |
| Gold (XAU/USD) | Stooq public **daily** CSV, if accessible | Delayed end-of-day value, **not live gold prices**; Yahoo GC=F futures *proxy* fallback clearly labelled |
| US dollar movements | Stooq DX.F **futures proxy** daily CSV, if accessible | Not exact spot USD index; unofficial Yahoo DXY index daily chart fallback |
| Real yields | US Treasury official 10-year TIPS daily yield XML | Publication day snapshot, **not intraday** real yields |
| Extra article discovery | Optional GDELT (`ENABLE_GDELT=1`) | Metadata discovery only; articles and claims not independently verified |

All inputs record source URLs, dates and retrieval time when known. Public sites
may block automated requests, rate-limit, change formats or return stale data.
Those failures are visible; no quote is fabricated. The scanner does **not**
pretend a search result supplies a numeric CPI release or a real-time price.
For commercial use, independently review and acquire the necessary usage rights
for each data provider. Do not redistribute scraped data without permission.

## Account connection and security

This app supports **Sign in with ChatGPT** using documented local OAuth / PKCE.
The browser signs in directly at `auth.openai.com`; the app requests separate
consent for `chatgpt.tokens.use.direct`. The local server handles the OAuth
callback and stores credentials with restrictive permissions under the current
user's `~/.config/narrative-os` (override with `NARRATIVE_AUTH_DIR`). Tokens are
never included in `/api/bootstrap` or other browser API responses. Sign-out
removes the local credential. It does not revoke sessions from the OpenAI side.

The app binds to **127.0.0.1**, not the public Internet, and is intended for
**single-user local use only**. Do not expose this local proof-of-concept to
an untrusted network, deploy it as a SaaS, or share a backed-up credential folder.
Direct API keys are an optional **separately billed** alternative via
`OPENAI_API_KEY`, never necessary when an eligible ChatGPT plan connection works.

**Important:** We can test the local OAuth start/state/PKCE logic, local API
behaviour and mocked web/source ingestion without live credentials. The external
ChatGPT sign-in and streaming responses must be verified by the actual user
in their own browser; availability may differ among users/plans.

## Technical details

- Python FastAPI backend, SQLite research log, plain HTML/CSS/JS UI.
- No additional paid economic calendar API by default; no cloud account needed
  to run news/data collection.
- Local server auto-scans every 900 seconds (15 minutes); no scanning happens
  after the local server exits.
- Every imported item receives four rule-based 0–5 evidence ratings. Unverified
  headline-only news is directionally **neutral** unless further verified
  information is provided. Narrative balances are ordinal research annotations,
  not estimated probabilities, calibrated predictive probabilities, trading
  instructions, or observations of real institutional positions.
- Date/replay note: historical replay uses event timestamps from collected
  research; it is **not** a complete, revision-safe point-in-time macro dataset.
  A search result appearing later does not imply a trader could have seen it
  at its published timestamp.
- AI analysis does **not** automatically validate headlines against full articles;
  it only interprets supplied metadata and source-dated snapshots.

## Local API

- `GET /api/bootstrap?mode=live` — sourced evidence, hypothesis state and market
  observations.
- `POST /api/live/refresh` — run current public feed scans, return new items,
  timestamps, provider errors and fallback flags.
- `POST /api/live/search` — `{ "question": "..." }`, custom Google News search
  without a login.
- `POST /api/ai/research` — `{ "question": "..." }`, custom search and AI research
  with a connected ChatGPT plan or optional API key.
- `GET /api/auth/status` — connection and background permission (no tokens).
- `POST /api/auth/start` — generated official OpenAI OAuth authorisation URL.
- `GET /auth/callback` — local OAuth return endpoint.
- `POST /api/auth/disconnect` — erase local credentials and disable background AI.
- `POST /api/ai/automatic` — `{ "enabled": true }` after approved plan consent.
- `POST /api/ai/analyse` — `{ "id": "..." }`, refine both numeric research scores
  and qualitative hypotheses of one source-backed event with explicit AI access.
- `GET /api/market` — latest available source-dated gold, dollar and TIPS observations.

## Run checks

```bash
python -m pip install pytest httpx
DISABLE_POLLING=1 python -m pytest -q
```

Relevant documentation:
- https://developers.openai.com/siwc/token-sharing-open-source/sign-in
- https://developers.openai.com/cookbook/articles/sign-in-with-chatgpt
- https://home.treasury.gov/resource-center/data-chart-center/interest-rates
- https://www.bls.gov/help/hlp_rss.htm

## v0.4 — Manual TradingView chart CSV import (no price-feed integration)

**New: Chart CSV imports** in the left sidebar. In TradingView's chart toolbar,
choose **Download chart data**, select the chart and download its CSV. Check
that chart/timeframe corresponds to your intended dataset. In Narrative OS
select ticker (for example `OANDA:XAUUSD`), timeframe and CSV file, then press
**Import CSV**.

The app validates and persists OHLC candles, optional volume and exported
indicator columns to local `narrative.db`, and shows an in-app closing-price
chart, 1-bar / 20-bar percentage changes, range and the final candle UTC
stamp. Further uploads for the *same ticker + timeframe* replace the latest
snapshot while retaining up to three versions of that series. Duplicate
exact files and older files are rejected; you can import a distinct timeframe
or ticker separately. A new ZIP version keeps any old research if you copy
`narrative.db` into the new folder while the old application is stopped.

**Import does not create a trade signal or mechanically change macro narrative
scores.** It becomes source-dated price context on Overview and a compact
summary is passed to *Ask Narrative AI* when you actively request AI
analysis (and may be included with background evidence analysis only if you
separately authorise background AI); this does not fetch fresh chart data. The latest bar may be an
unclosed, changing candle. Source/market ticker and interval are labels you
choose, not verified against TradingView. Timezone-free dates are interpreted
as UTC; inspect TradingView timezone settings.

`Scan web` only checks BLS release headlines and public news search by default.
There are **no automatic TradingView, broker, gold, dollar or Treasury-yield
price requests** unless you explicitly set `ENABLE_REMOTE_MARKET=1` in your
`.env` file. Financial news still requires internet; offline CSV imports do
not. For 10Y *real* yields use the actual TIPS real-yield series such as
`FRED:DFII10`, not nominal Treasury 10Y yields (`TVC:US10Y`). Spot gold and
gold futures should be imported under their original, distinct ticker codes.

TradingView's CSV export includes data loaded into the chart; scroll to load
more history before downloading. Availability depends on your TradingView
plan. Chart data may be subject to personal-use or redistribution restrictions:
review the TradingView and underlying exchange data agreements before
using the app commercially or sharing imported chart datasets. Never submit
TradingView passwords or cookies to Narrative OS.

**Upload limits:** UTF-8 CSV, up to 8 MB and 20,000 rows per import, with `time`
(or `timestamp`/`date`), `open`, `high`, `low`, `close` and optional `volume`
plus indicator fields. A timestamp may be Unix seconds/milliseconds or an ISO
8601 date/time. The latest CSV snapshot is not a live quote.