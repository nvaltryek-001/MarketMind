# 📈 MarketMind — Autonomous Indian Stock Intelligence

> An AI-powered multi-agent stock intelligence platform for analyzing Indian stocks using technical, fundamental, sentiment, risk, EDA, and ML-based signals.

---

## 🚀 Overview

**MarketMind** is an intelligent stock-analysis platform designed to provide a structured view of Indian stocks from multiple analytical perspectives.

Instead of relying on a single indicator, MarketMind combines multiple intelligence modules and presents the results through a unified **War Room** dashboard.

The system analyzes a stock and produces:

- 📊 Technical analysis
- 💰 Fundamental analysis
- 📰 Sentiment analysis
- ⚠️ Risk analysis
- 🤖 Machine-learning signals
- 📈 Exploratory Data Analysis (EDA)
- 🧠 Conviction Engine
- 🎯 Final BUY / HOLD / SELL verdict
- 📋 Historical analysis reports

The platform is designed to make complex market information easier to inspect through a single interactive interface.

---

# ✨ Key Features

## 1. 📊 Technical Analysis

MarketMind processes market price and volume information to generate technical insights.

Supported market data includes:

- OHLCV data
- Price movement
- Trading volume
- Candlestick visualization
- Multiple time ranges
- Technical indicators

The frontend provides an interactive chart-based view of the analyzed stock.

---

## 2. 💰 Fundamental Analysis

The system evaluates available company fundamentals and presents them as part of the overall intelligence report.

Fundamental analysis can include information such as:

- Company financial information
- Valuation-related metrics
- Corporate information
- Shareholding information
- Company actions

---

## 3. 📰 Sentiment Intelligence

MarketMind includes a sentiment-analysis layer that attempts to incorporate available market/news sentiment into the overall analysis.

When a sentiment provider is unavailable, the system reports the unavailable signal instead of stopping the complete analysis pipeline.

---

## 4. ⚠️ Risk Analysis

The risk layer evaluates the available signals and identifies the overall risk condition of the analyzed stock.

The dashboard presents information such as:

- Risk level
- Market regime
- Risk-related signals
- Confidence information

---

## 5. 🤖 Machine Learning

MarketMind contains an ML analysis layer for generating additional predictive signals.

The system also handles insufficient training data safely.

For example:

```text
ML model requires 100+ samples.
Current: 0.
Prediction suppressed.
