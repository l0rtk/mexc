# Setting Up Telegram Alerts

Follow these steps to enable Telegram notifications for the MEXC monitor:

## 1. Create a Telegram Bot

1. Open Telegram and search for `@BotFather`
2. Start a conversation and send `/newbot`
3. Choose a name for your bot (e.g., "MEXC Monitor Bot")
4. Choose a username for your bot (must end in `bot`, e.g., `mexc_monitor_bot`)
5. BotFather will give you a token like: `1234567890:ABCdefGHIjklMNOpqrsTUVwxyz`
6. Save this token - you'll need it for the `.env` file

## 2. Create a Channel or Group

### Option A: Public Channel (Recommended)
1. Create a new channel in Telegram
2. Make it public and choose a username (e.g., `@mexc_alerts`)
3. Add your bot as an administrator
4. Use `@mexc_alerts` as your `TELEGRAM_CHANNEL_ID`

### Option B: Private Group
1. Create a new group in Telegram
2. Add your bot to the group
3. Make the bot an administrator
4. Get the chat ID by:
   - Send a message in the group
   - Visit: `https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates`
   - Look for the chat ID (negative number like `-1001234567890`)
   - Use this ID as your `TELEGRAM_CHANNEL_ID`

## 3. Configure the Monitor

1. Copy `.env.example` to `.env`:
   ```bash
   cp .env.example .env
   ```

2. Edit `.env` and add your credentials:
   ```
   TELEGRAM_BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz
   TELEGRAM_CHANNEL_ID=@mexc_alerts
   ```

## 4. Test the Configuration

Run the test script to verify everything works:
```bash
cd src
python telegram_notifier.py
```

You should receive a test alert in your channel!

## 5. Start Monitoring

Run the multi-pair monitor:
```bash
python run_multi_monitor.py
```

## Alert Types

The monitor will send these types of alerts:

1. **Manipulation Alerts** (HIGH/EXTREME risk)
   - Pump detection
   - Wash trading
   - Spoofing
   - Stop hunts

2. **Extreme Conditions**
   - RSI oversold (<20) or overbought (>80)
   - Volume spikes (>5x average)
   - Rapid price movements with volume

3. **Hourly Summaries**
   - Top movers
   - Most active pairs
   - Alert statistics

## Customization

Edit `multi_pair_monitor.py` to adjust:
- Alert cooldown period (default: 5 minutes)
- Risk thresholds
- Update frequency
- Number of pairs to monitor