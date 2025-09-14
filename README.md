# MEXC Futures Monitoring System

Real-time monitoring system for detecting large orders and unusual trading activity on MEXC futures markets.

## Features

- **Large Order Detection**: Identifies orders exceeding configurable USDT thresholds
- **Order Book Analysis**: Detects buy/sell walls and imbalances
- **Trade Monitoring**: Tracks large market orders and whale activity
- **Volume Surge Detection**: Alerts on sudden volume increases
- **Coordinated Trading Detection**: Identifies potential coordinated trades
- **Spoofing Detection**: Monitors for potential order book manipulation
- **Real-time Alerts**: Console and Telegram notifications with priority levels

## Installation

```bash
# Clone the repository
cd mexc

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your credentials:
# - MEXC API keys (optional but recommended for better rate limits)
# - Telegram bot token and channel ID (for alerts)
```

## Usage

### Basic Usage

Monitor specific futures pairs:

```bash
python monitor.py BTC_USDT ETH_USDT
```

### Advanced Options

```bash
python monitor.py BTC_USDT ETH_USDT SOL_USDT \
  --min-order 100000 \
  --min-trade 50000 \
  --whale-threshold 250000 \
  --interval 3 \
  --log-alerts
```

### Command Line Arguments

- `symbols`: Space-separated list of symbols to monitor (e.g., BTC_USDT ETH_USDT)
- `--min-order`: Minimum order size to alert in USDT (default: 50000)
- `--min-trade`: Minimum trade size to track in USDT (default: 25000)
- `--whale-threshold`: Threshold for whale alerts in USDT (default: 100000)
- `--interval`: Update interval in seconds (default: 5)
- `--log-alerts`: Save alerts to file (alerts.log)
- `--no-telegram`: Disable Telegram notifications
- `--test-telegram`: Test Telegram connection and exit

## Alert Types

1. **Large Orders**: Orders exceeding minimum threshold
2. **Whale Orders**: Orders exceeding whale threshold (highlighted)
3. **Order Walls**: Large limit orders blocking price movement
4. **Volume Surges**: Sudden increases in trading volume
5. **Aggressive Trading**: Sustained buying or selling pressure
6. **Coordinated Trades**: Multiple trades at similar prices/times
7. **Spoofing Alerts**: Potential order book manipulation

## Configuration

### Environment Variables (.env)

```env
# Optional MEXC API credentials for better rate limits
MEXC_ACCESS_KEY=your_access_key
MEXC_SECRET_KEY=your_secret_key

# Telegram Bot Configuration (required for Telegram alerts)
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_CHANNEL_ID=@your_channel_or_chat_id
```

### Setting up Telegram Alerts

1. **Create a Telegram Bot**:
   - Message @BotFather on Telegram
   - Send `/newbot` and follow instructions
   - Copy the bot token

2. **Get Channel/Chat ID**:
   - Create a channel or group
   - Add your bot as admin
   - For channels: use @channelname
   - For groups: use the group ID (starts with -100)

3. **Test Connection**:
   ```bash
   python monitor.py --test-telegram
   ```

## Project Structure

```
mexc/
├── monitor.py              # Main monitoring script
├── requirements.txt        # Python dependencies
├── .env.example           # Environment configuration template
└── src/
    ├── mexc_client.py     # MEXC API client
    ├── order_monitor.py   # Order book analysis
    ├── trade_monitor.py   # Trade flow analysis
    └── alert_system.py    # Alert formatting and delivery
```

## Requirements

- Python 3.8+
- Internet connection
- MEXC API access (optional but recommended for better rate limits)

## Notes

- The system monitors futures contracts only (not spot markets)
- API rate limits apply (public endpoints: ~20 requests/second)
- Large order thresholds should be adjusted based on the liquidity of monitored pairs
- Lower timeframe monitoring (< 5 seconds) may hit rate limits with many symbols