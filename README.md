# Narrative OS v0.6.1 — Private iPhone Cloud Edition

This is the real v0.6 Python/FastAPI research app, adapted for a **single private owner**. It adds password authentication, a persistent database, HTTPS deployment configuration, iPhone-friendly navigation and a one-time import of your previous research. No stock broker or TradingView login is needed; TradingView chart data remains manually uploaded as CSV.

## Quick deployment: Render + private GitHub repo

You will need a GitHub account and Render account. A paid Render instance and persistent disk are required for the SQLite file to survive redeployments. Review current pricing at <https://render.com/pricing>. The `render.yaml` selects the Starter instance in **Frankfurt** (near London) and a 1 GB disk. The Render URL is publicly *addressable*, but **every dashboard, static file and API endpoint requires your password** (except the health check and sign-in screen).

1. Extract this ZIP on Windows or Mac. Inside you'll see `app.py`, `render.yaml`, `static/`, `requirements.txt` and other files.
2. Create a **private** GitHub repository named `narrative-os-private` at <https://github.com/new>. Do not commit `.env`, API keys, OAuth tokens or `.db` files. `.gitignore` excludes them.
3. Publish the **contents of the extracted folder** to that repository's **root**, so `render.yaml` appears at the root. The easiest approach on Windows is GitHub Desktop: **File → Add local repository → Create a repository here → Publish repository**, ensuring *Keep this code private* is selected. Or use Git CLI if preferred.
4. Open <https://dashboard.render.com/>. Choose **New → Blueprint**, connect your GitHub account, and select that private repository. Render detects `render.yaml`.
5. Confirm the paid **Starter** instance and attached **1 GB persistent disk**. When Render requests environment variable values, set `APP_PASSWORD` to a **unique 16+ character password**. `APP_SESSION_SECRET` is randomised by Render's `generateValue` setting. DO NOT enter your ChatGPT password or any TradingView credentials.
6. Deploy. After it succeeds, open your Render URL, normally `https://narrative-os-private-<suffix>.onrender.com`. You should see the **private sign-in** screen. Enter your `APP_PASSWORD`.
7. On iPhone, open the same HTTPS link in Safari. Tap **Share → Add to Home Screen** to keep Narrative OS on your Home Screen. CSV uploads work through Safari's Files picker; for chart exports, you may still find it easier to export from TradingView on a computer and move the CSV to iCloud Drive.
8. In **Data sources**, you may upload your old `narrative.db` (from v0.6) to restore research. Importing merges known research tables; it does **not** import ChatGPT OAuth tokens or turn on automatic AI. Use **Download cloud backup** periodically.

### Optional AI on the hosted version

The previous v0.6 **Sign in with ChatGPT** code uses a localhost-only redirect. It **cannot** be reused as a cloud-hosted sign-in flow. This cloud version disables it rather than pretending it works. **Rule-based evidence scoring, CSV imports, council scenarios and persistent bias all work without AI credentials.**

For AI prose, ticker request refinement and council synthesis, separately add `OPENAI_API_KEY` as a **secret environment variable in Render**, then redeploy. This uses the **OpenAI API's separate billing**; your ChatGPT Plus subscription does not pay for API usage. Never put your key in GitHub, chat, a CSV or the web dashboard. The default model is `gpt-4.1-mini` and can be changed with `OPENAI_MODEL` if the API account supports another model. **AI runs only when you ask for it**, not in background, to avoid unattended costs.

### Research flow from iPhone

1. Open **Interdisciplinary Council**; type a research question and let the planner request a minimal ticker basket.
2. Export those tickers from TradingView, save the CSVs in your iPhone's Files app, and upload each chart in **Chart CSV imports** or in the Council's request checklist.
3. Tap **Re-run interdisciplinary analysis**. The app compares overlapping instrument histories, flags missing non-price evidence and maintains your held fundamental bias across sessions.
4. If `OPENAI_API_KEY` is configured, you can request **AI synthesis** for the interdisciplinary scenario report. This is a conditional research forecast, not a live trade signal.
5. Scan news manually with **Scan web**. In this cloud config the web-poller is disabled by default (`DISABLE_POLLING=1`). To permit periodic *non-AI* news scans while the Render instance stays on, set it to `0` (default 15-minute interval), keeping an eye on source limits.

## Important service details

- Render env variables from the Blueprint: `CLOUD_MODE=1`, `NARRATIVE_DB=/var/data/narrative.db`, `NARRATIVE_AUTH_DIR=/var/data/auth`, `DISABLE_POLLING=1`, `ENABLE_REMOTE_MARKET=0`, `APP_PASSWORD=<set privately>`, `APP_SESSION_SECRET=<auto generated>`.
- **Do not use Render's free web service for persistent SQLite storage.** Its ephemeral files do not survive deploys; the paid disk is required.
- Run **one web worker / one instance** as specified. SQLite and the in-memory login rate limiter are deliberately single-instance. This is not a multi-user production SaaS.
- Password sessions use HMAC-signed cookies, `HttpOnly`, `Secure`, `SameSite=Strict` and a 7-day expiry. Login attempts are rate limited. All write operations reject cross-origin requests. Changing `APP_PASSWORD` invalidates earlier sessions.
- The service is HTTPS-encrypted in transit via Render. The disk is persistent, but persistence is **not the same as a backup**; use **Download cloud backup** after important research. Research and CSVs reside with your hosting provider, not exclusively on your iPhone.
- The public `/health` endpoint returns only service status/version; it does not expose research data. The login screen is public. Static assets, the dashboard and all APIs are behind authentication.
- Use a unique password and enable two-factor authentication on your GitHub and Render accounts. Never share the URL and password together.
- Existing local research remains on the Windows machine until you import the old `narrative.db`. Import source must be a genuine SQLite database, not a JSON export. Max 32 MB per upload.
- Background AI is deliberately disabled; optional API-key calls can incur charges when manually requested. Web-based news search remains a best-effort source discovery tool, not a guaranteed low-latency financial data feed.

## Local verification (optional)

From this extracted folder:

```bash
python -m pip install -r requirements.txt
python -m pip install pytest httpx
python -m pytest -q
```

To simulate the private cloud service locally in a development environment, set `CLOUD_MODE=1`, `APP_PASSWORD` and `APP_SESSION_SECRET` (32+ chars), `NARRATIVE_DB` to a writable path, then use `uvicorn app:app --host 127.0.0.1 --port 8000`. **The `Secure` session cookie is designed for HTTPS; test browser sign-in on Render's HTTPS URL rather than exposing a local HTTP service to the internet.**

## Current verification status

Code and API checks are automated, but external deployment still needs your GitHub/Render authorisation and a live HTTPS acceptance test. An actual TradingView CSV and live AI sign-in have not been tested end-to-end on a production-hosted instance. See `README-v06-local.md` for the original model/research design.

## v0.7 — Unified Research Studio (on demand)

Narrative OS now has an **on-demand Research Studio** on the sidebar and an entry point on Overview:

1. **Discover**: enter a research mandate, select a ticker/horizon, optionally run a targeted headline scan, and request AI discovery. AI must propose multiple *unconventional cross-disciplinary* causal mechanisms, one provisional priority and serious challengers, with observable earliest signals, missing external evidence and falsifiers. The original headline text/URLs are source metadata, **not proof of the proposed claims**.
2. **Commit to a provisional thesis**: if no prior directional bias exists, a valid AI discovery can seed an explicitly **AI-proposed, unverified** bullish or bearish working bias. It does **not** overwrite a held user or evidence-based bias; headlines, price noise and repeated identical CSVs cannot flip an established fundamental position.
3. **Request and upload chart data**: AI chooses 2–6 cross-market instruments from a validation catalog; download TradingView CSVs manually in the requested timeframes and upload each. External non-price measurements remain separately required. Do not upload passwords or account credentials.
4. **Analyse uploaded markets**: the app aligns completed candle timestamps and computes descriptive cross-market results. The user can request AI synthesis and a qualitative **theory horse race**. The race may re-rank candidate explanations using the actual uploaded context, but cannot by itself reverse the retained fundamental bias.
5. **Refresh evidence and reassess**: one explicit button performs a new targeted news search, revises evidence scores and the held/challenged/switch bias state, and optionally runs AI synthesis when the required CSVs are ready. Every action is user-triggered; the app does **not** poll 100s of tickers or continuously call the AI.

This workflow is a **single controlled council synthesis**, not hundreds of independently simulated agents. AI priorities and qualitative points are not calibrated probabilities, confirmed physical-market mechanisms, guaranteed causal findings, or trade signals. If there are no verifiable source or price observations, the dashboard keeps the distinction between a tentative idea and a verified fundamental development. Research data stays on the existing persistent disk; the upgrade only adds optional JSON fields to council plan/run records and does not migrate or reset earlier data.