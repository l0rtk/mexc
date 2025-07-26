# MEXC Futures Manipulation Monitor

Advanced monitoring system for detecting manipulation patterns in MEXC futures markets using multi-signal analysis and real-time Telegram alerts.

## 🚀 Features

- **Multi-Pair Monitoring**: Track up to 100 futures pairs simultaneously
- **Advanced Signal Detection**: 
  - Volume explosion patterns (>5x average)
  - RSI divergence analysis
  - Momentum shift detection
  - Order book manipulation (spoofing, liquidity traps)
  - Accumulation/distribution phases
- **Real-Time Alerts**: Clear, actionable Telegram notifications
- **Comprehensive Logging**: Full audit trail with rotating logs
- **MongoDB Storage**: Historical data for pattern analysis

## 📊 Signal Detection

### Volume Explosion
Detects explosive volume (>5x average) with price confirmation, indicating potential pumps.

### RSI Divergence
Identifies price/momentum divergences for reversal opportunities:
- Bullish: Price down, RSI up (oversold bounce)
- Bearish: Price up, RSI down (overbought reversal)

### Momentum Shifts
Catches rapid acceleration patterns and V-shaped reversals.

### Order Book Analysis
- Spoofing detection
- Liquidity trap identification
- Spread analysis

### Accumulation/Distribution
Identifies smart money movements during accumulation and distribution phases.

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

```bash
cd src
python run_multi_monitor.py
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
│   ├── run_multi_monitor.py         # Main entry point
│   ├── multi_pair_monitor.py        # Core monitoring logic
│   ├── data_fetcher.py              # MEXC API integration
│   ├── enhanced_data_fetcher.py     # Order book & trade analysis
│   ├── advanced_signals.py          # Signal detection algorithms
│   ├── improved_telegram_notifier.py # Alert formatting
│   ├── database.py                  # MongoDB operations
│   ├── logging_config.py            # Logging setup
│   ├── analyze_patterns.py          # Historical analysis tool
│   └── setup_telegram.md            # Telegram setup guide
├── logs/                            # Application logs
├── .env.example                     # Environment template
├── requirements.txt                 # Python dependencies
├── CLAUDE.md                        # Assistant instructions
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

### No Alerts
- Markets may be stable - lower thresholds if needed
- Check Telegram configuration
- Verify MongoDB is running

### Rate Limiting
- System includes automatic delays
- Reduce pair count if seeing errors

### SSL/Connection Issues
- Normal during high load
- System handles gracefully

## 📝 Notes

- Monitor 50-100 pairs for best coverage
- Alerts have 5-minute cooldown per symbol
- Order book data is optional but improves accuracy
- All times in UTC

## ⚠️ Disclaimer

This tool is for educational purposes only. Cryptocurrency trading carries significant risk. Always do your own research and never invest more than you can afford to lose.