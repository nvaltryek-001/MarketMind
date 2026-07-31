<div align="center">

# 🔮 FinSight — Autonomous Indian Stock Intelligence System

**A multi-agent AI system that performs institutional-grade equity research on Indian stocks in real time.**

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Next.js](https://img.shields.io/badge/Next.js-16-000000?style=for-the-badge&logo=next.js&logoColor=white)](https://nextjs.org)
[![React](https://img.shields.io/badge/React-19-61DAFB?style=for-the-badge&logo=react&logoColor=black)](https://react.dev)
[![SQLite](https://img.shields.io/badge/SQLite-003B57?style=for-the-badge&logo=sqlite&logoColor=white)](https://sqlite.org)
[![License](https://img.shields.io/badge/License-MIT-yellow?style=for-the-badge)](LICENSE)

[Features](#-features) · [Architecture](#-architecture) · [Quick Start](#-quick-start) · [API Reference](#-api-reference) · [Tech Stack](#-tech-stack)

</div>

---

## 📖 Overview

FinSight is an **autonomous multi-agent stock intelligence system** purpose-built for the **Indian equity market** (NSE/BSE). It combines three interconnected subsystems:

1. **Multi-Agent Analysis Pipeline** — Orchestrates **10 specialized AI agents** that run concurrently — fetching live market data, computing technical indicators, analyzing fundamentals, gauging news sentiment via LLMs, assessing risk, predicting price direction with ML, performing deep exploratory data analysis, interpreting macro FII/DII flows, and stress-testing bullish calls through a built-in Critic — then synthesises everything into a single **BUY / HOLD / SELL** verdict with a detailed research report.

2. **NSE/BSE Market Data API** — A real-time market data layer with live stock snapshots, option chain analytics (PCR, max pain, OI buildup classification), corporate actions history, shareholding patterns, and OHLCV candlestick data — all with TTL-based caching and automatic NSE session management with retry logic.

3. **Quantitative Intelligence Engines** — Three standalone engines that detect derivative expiry patterns, flag filing anomalies from BSE XML disclosures, and track promoter holding velocity — combined into a weighted composite intelligence score.

The system features a **"War Room"**-themed React dashboard with real-time progress tracking via Server-Sent Events (SSE), interactive candlestick charts (TradingView Lightweight Charts), per-stock drill-down reports, and a three-panel intelligence layout. An additional **vanilla HTML/JS frontend** provides a lightweight interface for the market data and intelligence engine APIs.

> ⚠️ **Disclaimer**: FinSight is built for **educational and research purposes only**. It is not SEBI-registered investment advice. Always consult a qualified financial advisor before making investment decisions.

---

## ✨ Features

| Category | Highlights |
|---|---|
| **Multi-Agent Pipeline** | 10 autonomous agents run in parallel across a 4-stage orchestrated pipeline |
| **Real-Time Streaming** | SSE-based live progress updates — watch each agent complete in real time |
| **Regime-Aware ML** | GradientBoosting ensemble with regime detection (bull/bear/sideways) for 5-day direction forecasting |
| **LLM-Powered Analysis** | Sentiment analysis, research report generation, and critic challenges via OpenRouter (Claude Haiku) |
| **War Room Dashboard** | Three-panel Next.js 16 UI — Intelligence Feed, Interactive Chart Room, Verdict Panel |
| **Live Market Data** | NSE stock snapshots, option chains with analytics, corporate actions, shareholding patterns |
| **Option Chain Analytics** | Put-Call Ratio, Max Pain calculation, OI buildup classification (long/short buildup, covering, unwinding) |
| **Expiry Pattern Detection** | Historical analysis of pre/post-expiry behavior patterns (rally, selloff, pin-to-strike) |
| **Filing Anomaly Detection** | BSE XML filing parser that detects auditor changes, going concern qualifications, material RPTs, pledge creations |
| **Promoter Velocity Tracking** | Promoter holding momentum analysis with acceleration anomaly detection and price correlation |
| **Composite Intelligence Score** | Weighted score combining promoter velocity (45%), expiry pattern (25%), and filing resilience (30%) |
| **Macro Flow Intelligence** | FII/DII activity tracking with confidence multiplier adjustment |
| **Critic Agent** | Automated devil's advocate that stress-tests bullish synthesis calls |
| **Exploratory Data Analysis** | Statistical distributions, outlier detection, volatility regimes, correlation matrices |
| **Multi-Stock Support** | Analyze up to 5 NSE/BSE stocks simultaneously with cross-correlation analysis |
| **Persistent Storage** | SQLite-backed run history with full agent output replay |
| **TTL Caching** | In-memory TTL cache layer — 5-minute TTL for live quotes, 1-hour TTL for analysis results |
| **Conflict Detection** | Automatic identification of disagreements between agents and macro-flow divergences |

---

## 🏗 Architecture

### System Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│           FRONTEND (Next.js 16 — War Room)  :3000                      │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                 │
│  │ Intelligence  │  │  Chart Room   │  │   Verdict    │                 │
│  │   Feed (SSE)  │  │(Candlestick) │  │    Panel     │                 │
│  │   28% width   │  │  44% width   │  │  28% width   │                 │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘                 │
│         └─────────────────┴─────────────────┘                          │
│                            │ Axios / SSE                                │
├────────────────────────────┼────────────────────────────────────────────┤
│  VANILLA FRONTEND (HTML/JS/CSS — Intelligence Dashboard)               │
│  ┌───────────┐  ┌───────────────┐  ┌──────────────┐                   │
│  │ Watchlist  │  │ Tabbed Panel  │  │  Composite   │                   │
│  │ + Search   │  │(Promo/Expiry/ │  │  Intelligence│                   │
│  │           │  │ Filing Flags) │  │  Matrix      │                   │
│  └───────────┘  └───────────────┘  └──────────────┘                   │
└────────────────────────────┼────────────────────────────────────────────┘
                             │
              ┌──────────────┴──────────────┐
              │                             │
    ┌─────────▼─────────┐        ┌──────────▼──────────┐
    │   FastAPI Server   │        │  /api/stock/...     │
    │   (REST + SSE)     │        │  /api/analysis/...  │
    │   :8000            │        │  (Market Data API)  │
    └─────────┬─────────┘        └──────────┬──────────┘
              │                             │
    ┌─────────▼─────────┐        ┌──────────▼──────────┐
    │   Orchestrator     │        │   Intelligence      │
    │  (Pipeline Mgr)    │        │   Engines           │
    └─────────┬─────────┘        │  ┌──────────────┐   │
              │                   │  │ExpiryPattern │   │
       ┌──────┴───────┐          │  │FilingAnomaly │   │
       │  10 Agents   │          │  │PromoterVeloc.│   │
       │  (see below) │          │  └──────────────┘   │
       └──────┬───────┘          └──────────┬──────────┘
              │                             │
    ┌─────────▼─────────┐        ┌──────────▼──────────┐
    │    SQLite DB       │        │  NSE Market Data    │
    │  (finsight.db)     │        │  Service (httpx)    │
    └───────────────────┘        │  + TTL Cache        │
                                  └─────────────────────┘
```

### Multi-Agent Pipeline

```
┌─────────────────────────────────────────────────────────────────────┐
│                      ORCHESTRATOR PIPELINE                          │
│                                                                     │
│  Stage 1 ─── Data Ingestion (sequential per symbol)                │
│       │                                                             │
│       ▼                                                             │
│  Stage 2 ─── EDA + ML Prediction + Macro (parallel)                │
│       │       ┌──────┬─────────────┬───────────┐                   │
│       │       │ EDA  │  ML Agent   │ Macro     │                   │
│       │       │(all) │ (per symbol)│ (FII/DII) │                   │
│       │       └──────┴─────────────┴───────────┘                   │
│       ▼                                                             │
│  Stage 3 ─── Core Analysis (parallel per symbol)                   │
│       │       ┌────────┬───────────┬──────────┬──────┐             │
│       │       │Techni- │Fundamen-  │Sentiment │ Risk │             │
│       │       │cal     │tal        │(LLM)     │      │             │
│       │       └────────┴───────────┴──────────┴──────┘             │
│       ▼                                                             │
│  Stage 4 ─── Synthesis → Critic (sequential per symbol)            │
│               ┌────────────────────────────────────┐               │
│               │ Weighted Signal Aggregation (LLM)  │               │
│               │        ↓                           │               │
│               │ Critic Agent (Devil's Advocate)    │               │
│               └────────────────────────────────────┘               │
│                       ↓                                             │
│               ┌──────────────┐                                     │
│               │  SQLite DB   │                                     │
│               └──────────────┘                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### Pipeline Stages

| Stage | Agents | Execution | Description |
|-------|--------|-----------|-------------|
| **1** | Data Ingestion | Sequential per symbol | Fetches 1-year daily OHLCV from Yahoo Finance (NSE → BSE fallback) |
| **2** | EDA + ML Prediction + Macro | Parallel | Multi-stock EDA + regime-aware ML classifier + FII/DII flows |
| **3** | Technical + Fundamental + Sentiment + Risk | Parallel per symbol | Core analysis agents run concurrently |
| **4** | Synthesis → Critic | Sequential per symbol | Weighted signal aggregation + LLM report → critic challenge loop |

---

## 🤖 Agent Details

### 1. Data Ingestion Agent
- **Source**: Yahoo Finance via `yfinance`
- **Data**: 1-year daily OHLCV (Open, High, Low, Close, Volume)
- **Fallback**: Tries `.NS` (NSE) first, then `.BO` (BSE)
- **Output**: `OHLCVData` with current price and daily change %

### 2. Technical Analysis Agent
- **Indicators**: RSI-14, MACD (12/26/9), Bollinger Bands (20, 2σ), SMA-50, SMA-200
- **Method**: Weighted scoring system across all indicators (max score ±8)
- **Output**: Trend classification (bullish/bearish/sideways) + BUY/SELL/HOLD signal with confidence

### 3. Fundamental Analysis Agent
- **Metrics**: PE ratio, PB ratio, Debt-to-Equity, EPS, Revenue Growth, ROE
- **Benchmark**: Compares against sector PE averages
- **Output**: Valuation assessment + BUY/SELL/HOLD signal

### 4. Sentiment Analysis Agent
- **Source**: Google News RSS (top 10 headlines per stock)
- **Engine**: LLM-powered analysis via OpenRouter (Claude Haiku)
- **Output**: Sentiment score (-1 to +1), key themes, trading signal
- **Fallback**: Returns neutral defaults if LLM is unavailable

### 5. Risk Assessment Agent
- **Metrics**: Beta (vs Nifty 50), Value-at-Risk (95%), Sharpe Ratio, Max Drawdown, Annualized Volatility
- **Classification**: LOW / MEDIUM / HIGH risk levels
- **Output**: Comprehensive risk profile with reasoning

### 6. ML Prediction Agent
- **Model**: Regime-Aware GradientBoosting Ensemble (scikit-learn)
- **Regime Detection**: Classifies market as bull/bear/sideways using volatility + SMA slope thresholds; trains separate models per regime
- **Features**: 27 engineered features across 5 categories:
  - **Momentum** (8): Returns (1d/3d/5d/10d/20d), RSI-14, Momentum-10, ROC-5
  - **Volatility** (6): Rolling vol (5d/10d/20d), ATR-14, BB Width, High-Low Range
  - **Volume** (4): Volume ratios (5d/20d), OBV change, Volume momentum
  - **Calendar** (4): Day of week, Month, Quarter, Month-end flag
  - **Technical** (5): SMA ratios (50/200), Price vs BB upper, MACD histogram, ADX-14
- **Validation**: Time-series cross-validation (5 splits) — no data leakage
- **Labels**: 3-class direction (DOWN < -2%, SIDEWAYS ±2%, UP > +2%) over 5-day horizon
- **Smart Suppression**: When model accuracy is insufficient, the agent self-suppresses with `model_valid=false` and overrides its weight to 0.0 so it doesn't damage the composite score
- **Output**: Predicted direction, confidence, top-10 feature importances, full model metrics

### 7. EDA Agent (Exploratory Data Analysis)
- **Statistics**: Returns & volume distribution (mean, median, std, skewness, kurtosis, normality test)
- **Outlier Detection**: Z-score based identification of volume spikes, price gaps, volatility spikes
- **Volatility Regimes**: Low / Medium / High / Extreme classification with percentile ranking
- **Cross-Correlation**: Pairwise return correlations with relationship labeling
- **Chart Data**: Returns histogram, 30-day rolling volatility, volume MA ratio, price vs SMA overlays

### 8. Macro Flow Agent
- **Source**: BSE FII/DII trade activity data (with `derived_from_index` fallback)
- **Method**: Aggregates 5-day net FII and DII flows, classifies as BULLISH / NEUTRAL / BEARISH
- **Trend Tracking**: Classifies 5-day FII/DII trends as buying / selling / mixed
- **Confidence Multiplier**: Adjusts synthesis confidence (1.1× for bullish FII, 0.9× for bearish)
- **Fallback**: Returns neutral defaults with 1.0× multiplier if API is unreachable

### 9. Meta-Synthesis Agent
- **Method**: Weighted signal aggregation with dynamic weight adjustment
- **Base Weights**: Technical (22%), Fundamental (30%), Sentiment (13%), Risk (20%), ML (15%)
- **Dynamic Adjustment**: Risk level shifts weight from Technical to Fundamental
- **Macro Integration**: Applies FII/DII confidence multiplier to final confidence score
- **Conflict Detection**: Identifies BUY vs SELL disagreements across agents + macro divergences
- **Report**: LLM-generated 400-word institutional-grade equity research report
- **Evidence Trail**: Generates per-agent card data with verdict, score (0–10), weight, weighted score, and key triggers for frontend rendering
- **Output**: Final BUY/SELL/HOLD verdict, confidence, price target estimate, decision logic map

### 10. Critic Agent (Devil's Advocate)
- **Trigger**: Activates when any valid agent disagrees with the final synthesis verdict
- **Method**: LLM-powered challenge — identifies top 3 reasons the thesis could be wrong
- **Penalty Calculation**: Applies 0–15% confidence penalty based on challenge severity
- **Bonus Penalty**: Extra 5% for challenges involving debt, leverage, or overvaluation
- **Output**: Challenge list + confidence penalty applied to synthesis result

---

## ⚙️ Intelligence Engines

Three standalone quantitative engines power the secondary analysis layer, accessible via the `/api/analysis/` routes and combined into a composite score.

### Expiry Pattern Engine
Detects recurring pre- and post-expiry behavior per stock using historical OHLCV data.

| Feature | Detail |
|---|---|
| **Window Returns** | T-5→T-1 return, T-1→T+1 return, max intraday spike for each expiry |
| **Pattern Detection** | `expiry_rally`, `expiry_selloff`, `pin_to_strike`, `no_pattern` |
| **Confidence Scoring** | Weighted blend of hit rate (65%), pattern separation (25%), and sample depth (10%) |
| **Current Signal** | Identifies today's phase (`pre_expiry_window`, `expiry_day`, `post_expiry_window`, `outside_window`) with directional bias |
| **Holiday Awareness** | NSE holidays adjust Thursday expiry dates to previous trading day |

### Filing Anomaly Detector
Parses BSE XML announcement filings and detects high-risk signals.

| Red Flag | Weight | Description |
|---|---|---|
| Going Concern Qualification | 28 | Material uncertainty or going concern language in filings |
| Auditor Change/Resignation | 24 | Statutory auditor resignation or mid-term appointment changes |
| Promoter Pledge Creation | 22 | Encumbrance or creation of pledge on promoter holdings |
| Material Related Party Transaction | 20 | RPTs exceeding ₹10 crore threshold or marked as material |
| Registered Address Change | 14 | Sudden change or relocation of registered office |

- **Risk Score**: 0–100 scale with recency-weighted flag severity (30d: 1.0×, 60d: 0.75×, 90d: 0.55×)
- **Source**: BSE India Announcements XML API

### Promoter Velocity Engine
Tracks the rate of promoter holding change and converts it into statistical signals.

| Metric | Description |
|---|---|
| **Velocity** | Quarter-on-quarter change in promoter holding % |
| **Rolling 4Q Average** | Smoothed velocity trend over 4 quarters |
| **Acceleration** | Change in velocity (rate of rate of change) |
| **Anomaly Flag** | Z-score > 1.5σ from historical acceleration baseline |
| **Price Correlation** | Pearson correlation between velocity and subsequent 30-day price returns |
| **Signal Strength** | 0–100 weighted score: velocity z-score (45%) + correlation (35%) + anomaly (10%) + trend consistency (10%) |

### Composite Intelligence Score
All three engines feed into a weighted composite score:

```
Composite = (0.45 × Promoter Signal Strength)
          + (0.25 × Expiry Opportunity Score)
          + (0.30 × Filing Resilience)
```

| Score Range | Outlook |
|---|---|
| ≥ 70 | `strong_opportunity` |
| 55–69 | `opportunity` |
| 45–54 | `neutral` |
| 30–44 | `caution` |
| < 30 | `high_risk` |

---

## 🛠 Tech Stack

### Backend
| Technology | Purpose |
|---|---|
| **Python 3.11+** | Core language |
| **FastAPI** | Async REST API + SSE streaming |
| **SQLAlchemy 2.0** | ORM with SQLite persistence |
| **Pydantic v2** | Schema validation with 20+ models |
| **yfinance** | Yahoo Finance market data |
| **pandas + pandas-ta** | Data manipulation + technical indicators |
| **pandas-ta-classic** | Legacy indicator compatibility |
| **scikit-learn** | ML pipeline (StandardScaler + GradientBoosting regime ensemble) |
| **XGBoost** | Gradient boosting framework |
| **scipy** | Statistical tests (Shapiro-Wilk normality) |
| **NumPy** | Numerical computing for engines |
| **feedparser** | Google News RSS parsing |
| **httpx** | Async HTTP client for OpenRouter LLM, NSE/BSE API calls |
| **sse-starlette** | Server-Sent Events for real-time streaming |
| **beautifulsoup4 + lxml** | HTML/XML parsing for BSE filing data |
| **python-dotenv** | Environment variable management |

### Frontend
| Technology | Purpose |
|---|---|
| **Next.js 16** | React framework with App Router |
| **React 19** | UI components |
| **TypeScript** | Type-safe frontend |
| **Tailwind CSS 4** | Utility-first styling (War Room theme) |
| **Lightweight Charts v5** | TradingView-powered candlestick chart with markers |
| **Recharts** | Interactive charts (bar, radar, heatmap, histogram) |
| **Lucide React** | Icon library |
| **Axios** | HTTP client for API communication |

### Infrastructure
| Technology | Purpose |
|---|---|
| **SQLite** | Embedded database for run persistence |
| **TTL Cache** | Thread-safe in-memory cache with configurable TTL per tier |
| **NSEMarketDataService** | Production-grade NSE API client with session management, retries, rate limiting |

---

## 🚀 Quick Start

### Prerequisites

- **Python 3.11+** and **pip**
- **Node.js 18+** and **npm**
- (Optional) **OpenRouter API key** for LLM-powered sentiment analysis & report generation

### 1. Clone the Repository

```bash
git clone https://github.com/bhuvantharanath/FinSight-Autonomous-Indian-Stock-Intelligence-System.git
cd FinSight-Autonomous-Indian-Stock-Intelligence-System
```

### 2. Backend Setup

```bash
# Create and activate virtual environment
python -m venv venv
source venv/bin/activate        # macOS/Linux
# venv\Scripts\activate         # Windows

# Install dependencies
pip install -r backend/requirements.txt
```

### 3. Configure Environment Variables

```bash
# Copy the example env file
cp .env.example .env
```

Edit `.env` with your settings:

```env
OPENROUTER_API_KEY=your_openrouter_api_key_here
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
SYNTHESIS_MODEL=anthropic/claude-haiku-4-5
SENTIMENT_MODEL=anthropic/claude-haiku-4-5
```

> **Note**: The system works without an API key — sentiment defaults to neutral, reports use template-based generation, and the critic agent skips LLM challenges.

### 4. Start the Backend

```bash
uvicorn backend.main:app --reload --port 8000
```

The API will be available at `http://localhost:8000`. Visit `http://localhost:8000/docs` for the interactive Swagger UI.

### 5. Frontend Setup (Next.js War Room)

```bash
cd frontend

# Install dependencies
npm install

# Create environment file
echo "NEXT_PUBLIC_API_URL=http://localhost:8000" > .env.local

# Start development server
npm run dev
```

The War Room dashboard will be available at `http://localhost:3000`.

### 6. Vanilla Frontend (Optional)

The vanilla frontend requires no build step — just serve `vanilla-frontend/` with any static server while the backend is running:

```bash
# Using Python's built-in HTTP server
python -m http.server 5500 -d vanilla-frontend
```

Available at `http://localhost:5500`. Provides the stock intelligence dashboard with promoter velocity, expiry patterns, filing flags, option chain data, and composite scoring.

### 7. NSE Intelligence Microservice (Optional)

A separate FastAPI service for standalone NSE/BSE data access:

```bash
cd nse-intelligence
pip install -r requirements.txt
uvicorn main:app --reload --port 8001
```

---

## 📡 API Reference

### Multi-Agent Analysis Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/analyze` | Start a new multi-stock analysis run (max 5 symbols) |
| `GET` | `/status/{run_id}` | Get full run status with all agent outputs |
| `GET` | `/stream/{run_id}` | SSE stream for real-time progress updates |
| `GET` | `/runs` | List the 10 most recent analysis runs |
| `GET` | `/report/{run_id}/{symbol}` | Get detailed synthesis report for a symbol |
| `GET` | `/eda/{run_id}` | Get exploratory data analysis results |
| `GET` | `/ml/{run_id}/{symbol}` | Get ML prediction details for a symbol |
| `GET` | `/health` | Liveness probe |

### Stock Market Data Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/stock/{symbol}/snapshot` | Live stock quote — price, change, 52W range, delivery %, circuit limits |
| `GET` | `/api/stock/{symbol}/option-chain` | Full option chain with analytics (PCR, max pain, OI buildup) |
| `GET` | `/api/stock/{symbol}/corporate-actions` | 3-year corporate action history (dividends, splits, bonuses) |
| `GET` | `/api/stock/{symbol}/shareholding` | Quarterly shareholding pattern (promoter, FII, DII) |
| `GET` | `/api/stock/{symbol}/ohlcv?period=6mo` | OHLCV candlestick data (periods: 1mo, 3mo, 6mo, 1y, 2y) |

### Intelligence Analysis Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/analysis/{symbol}/promoter-velocity` | Promoter holding velocity, acceleration, anomaly detection, signal |
| `GET` | `/api/analysis/{symbol}/expiry-pattern` | Expiry window returns, pattern detection, current signal |
| `GET` | `/api/analysis/{symbol}/filing-flags` | BSE filing red flag detection with risk score |
| `GET` | `/api/analysis/{symbol}/composite-score` | Weighted composite intelligence score across all engines |

### NSE Intelligence Microservice Endpoints (port 8001)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/nse/quote/{symbol}` | Raw + normalized NSE equity quote |
| `GET` | `/nse/options/{symbol}` | Raw + normalized option chain |
| `GET` | `/nse/corporate-actions` | Market-wide corporate actions |
| `GET` | `/bse/filings` | Paginated BSE XML filing announcements |
| `GET` | `/health` | Liveness probe |

### Example: Start Analysis

```bash
curl -X POST http://localhost:8000/analyze \
  -H "Content-Type: application/json" \
  -d '{"symbols": ["RELIANCE", "TCS", "INFY"]}'
```

**Response** (202 Accepted):
```json
{
  "run_id": "a1b2c3d4-...",
  "status": "started",
  "message": "Analysis started for RELIANCE, TCS, INFY. Track progress at /status/a1b2c3d4-..."
}
```

### Example: Get Composite Intelligence Score

```bash
curl http://localhost:8000/api/analysis/RELIANCE/composite-score
```

**Response**:
```json
{
  "symbol": "RELIANCE",
  "cached": false,
  "analysis": {
    "symbol": "RELIANCE",
    "composite": {
      "composite_score": 62.45,
      "outlook": "opportunity",
      "component_scores": {
        "promoter_signal_strength": 55.0,
        "expiry_pattern_opportunity": 50.0,
        "filing_resilience": 100.0,
        "filing_risk": 0.0
      }
    },
    "inputs": {
      "promoter_velocity_signal": { "velocity": -0.12, "direction": "decreasing", "signal_strength": 55 },
      "expiry_pattern_signal": { "phase": "pre_expiry_window", "directional_bias": "neutral" },
      "filing_risk": { "risk_score": 0, "flags_found": [] }
    }
  }
}
```

### Example: Poll Run Status

```bash
curl http://localhost:8000/status/{run_id}
```

**Response**:
```json
{
  "run_id": "a1b2c3d4-...",
  "symbols": ["RELIANCE", "TCS", "INFY"],
  "status": "completed",
  "agents": {
    "technical_RELIANCE": {
      "agent_name": "technical",
      "status": "completed",
      "signal": "BUY",
      "confidence": 0.75,
      "reasoning": "RELIANCE shows a bullish trend with RSI at 42.3..."
    }
  },
  "results": {
    "RELIANCE": {
      "final_verdict": "BUY",
      "overall_confidence": 0.68,
      "price_target_pct": 12.8,
      "summary": "BUY RELIANCE with 68% confidence..."
    }
  }
}
```

---

## 📁 Project Structure

```
FinSight-Autonomous-Indian-Stock-Intelligence-System/
├── backend/                          # Multi-agent analysis pipeline
│   ├── agents/
│   │   ├── data_ingestion.py         # Yahoo Finance OHLCV fetcher
│   │   ├── technical.py              # RSI, MACD, Bollinger, SMA analysis
│   │   ├── fundamental.py            # PE, PB, D/E, ROE valuation
│   │   ├── sentiment.py              # News RSS + LLM sentiment
│   │   ├── risk.py                   # Beta, VaR, Sharpe, drawdown
│   │   ├── ml_agent.py               # Regime-aware GradientBoosting ensemble
│   │   ├── eda_agent.py              # Exploratory data analysis
│   │   ├── macro_agent.py            # FII/DII flow analysis
│   │   ├── synthesis.py              # Meta-synthesis + report generation
│   │   └── critic.py                 # Devil's advocate challenge agent
│   ├── models/
│   │   └── schemas.py                # 20+ Pydantic v2 models
│   ├── database.py                   # SQLAlchemy ORM + CRUD operations
│   ├── orchestrator.py               # 4-stage async pipeline coordinator
│   ├── main.py                       # FastAPI app with REST + SSE endpoints
│   └── requirements.txt              # Python dependencies
│
├── api/                              # Market data & analysis API layer
│   ├── routes/
│   │   ├── stock.py                  # /api/stock/ — snapshot, option-chain, OHLCV
│   │   └── analysis.py               # /api/analysis/ — engines + composite score
│   ├── services/
│   │   └── market_data.py            # NSEMarketDataService (721 LOC) — session
│   │                                 # management, retries, rate limiting, parsing
│   ├── cache.py                      # TTLCache with 5min/1hr tiers
│   └── main.py                       # Standalone API app factory (development)
│
├── engines/                          # Quantitative intelligence engines
│   ├── expiry_pattern.py             # Derivative expiry pattern detection
│   ├── filing_anomaly.py             # BSE XML filing red flag detector
│   └── promoter_velocity.py          # Promoter holding momentum analysis
│
├── nse-intelligence/                 # Standalone NSE/BSE data microservice
│   ├── data/
│   │   ├── fetcher.py                # NSE API fetcher with session handling
│   │   ├── parser.py                 # Quote, option chain, corporate action parsers
│   │   └── bse_parser.py             # BSE XML announcement parser
│   ├── config.py                     # NSE/BSE API configuration
│   ├── main.py                       # FastAPI microservice entry point
│   └── requirements.txt              # Microservice dependencies
│
├── vanilla-frontend/                 # Lightweight vanilla JS frontend
│   ├── index.html                    # Single-page intelligence dashboard
│   ├── app.js                        # API integration, charts, composite view
│   ├── style.css                     # Dark theme styling
│   └── prefetch.js                   # Asset prefetching
│
├── frontend/                         # Next.js 16 War Room dashboard
│   ├── src/
│   │   ├── app/
│   │   │   ├── page.tsx              # Intelligence Terminal (stock input)
│   │   │   ├── layout.tsx            # Root layout with metadata + fonts
│   │   │   ├── globals.css           # War Room theme + CSS variables
│   │   │   ├── run/[runId]/
│   │   │   │   └── page.tsx          # War Room 3-panel analysis view
│   │   │   └── history/
│   │   │       └── page.tsx          # Mission Archive (past runs)
│   │   ├── components/
│   │   │   ├── Navbar.tsx            # Navigation bar
│   │   │   ├── IntelligenceFeed.tsx  # Real-time agent status feed (SSE)
│   │   │   ├── VerdictPanel.tsx      # Final verdict + confidence display
│   │   │   ├── EvidenceTrail.tsx     # Agent decision logic trail
│   │   │   ├── warroom/
│   │   │   │   └── ChartRoom.tsx     # Chart panel wrapper
│   │   │   └── charts/
│   │   │       ├── CandlestickChart.tsx      # TradingView lightweight-charts
│   │   │       ├── ConfusionMatrix.tsx       # ML model confusion matrix
│   │   │       ├── CorrelationHeatmap.tsx    # Cross-stock correlation
│   │   │       ├── FeatureImportanceChart.tsx# ML feature importance
│   │   │       ├── MLPredictionCard.tsx      # ML prediction summary
│   │   │       ├── ReturnsHistogram.tsx      # Return distribution
│   │   │       └── VolatilityChart.tsx       # Rolling volatility
│   │   └── lib/
│   │       ├── api.ts                # Typed API client (Axios)
│   │       └── utils.ts              # Signal colors, formatting utilities
│   ├── next.config.ts
│   ├── package.json
│   └── tsconfig.json
│
├── .env.example                      # Environment variable template
├── .gitignore
├── Dockerfile                        # Container build (placeholder)
├── docker-compose.yml                # Container orchestration (placeholder)
└── README.md
```

---

## 🔧 Configuration

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `OPENROUTER_API_KEY` | No | `""` | OpenRouter API key for LLM features |
| `OPENROUTER_BASE_URL` | No | `https://openrouter.ai/api/v1` | OpenRouter API base URL |
| `SYNTHESIS_MODEL` | No | `anthropic/claude-haiku-4-5` | LLM model for report generation |
| `SENTIMENT_MODEL` | No | `anthropic/claude-haiku-4-5` | LLM model for sentiment analysis |

### Synthesis Agent Weights

The final verdict is computed using weighted signals from all agents. Default weights (configurable in `backend/agents/synthesis.py`):

```
Fundamental: 30%  ████████████████
Technical:   22%  ████████████
Risk:        20%  ███████████
ML:          15%  ████████
Sentiment:   13%  ███████
```

After synthesis, the Macro Flow agent applies a confidence multiplier (0.9×–1.1×), and the Critic agent may apply an additional penalty (0–15%).

### Cache TTLs

| Cache Tier | TTL | Covered Routes |
|---|---|---|
| **Live Quotes** | 5 minutes | `/api/stock/{symbol}/snapshot`, `/api/stock/{symbol}/ohlcv` |
| **Analysis** | 1 hour | `/api/analysis/{symbol}/*`, `/api/stock/{symbol}/corporate-actions`, `/api/stock/{symbol}/shareholding` |

### NSE Market Data Service Configuration

| Parameter | Default | Description |
|---|---|---|
| `timeout_seconds` | 20.0 | HTTP request timeout |
| `max_retries` | 4 | Maximum retry attempts per request |
| `retry_backoff_seconds` | 0.8 | Base backoff between retries (exponential) |
| `min_request_interval_seconds` | 0.4 | Rate limiter: minimum gap between requests |

---

## 🧪 Usage Examples

### Single Stock Analysis
```
Input: RELIANCE
```
Analyzes Reliance Industries across all 10 agents and produces a comprehensive verdict.

### Multi-Stock Comparison
```
Input: RELIANCE, TCS, INFY, HDFCBANK, ICICIBANK
```
Runs full analysis on all 5 stocks, plus generates cross-correlation analysis and portfolio-level EDA.

### Supported Symbols
Any valid **NSE** or **BSE** ticker symbol. Examples:
- Large Cap: `RELIANCE`, `TCS`, `INFY`, `HDFCBANK`, `ICICIBANK`
- Mid Cap: `BAJFINANCE`, `ADANIGREEN`, `TATAMOTORS`, `WIPRO`
- Banking: `SBIN`, `KOTAKBANK`, `AXISBANK`, `INDUSINDBK`

---

## 📊 War Room Dashboard

### Intelligence Feed (Left Panel)
- Real-time SSE-powered agent status feed with animated transitions
- Per-agent signal badges (BUY/SELL/HOLD) and confidence scores
- Live progress tracking with color-coded states (pending → running → completed/failed)

### Chart Room (Center Panel)
- **Candlestick Chart** — TradingView Lightweight Charts v5 with OHLCV data
- **Agent Signal Markers** — Visual arrows on chart for each agent's signal
- **Time Range Selector** — 1M / 3M / 6M / 1Y view toggles
- **Volume Overlay** — Color-coded volume bars (green for up, red for down)

### Verdict Panel (Right Panel)
- Final BUY/SELL/HOLD verdict with confidence percentage
- Price target estimate with directional indicator
- Agent weight breakdown visualization
- Conflict detection and macro flow warnings

### Evidence Trail (Center Bottom)
- Interactive agent decision cards showing signal, weight, and key triggers
- Critic challenge display for bullish calls
- Hover-to-highlight: hovering a card highlights corresponding chart marker

### History Page (Mission Archive)
- Tabular view of all past analysis runs
- Status badges, duration tracking, and direct links to War Room views

---

## 🧩 Vanilla Intelligence Dashboard

A lightweight static frontend (`vanilla-frontend/`) for the market data and intelligence engine APIs:

- **Stock Search & Watchlist** — Real-time search with auto-selection
- **Price Strip** — Live price, change %, day range indicator, delivery %
- **Tabbed Analysis Panel**:
  - **Promoter Velocity** — Sparkline chart, velocity gauge (-100 to +100), natural language summary
  - **Expiry Pattern** — Expiry returns chart, pattern label with confidence ticks, signal sentence
  - **Filing Red Flags** — Risk score badge with timeline of detected flags
- **Corporate Actions & Shareholding** — Timeline chart + shareholding pattern canvas
- **Composite Intelligence Matrix** — Multi-stock comparison grid with per-engine scores and strongest signal highlight

---

## 🤝 Contributing

Contributions are welcome! Please follow these steps:

1. **Fork** the repository
2. **Create** a feature branch (`git checkout -b feature/amazing-feature`)
3. **Commit** your changes (`git commit -m 'Add amazing feature'`)
4. **Push** to the branch (`git push origin feature/amazing-feature`)
5. **Open** a Pull Request

---

## 📄 License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

---

## 🙏 Acknowledgments

- [Yahoo Finance](https://finance.yahoo.com/) via **yfinance** for market data
- [OpenRouter](https://openrouter.ai/) for LLM API access
- [Google News RSS](https://news.google.com/) for financial news headlines
- [pandas-ta](https://github.com/twopirllc/pandas-ta) for technical indicators
- [TradingView Lightweight Charts](https://tradingview.github.io/lightweight-charts/) for candlestick rendering
- [Recharts](https://recharts.org/) for React charting components
- [NSE India](https://www.nseindia.com/) for equity quotes, option chains, and FII/DII data
- [BSE India](https://www.bseindia.com/) for corporate filing announcements
- [scikit-learn](https://scikit-learn.org/) for machine learning pipelines
- [XGBoost](https://xgboost.readthedocs.io/) for gradient boosting framework

---

<div align="center">

**Built with ❤️ for the Indian investor community**

*FinSight is for educational purposes only. Not SEBI-registered investment advice.*

</div>