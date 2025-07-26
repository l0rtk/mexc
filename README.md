# MEXC Futures Manipulation Monitor

Advanced monitoring system for detecting manipulation patterns in MEXC futures markets using multi-signal analysis and real-time Telegram alerts.

**⚡ Performance Optimized** - Now runs in 2-3 seconds (was 30+). Multiple monitoring modes available for different use cases.

**🚀 Enhanced V2 Features** - Funding arbitrage, liquidation detection, statistical filtering, and ML-powered signals.

## 🚀 Features

### Core Features
- **Optimized Performance**: 2-3s for 3 pairs, 20-30s for 100 pairs
- **Multi-Pair Monitoring**: Track 3-100 futures pairs simultaneously
- **Real-Time Alerts**: Clear, actionable Telegram notifications
- **MongoDB Storage**: Historical data for pattern analysis
- **Smart Optimization**: Auto-disables slow features when needed

### Signal Detection (V2)
- **Volume Explosion**: Detects >2-5x volume spikes
- **Funding Arbitrage**: Tracks funding rates for arbitrage opportunities
- **Liquidation Cascade**: Predicts stop-loss hunting patterns
- **Statistical Outliers**: Z-score based anomaly detection
- **Multi-Timeframe**: 1m, 5m, 15m divergence analysis
- **Order Book Analysis**: Spoofing and liquidity trap detection
- **RSI Divergence**: Price/momentum divergence patterns
- **Hidden Accumulation**: Smart money movement detection
- **Dynamic Thresholds**: ATR-based adaptive sensitivity

## ⚡ Quick Start

### Monitor 100 Pairs (Full Coverage)
```bash
# Automatic top 100 pairs by volume
./monitor_100_pairs.py

# Or manually with fast mode (recommended for 100 pairs)
cd src
python monitor_optimized.py --mode fast --file ../watchlists/top_100.txt
```

### Monitor 3-10 Pairs (Best Performance)
```bash
cd src

# First run - use startup mode (sensitive thresholds)
python monitor_optimized.py --mode startup AIXBT_USDT USUAL_USDT XMR_USDT

# Active trading - use fast mode (5s updates)
python monitor_optimized.py --mode fast AIXBT_USDT USUAL_USDT XMR_USDT

# After 24h - use balanced mode (better signals)
python monitor_optimized.py --mode balanced AIXBT_USDT USUAL_USDT XMR_USDT
```

### Performance Modes

| Mode | 3 Pairs | 100 Pairs | Features | Best For |
|------|---------|-----------|----------|----------|
| **startup** | 2-3s | 20-30s | Basic + Funding | First 24h, testing |
| **fast** | 1-2s | 20-30s | Minimal | Active trading, 100 pairs |
| **balanced** | 3-5s | 40-60s | Most features | Daily monitoring |
| **thorough** | 10-20s | 2-3min | All features | Deep analysis |


## 🛠️ Quick Start

### Prerequisites
- Python 3.8+
- MongoDB 4.0+ (must be running)
- Telegram Bot (for alerts)

### Installation

1. **Clone and setup**:
```bash
cd mexc
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

2. **Configure environment**:
```bash
cp .env.example .env
# Edit .env with your credentials
```

3. **Setup MongoDB** (if not running):
```bash
# Ubuntu/Debian
sudo apt-get install mongodb
sudo systemctl start mongod

# macOS
brew install mongodb-community
brew services start mongodb-community
```

4. **Setup Telegram** (optional but recommended):
- Create bot with [@BotFather](https://t.me/botfather)
- Get bot token
- Create channel and add bot as admin
- Add credentials to `.env`

### Run the Monitor

**🎯 Optimized Monitor** (Recommended):
```bash
cd src
# Startup mode for first run
python monitor_optimized.py --mode startup AIXBT_USDT USUAL_USDT XMR_USDT

# Fast mode for active trading
python monitor_optimized.py --mode fast AIXBT_USDT USUAL_USDT XMR_USDT

# From watchlist file
python monitor_optimized.py --mode fast --file ../watchlists/favorites.txt
```

**🎮 Easy Launcher**:
```bash
# Interactive mode selector
./monitor_3_pairs.py
```

## 📱 Telegram Alert Examples

### Action Alerts
```
🟢🚀 STRONG_BUY - SHIB_USDT
Confidence: 85%

💰 Price: $0.000014 📈 +2.5%
📊 Volume: 8.3x average
⚡ RSI: 24 (Oversold)

🎯 Signals Detected:
• Volume Explosion (90%)
• RSI Divergence (75%)

💡 Recommendation:
Strong bullish signals - Consider buying
⚠️ Set stop loss at -2%

⏰ 15:23:45 UTC
```

### Hourly Summary
```
📊 Hourly Market Summary
━━━━━━━━━━━━━━━━

📈 Activity:
• Pairs monitored: 100
• Total alerts: 15
• Strong signals: 3

🎯 Top Opportunities:
🟢 SHIB_USDT: Oversold bounce setup (80%)
🟢 LINK_USDT: Pump in progress (75%)
🔴 BTC_USDT: Overbought - watch for dump (70%)

🚀 Biggest Moves:
📈 DOGE_USDT: +5.2%
📉 SOL_USDT: -3.8%

⚠️ High Risk Pairs:
• BTC_USDT: Extremely overbought (RSI 87)
• ETH_USDT: Abnormal volume (12.5x)
```

## 📁 Project Structure

```
mexc/
├── src/
│   ├── monitor_optimized.py         # ⚡ OPTIMIZED monitor (2-3s)
│   ├── monitor_config.py            # Performance configuration
│   ├── data_fetcher.py              # MEXC API integration
│   ├── enhanced_data_fetcher.py     # Order book & trade analysis
│   ├── advanced_signals_v2.py       # V2 enhanced signals
│   ├── funding_analyzer.py          # Funding rate arbitrage
│   ├── liquidation_monitor.py       # Liquidation detection
│   ├── statistical_analyzer.py      # Z-score analysis
│   ├── alert_prioritizer.py         # Alert filtering
│   ├── telegram_notifier_v2.py      # Enhanced notifications
│   ├── database.py                  # MongoDB operations
│   └── analyze_patterns.py          # Historical analysis
├── monitor_3_pairs.py               # Easy launcher script
├── logs/                            # Application logs
├── .env.example                     # Environment template
├── requirements.txt                 # Python dependencies
└── README.md                        # This file
```

## 🗄️ MongoDB Schema

### market_data Collection
Stores 1-minute candles with volume analysis and technical indicators:
```javascript
{
  symbol: "BTC_USDT",
  timestamp: ISODate("2024-01-15T10:30:00Z"),
  ohlcv: { open, high, low, close, volume },
  volume_analysis: { spike_magnitude, is_spike },
  price_movement: { change_5m, change_60m },
  indicators: { rsi_14, momentum }
}
```

### alerts Collection
Stores detected manipulation events:
```javascript
{
  symbol: "DOGE_USDT",
  detected_at: ISODate("2024-01-15T10:35:00Z"),
  risk_level: "HIGH",
  patterns: { action, confidence, signals }
}
```

## ⚙️ Configuration

### Environment Variables (.env)
```
# MongoDB
MONGODB_URI=mongodb://localhost:27017/
DATABASE_NAME=mexc

# Telegram Bot
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_CHANNEL_ID=@your_channel_or_chat_id

# Optional
LOG_LEVEL=INFO
```

### Adjusting Detection Sensitivity

Edit thresholds in `multi_pair_monitor.py`:
- Volume spike threshold (default: 5x)
- RSI extremes (default: <20, >80)
- Price movement (default: 3%)
- Risk levels (HIGH: >50%, EXTREME: >70%)

## 📈 Pattern Analysis

Analyze historical data for insights:
```bash
python analyze_patterns.py
```

This will:
- Find successful pump patterns
- Analyze alert accuracy
- Identify optimal signal combinations
- Generate trading recommendations

## 🐛 Troubleshooting

### Performance Issues
- **Slow processing (>10s)**: Use `--mode fast` or reduce pairs
- **No alerts on first run**: Use `--mode startup` (lower thresholds)
- **API errors**: Normal, system handles gracefully

### No Alerts
- Use startup mode for sensitive detection: `--mode startup`
- Monitor volatile pairs (AIXBT, USUAL, XMR, etc.)
- Check logs/app.log for errors
- Verify Telegram configuration

### Common Solutions
```bash
# For first run (no history)
python monitor_optimized.py --mode startup AIXBT_USDT

# For maximum speed
python monitor_optimized.py --mode fast AIXBT_USDT

# Check what's happening
tail -f ../logs/app.log
```

## 📝 Notes

- **For 100 pairs**: Use fast mode (20-30s cycles)
- **For best signals**: Monitor 3-10 volatile pairs
- **First 24h**: Use startup mode for sensitive detection
- **System improves**: Better signals after building history
- **Alert cooldown**: 2-5 minutes per symbol
- **Auto-optimization**: Disables slow features if needed
- **All times in UTC**

## 📚 Technical Overview

### How It Works

```
MEXC API → Data Collection → Analysis → Signal Detection → Alert Filtering → Telegram
    ↑           ↓               ↓            ↓                ↓
    └─────── MongoDB ←──────────┴────────────┴────────────────┘
              (History)
```

Every 10 seconds, the system:
1. Fetches market data for each monitored pair
2. Analyzes multiple indicators and patterns
3. Detects potential manipulation signals
4. Filters alerts based on quality and performance
5. Sends actionable alerts to Telegram

### Signal Detection Algorithms

**Volume Explosion**: Detects when volume > 5x average with > 3% price movement
**RSI Divergence**: Bullish (price down, RSI up) or Bearish (price up, RSI down)
**Liquidation Squeeze**: High funding + heavy liquidations + overbought/oversold
**Funding Arbitrage**: Extreme funding rates creating arbitrage opportunities
**Statistical Significance**: Z-score > 3 standard deviations indicates unusual activity

### Alert Generation

Signals are weighted and combined:
- Volume Explosion: 20% weight
- RSI Divergence: 15% weight
- Momentum Shift: 15% weight
- Liquidation Squeeze: 15% weight
- Other signals: 5-10% each

Actions are determined by:
- STRONG_BUY/SELL: Confidence > 70% OR (3+ signals with avg > 60%)
- Priority adjusted by: Win rate, volume Z-score, freshness, recent performance

## ⚠️ Disclaimer

This tool is for educational purposes only. Cryptocurrency trading carries significant risk. Always do your own research and never invest more than you can afford to lose.