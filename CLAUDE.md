# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

MEXC Futures Manipulation Monitor - An advanced system for detecting manipulation patterns in cryptocurrency futures markets using multi-signal analysis and real-time alerts.

## Current Architecture

### Core Components

1. **src/run_multi_monitor.py**: Main entry point
   - Handles environment setup and validation
   - Manages graceful shutdown
   - Displays configuration and startup info

2. **src/multi_pair_monitor.py**: Core monitoring engine
   - Monitors up to 100 futures pairs concurrently
   - Integrates advanced signal detection
   - Manages alert cooldowns and aggregation
   - Sends Telegram notifications

3. **src/advanced_signals.py**: Signal detection algorithms
   - Volume explosion detection (>5x with price confirmation)
   - RSI divergence patterns (bullish/bearish)
   - Momentum shift detection (acceleration/reversals)
   - Order book manipulation (spoofing, liquidity traps)
   - Accumulation/distribution phase detection
   - Composite signal scoring with weighted confidence

4. **src/data_fetcher.py**: MEXC API integration
   - Fetches 1-minute candles
   - Calculates RSI, volume ratios, momentum
   - Handles rate limiting
   - Analyzes price movements

5. **src/enhanced_data_fetcher.py**: Advanced data collection
   - Order book depth analysis
   - Trade flow analysis (wash trading detection)
   - Market microstructure metrics
   - Open interest tracking

6. **src/improved_telegram_notifier.py**: Alert formatting
   - Clear action-based alerts (BUY/SELL signals)
   - Confidence percentages
   - Risk management recommendations
   - Hourly summaries with top opportunities

7. **src/database.py**: MongoDB operations
   - Connection management
   - Index creation for performance
   - Data persistence for pattern analysis

8. **src/analyze_patterns.py**: Historical analysis
   - Finds successful pump patterns
   - Analyzes alert accuracy
   - Identifies optimal signal combinations
   - Generates trading recommendations

## Key Commands

```bash
# Run the main monitor (monitors 100 pairs)
cd src
python run_multi_monitor.py

# Analyze historical patterns
python analyze_patterns.py

# View logs
tail -f ../logs/mexc_monitor_*.log
```

## MongoDB Schema

### market_data
- 1-minute candles with full OHLCV
- Volume analysis (spike detection, ratios)
- Price movement metrics (1m, 5m, 15m, 60m changes)
- Technical indicators (RSI, momentum)

### alerts
- Detected manipulation events
- Risk levels (LOW, MEDIUM, HIGH, EXTREME)
- Pattern details and confidence scores
- Recommended actions

### enhanced_monitoring
- Order book snapshots
- Trade flow analysis
- Market microstructure data
- Manipulation scores

## Signal Detection Logic

The system uses weighted multi-signal detection:

1. **Volume Explosion** (weight: 0.3)
   - Triggers on >5x average volume with price movement
   - Higher confidence with sustained volume

2. **RSI Divergence** (weight: 0.2)
   - Bullish: Price down, RSI up
   - Bearish: Price up, RSI down

3. **Momentum Shifts** (weight: 0.2)
   - Rapid acceleration patterns
   - V-shaped reversals

4. **Liquidity Traps** (weight: 0.15)
   - Wide spreads with low liquidity
   - Spoofing detection

5. **Accumulation/Distribution** (weight: 0.15)
   - Smart money movement patterns
   - Order book imbalances

## Alert System

Alerts are sent via Telegram with:
- Clear actions: STRONG_BUY, BUY, SELL, STRONG_SELL
- Confidence percentages
- Entry/exit recommendations
- Stop loss levels
- 5-minute cooldown per symbol

## Configuration

Key thresholds in `multi_pair_monitor.py`:
- Volume spike: >5x average
- RSI extremes: <20 or >80
- Pump detection: >3% price + >3x volume
- Risk levels: HIGH >50%, EXTREME >70%

## Rate Limiting

- MEXC API: 1200 requests/minute
- 0.2s delay between order book requests
- Concurrent processing with proper async

## Important Notes

- Focus on low-medium volume pairs (<$50M daily)
- High leverage pairs (≥50x) show more manipulation
- Order book data is optional but improves accuracy
- All timestamps in UTC
- Logs rotate daily with 10MB max size

## When Making Changes

1. Test with a small number of pairs first
2. Monitor logs for rate limiting errors
3. Ensure MongoDB indexes are created
4. Verify Telegram formatting looks good
5. Consider alert frequency vs noise

## Troubleshooting

- SSL errors: Normal during high load, handled gracefully
- No alerts: Markets may be stable, check thresholds
- Rate limiting: Reduce pair count or increase delays
- MongoDB connection: Ensure mongod is running