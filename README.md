# MarketMind - Autonomous Indian Stock Intelligence

MarketMind is a full-stack AI-powered stock intelligence platform for analyzing Indian equities using multiple analytical layers.

## Features

- Technical Analysis
- Fundamental Analysis
- Sentiment Analysis
- Risk Analysis
- Exploratory Data Analysis
- Machine Learning
- Conviction Engine
- BUY / HOLD / SELL verdict
- Interactive candlestick charts
- Analysis history
- Critic challenges
- Confidence and market regime information
- Fault-tolerant analysis when individual data sources are unavailable

## Architecture

User -> Next.js Frontend -> FastAPI Backend -> Data Ingestion -> Technical / Fundamental / Sentiment / Risk / EDA / ML -> Conviction Engine -> Final Verdict -> Result Page -> History

## Technology Stack

### Frontend
- Next.js 16
- React
- TypeScript
- Turbopack

### Backend
- Python 3.14
- FastAPI
- Uvicorn

### Analysis
- NumPy
- Pandas
- SciPy
- Technical analysis
- Machine Learning
- Exploratory Data Analysis

## API

Current backend exposes 13 routes:

- /health
- /analyze
- /status/{run_id}
- /stream/{run_id}
- /runs
- /report/{run_id}/{symbol}
- /eda/{run_id}
- /ml/{run_id}/{symbol}
- /api/stock/{symbol}/snapshot
- /api/stock/{symbol}/option-chain
- /api/stock/{symbol}/corporate-actions
- /api/stock/{symbol}/shareholding
- /api/stock/{symbol}/ohlcv

## Local Setup

### Backend

    pip install -r backend/requirements.txt
    python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000

Backend: http://127.0.0.1:8000

API Docs: http://127.0.0.1:8000/docs

### Frontend

    cd frontend
    npm install
    npm run dev

Frontend: http://localhost:3000

Set:

    NEXT_PUBLIC_API_URL=http://127.0.0.1:8000

## Analysis Flow

Stock Selection
-> Data Collection
-> Technical Analysis
-> Fundamental Analysis
-> Sentiment Analysis
-> Risk Analysis
-> EDA
-> ML
-> Conviction Engine
-> Final Verdict
-> Result Page
-> History

## Fault Tolerance

If ML training data is insufficient, the ML prediction is suppressed and the remaining analysis continues.

If an external intelligence provider is unavailable, the system reports the unavailable signal while continuing available analysis modules.

## Verification

Latest local verification:

- Backend Health: PASS
- OpenAPI: PASS
- 13 API routes detected
- Runs API: PASS
- Frontend Home: PASS
- History Page: PASS
- MarketMind Branding: PASS
- TypeScript: PASS
- Production Build: PASS
- Git Branch: main

## Project Status

Local development and automated verification are complete.

GitHub push and production deployment are the next stages.

## Disclaimer

MarketMind is an educational and analytical software project. Its outputs are not financial advice or recommendations to buy or sell securities.

## License

Add the selected project license before public distribution.
