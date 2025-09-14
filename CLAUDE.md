# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

MEXC Futures Monitoring System - A real-time monitoring tool for detecting large orders and unusual trading patterns on MEXC futures markets.

## Common Development Commands

### Setup and Run
```bash
# Install dependencies
pip install -r requirements.txt

# Run the monitor with default settings
python monitor.py BTC_USDT ETH_USDT

# Run with custom thresholds
python monitor.py BTC_USDT --min-order 100000 --whale-threshold 250000
```

### Testing API Endpoints
```bash
# Test MEXC futures API connectivity
curl https://contract.mexc.com/api/v1/contract/ping

# Get active contracts
curl https://contract.mexc.com/api/v1/contract/detail
```

## Architecture

The system uses a modular architecture with clear separation of concerns:

- **MEXCFuturesClient** (src/mexc_client.py): Handles all MEXC API interactions, including order books, trades, and market data
- **OrderBookMonitor** (src/order_monitor.py): Analyzes order book data for large orders, walls, imbalances, and spoofing patterns
- **TradeMonitor** (src/trade_monitor.py): Processes trade data to detect large trades, volume surges, and coordinated trading
- **AlertSystem** (src/alert_system.py): Formats and delivers alerts with priority levels and colored console output
- **MEXCFuturesMonitor** (monitor.py): Main orchestrator that coordinates all components and manages the monitoring loop

## Key Technical Details

### MEXC API Endpoints
- Base URL: `https://contract.mexc.com`
- Order Book: `/api/v1/contract/depth/{symbol}`
- Recent Trades: `/api/v1/contract/deals/{symbol}`
- Ticker: `/api/v1/contract/ticker`
- Klines: `/api/v1/contract/kline/{symbol}`

### Monitoring Patterns
- **Large Orders**: Orders exceeding min_order_usdt threshold
- **Whale Detection**: Orders exceeding whale_threshold_usdt
- **Wall Detection**: Orders 3x larger than average in order book
- **Volume Surge**: Trading volume 2x+ baseline average
- **Spoofing**: Orders appearing/disappearing repeatedly at same price levels
- **Coordinated Trades**: Multiple trades at similar prices within 5 seconds

### Alert Priority Levels
- **HIGH** (Red): Whale orders, volume surges, spoofing, coordinated trades
- **MEDIUM** (Yellow): Large orders, walls, aggressive trading
- **LOW** (White): Informational alerts

## Development Guidelines

When modifying this codebase:

1. Maintain the modular architecture - each component should have a single responsibility
2. Use type hints for all function parameters and returns
3. Handle API errors gracefully with try/except blocks
4. Log errors using the logging module, not print statements
5. Keep API rate limits in mind (approximately 20 requests/second for public endpoints)
6. Test with small symbol lists first before scaling up
7. Adjust thresholds based on the liquidity of monitored pairs