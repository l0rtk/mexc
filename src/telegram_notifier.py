import os
import logging
import requests
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)


class TelegramNotifier:
    def __init__(self):
        self.bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
        self.channel_id = os.getenv('TELEGRAM_CHANNEL_ID')
        self.enabled = bool(self.bot_token and self.channel_id)

        if not self.enabled:
            logger.warning("Telegram notifications disabled - missing bot token or channel ID")
        else:
            logger.info(f"Telegram notifications enabled for channel: {self.channel_id}")

        self.base_url = f"https://api.telegram.org/bot{self.bot_token}"
        self.last_sent = {}
        self.rate_limit = 30  # Minimum seconds between similar alerts

    def send_message(self, message: str, parse_mode: str = "HTML") -> bool:
        """Send a message to Telegram"""
        if not self.enabled:
            return False

        try:
            url = f"{self.base_url}/sendMessage"
            payload = {
                'chat_id': self.channel_id,
                'text': message,
                'parse_mode': parse_mode,
                'disable_web_page_preview': True
            }

            response = requests.post(url, json=payload, timeout=10)

            if response.status_code == 200:
                return True
            else:
                logger.error(f"Telegram API error: {response.text}")
                return False

        except Exception as e:
            logger.error(f"Error sending Telegram message: {e}")
            return False

    def format_large_order_alert(self, order) -> str:
        """Format large order alert for Telegram"""
        emoji = "🐋" if order.is_whale else "📊"
        side_emoji = "🟢" if order.side == "BUY" else "🔴"

        message = f"<b>{emoji} LARGE {order.side} ORDER</b>\n\n"
        message += f"{side_emoji} <b>{order.symbol}</b>\n"
        message += f"💰 Price: ${order.price:,.2f}\n"
        message += f"📦 Volume: {order.volume:,.2f}\n"
        message += f"💵 Value: ${order.volume_usdt:,.2f}\n"
        message += f"📊 Book %: {order.percentage_of_book:.1f}%\n"
        message += f"⏰ {datetime.now().strftime('%H:%M:%S')}"

        return message

    def format_wall_alert(self, wall: Dict) -> str:
        """Format wall alert for Telegram"""
        wall_type = wall['type']
        emoji = "🟢" if 'BUY' in wall_type else "🔴"

        message = f"<b>🚧 {wall_type} DETECTED</b>\n\n"
        message += f"{emoji} <b>{wall['symbol']}</b>\n"
        message += f"💰 Price: ${wall['price']:,.2f}\n"
        message += f"📦 Volume: {wall['volume']:,.2f}\n"
        message += f"💵 Value: ${wall['volume_usdt']:,.2f}\n"
        message += f"📏 Size vs Avg: {wall['multiplier']:.1f}x\n"
        message += f"📍 Position: #{wall['position']}"

        return message

    def format_aggressive_trading_alert(self, data: Dict) -> str:
        """Format aggressive trading alert for Telegram"""
        emoji = "🟢" if data['dominant_side'] == 'BUY' else "🔴"

        message = f"<b>⚡ AGGRESSIVE {data['dominant_side']}</b>\n\n"
        message += f"{emoji} <b>{data['symbol']}</b>\n"
        message += f"🟢 Buy: ${data['buy_volume_usdt']:,.0f} ({data['buy_percentage']:.1f}%)\n"
        message += f"🔴 Sell: ${data['sell_volume_usdt']:,.0f} ({data['sell_percentage']:.1f}%)\n"
        message += f"🎯 Aggression: {data['aggression_score']:.1f}/50\n"
        message += f"⏱ Window: {data['time_window']}s"

        return message

    def format_volume_surge_alert(self, surge: Dict) -> str:
        """Format volume surge alert for Telegram"""
        message = f"<b>🚀 VOLUME SURGE</b>\n\n"
        message += f"<b>{surge['symbol']}</b>\n"
        message += f"📈 Current: ${surge['current_volume']:,.0f}\n"
        message += f"📊 Average: ${surge['average_volume']:,.0f}\n"
        message += f"🔥 Surge: {surge['surge_multiplier']:.1f}x normal\n"
        message += f"⏱ Baseline: {surge['baseline_minutes']} min"

        return message

    def format_coordinated_trades_alert(self, coordinated: Dict) -> str:
        """Format coordinated trades alert for Telegram"""
        emoji = "🟢" if coordinated['side'] == 'BUY' else "🔴"

        message = f"<b>🎯 COORDINATED {coordinated['side']}</b>\n\n"
        message += f"{emoji} <b>{coordinated['symbol']}</b>\n"
        message += f"🔢 Trades: {coordinated['trade_count']}\n"
        message += f"💵 Volume: ${coordinated['total_volume_usdt']:,.0f}\n"
        message += f"💰 Avg Price: ${coordinated['avg_price']:,.2f}\n"
        message += f"⏱ Time Span: {coordinated['time_span']}s"

        return message

    def format_spoofing_alert(self, spoof: Dict) -> str:
        """Format spoofing alert for Telegram"""
        emoji = "🟢" if spoof['side'] == 'BUY' else "🔴"

        message = f"<b>⚠️ POTENTIAL SPOOFING</b>\n\n"
        message += f"{emoji} <b>{spoof['side']} orders at ${spoof['price']:,.2f}</b>\n"
        message += f"👁 Appearances: {spoof['appearances']} times\n"
        message += f"💵 Avg Volume: ${spoof['avg_volume_usdt']:,.0f}\n"
        message += f"📊 Variation: ${spoof['volume_variation']:,.0f}"

        return message

    def should_send_alert(self, alert_type: str, symbol: str) -> bool:
        """Check if alert should be sent based on rate limiting"""
        key = f"{alert_type}:{symbol}"
        now = datetime.now()

        if key in self.last_sent:
            time_since = (now - self.last_sent[key]).total_seconds()
            if time_since < self.rate_limit:
                return False

        self.last_sent[key] = now
        return True

    def send_alert(self, alert_type: str, data: any, priority: str = "MEDIUM") -> bool:
        """Send alert to Telegram based on type"""
        if not self.enabled:
            return False

        # Check rate limiting
        symbol = ""
        if hasattr(data, 'symbol'):
            symbol = data.symbol
        elif isinstance(data, dict) and 'symbol' in data:
            symbol = data['symbol']

        if not self.should_send_alert(alert_type, symbol):
            logger.debug(f"Rate limited: {alert_type} for {symbol}")
            return False

        # Format message based on alert type
        try:
            if alert_type == "large_order":
                message = self.format_large_order_alert(data)
            elif alert_type == "wall":
                message = self.format_wall_alert(data)
            elif alert_type == "aggressive_trading":
                message = self.format_aggressive_trading_alert(data)
            elif alert_type == "volume_surge":
                message = self.format_volume_surge_alert(data)
            elif alert_type == "coordinated_trades":
                message = self.format_coordinated_trades_alert(data)
            elif alert_type == "spoofing":
                message = self.format_spoofing_alert(data)
            else:
                message = f"<b>📢 Alert: {alert_type}</b>\n\n{str(data)}"

            # Add priority tag
            if priority == "HIGH":
                message = "🔴 <b>HIGH PRIORITY</b>\n\n" + message
            elif priority == "LOW":
                message = "⚪ <i>Low Priority</i>\n\n" + message

            return self.send_message(message)

        except Exception as e:
            logger.error(f"Error formatting alert: {e}")
            return False

    def send_summary(self, alert_counts: Dict) -> bool:
        """Send daily summary to Telegram"""
        if not self.enabled or not alert_counts:
            return False

        total = sum(alert_counts.values())

        message = "<b>📊 24H ALERT SUMMARY</b>\n\n"
        message += f"Total Alerts: {total}\n\n"

        for alert_type, count in sorted(alert_counts.items(), key=lambda x: x[1], reverse=True):
            message += f"• {alert_type.replace('_', ' ').title()}: {count}\n"

        message += f"\n⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

        return self.send_message(message)

    def test_connection(self) -> bool:
        """Test Telegram bot connection"""
        if not self.enabled:
            print("❌ Telegram not configured")
            return False

        test_message = f"✅ MEXC Monitor Connected\n\n"
        test_message += f"Bot is ready to send alerts to {self.channel_id}\n"
        test_message += f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

        if self.send_message(test_message):
            print("✅ Telegram connection successful")
            return True
        else:
            print("❌ Failed to send test message")
            return False