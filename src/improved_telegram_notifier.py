"""
Improved Telegram notifier with clear, actionable alerts
"""

import os
import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional
import aiohttp
from dotenv import load_dotenv

load_dotenv('../.env')
logger = logging.getLogger(__name__)


class ImprovedTelegramNotifier:
    """Send clear, actionable alerts to Telegram"""
    
    def __init__(self, bot_token: str = None, channel_id: str = None):
        self.bot_token = bot_token or os.getenv('TELEGRAM_BOT_TOKEN')
        self.channel_id = channel_id or os.getenv('TELEGRAM_CHANNEL_ID')
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}"
        self.session = None
        
        if not self.bot_token or not self.channel_id:
            logger.warning("Telegram credentials not provided. Notifications disabled.")
            self.enabled = False
        else:
            self.enabled = True
            logger.info(f"Telegram notifier initialized for channel: {self.channel_id}")
    
    async def initialize(self):
        """Initialize aiohttp session"""
        if self.enabled and not self.session:
            self.session = aiohttp.ClientSession()
    
    async def close(self):
        """Close aiohttp session"""
        if self.session:
            await self.session.close()
    
    async def send_message(self, text: str, parse_mode: str = "HTML") -> bool:
        """Send a message to Telegram channel"""
        if not self.enabled:
            logger.debug("Telegram disabled, skipping notification")
            return False
        
        if not self.session:
            await self.initialize()
        
        url = f"{self.base_url}/sendMessage"
        data = {
            "chat_id": self.channel_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True
        }
        
        try:
            async with self.session.post(url, json=data) as response:
                result = await response.json()
                if result.get("ok"):
                    logger.info("Telegram message sent successfully")
                    return True
                else:
                    logger.error(f"Telegram API error: {result}")
                    return False
        except Exception as e:
            logger.error(f"Error sending Telegram message: {e}")
            return False
    
    def format_advanced_alert(self, symbol: str, signal_data: Dict) -> str:
        """Format advanced signal alert with clear action"""
        action = signal_data.get('action', 'WATCH')
        confidence = signal_data.get('confidence', 0) * 100
        
        # Emoji based on action
        action_emojis = {
            'STRONG_BUY': '🟢🚀',
            'BUY': '🟢',
            'STRONG_SELL': '🔴💥',
            'SELL': '🔴',
            'WATCH': '👀',
            'NEUTRAL': '😴'
        }
        
        emoji = action_emojis.get(action, '❓')
        
        # Start with clear action
        message = f"<b>{emoji} {action} - {symbol}</b>\n"
        message += f"<b>Confidence:</b> {confidence:.0f}%\n\n"
        
        # Market snapshot
        context = signal_data.get('market_context', {})
        price = context.get('price', 0)
        price_change = context.get('price_change_5m', 0)
        volume_ratio = context.get('volume_ratio', 0)
        rsi = context.get('rsi')
        
        message += f"💰 <b>Price:</b> ${price:.6f}"
        if price_change != 0:
            change_emoji = '📈' if price_change > 0 else '📉'
            message += f" {change_emoji} {price_change:+.1f}%"
        message += "\n"
        
        # Key indicators
        if volume_ratio > 2:
            message += f"📊 <b>Volume:</b> {volume_ratio:.1f}x average\n"
        if rsi:
            if rsi < 30:
                message += f"⚡ <b>RSI:</b> {rsi:.0f} (Oversold)\n"
            elif rsi > 70:
                message += f"🔥 <b>RSI:</b> {rsi:.0f} (Overbought)\n"
        
        # Active signals (simplified)
        active_signals = signal_data.get('signals', [])
        if active_signals:
            message += "\n<b>🎯 Signals Detected:</b>\n"
            for signal in active_signals[:3]:  # Top 3
                signal_type = signal['type'].replace('_', ' ').title()
                confidence = signal['confidence'] * 100
                message += f"• {signal_type} ({confidence:.0f}%)\n"
        
        # Action recommendation
        message += "\n<b>💡 Recommendation:</b>\n"
        if action == 'STRONG_BUY':
            message += "Strong bullish signals - Consider buying\n"
            message += "⚠️ Set stop loss at -2%"
        elif action == 'BUY':
            message += "Bullish signals detected - Watch for entry\n"
            message += "⚠️ Wait for confirmation"
        elif action == 'STRONG_SELL':
            message += "Strong bearish signals - Consider selling\n"
            message += "⚠️ Exit longs immediately"
        elif action == 'SELL':
            message += "Bearish signals detected - Be cautious\n"
            message += "⚠️ Reduce position size"
        else:
            message += "Monitor closely - No clear direction"
        
        # Timestamp
        message += f"\n\n⏰ {datetime.now(timezone.utc).strftime('%H:%M:%S UTC')}"
        
        return message
    
    def format_simple_alert(self, symbol: str, alert_type: str, data: Dict) -> str:
        """Format simple, focused alerts"""
        if alert_type == "pump_starting":
            return f"""<b>🚀 PUMP STARTING - {symbol}</b>

💰 Price: ${data['price']:.6f} 📈 +{data['price_change']:.1f}%
📊 Volume: {data['volume_ratio']:.1f}x spike!

<b>Action:</b> Consider buying with tight stop loss
<b>Target:</b> +3-5% 
<b>Stop Loss:</b> -2%

⏰ {datetime.now(timezone.utc).strftime('%H:%M UTC')}"""
        
        elif alert_type == "dump_warning":
            return f"""<b>🔴 DUMP WARNING - {symbol}</b>

💰 Price: ${data['price']:.6f} 📉 {data['price_change']:.1f}%
🔥 RSI: {data['rsi']:.0f} (Overbought)

<b>Action:</b> Exit longs / Consider short
<b>Risk:</b> High dump probability

⏰ {datetime.now(timezone.utc).strftime('%H:%M UTC')}"""
        
        elif alert_type == "reversal_setup":
            direction = "Bullish" if data.get('bullish') else "Bearish"
            emoji = "🟢" if data.get('bullish') else "🔴"
            
            return f"""<b>{emoji} {direction.upper()} REVERSAL - {symbol}</b>

💰 Price: ${data['price']:.6f}
⚡ RSI: {data['rsi']:.0f} ({data.get('rsi_status', '')})
📊 Volume: {data.get('volume_ratio', 1):.1f}x

<b>Pattern:</b> {data.get('pattern', 'Reversal setup')}
<b>Action:</b> {data.get('action', 'Watch for confirmation')}

⏰ {datetime.now(timezone.utc).strftime('%H:%M UTC')}"""
        
        return ""
    
    def format_hourly_summary(self, summary_data: Dict) -> str:
        """Format clear hourly summary"""
        message = "<b>📊 Hourly Market Summary</b>\n"
        message += "━━━━━━━━━━━━━━━━\n\n"
        
        # Performance stats
        total_alerts = summary_data.get('total_alerts', 0)
        strong_signals = summary_data.get('strong_signals', 0)
        
        message += f"<b>📈 Activity:</b>\n"
        message += f"• Pairs monitored: {summary_data.get('total_pairs', 0)}\n"
        message += f"• Total alerts: {total_alerts}\n"
        message += f"• Strong signals: {strong_signals}\n\n"
        
        # Top opportunities
        if summary_data.get('top_opportunities'):
            message += "<b>🎯 Top Opportunities:</b>\n"
            for opp in summary_data['top_opportunities'][:5]:
                emoji = '🟢' if opp['type'] == 'buy' else '🔴'
                message += f"{emoji} {opp['symbol']}: {opp['action']} ({opp['confidence']:.0f}%)\n"
            message += "\n"
        
        # Market movers
        if summary_data.get('biggest_movers'):
            message += "<b>🚀 Biggest Moves:</b>\n"
            for mover in summary_data['biggest_movers'][:5]:
                emoji = '📈' if mover['change'] > 0 else '📉'
                message += f"{emoji} {mover['symbol']}: {mover['change']:+.1f}%\n"
        
        # Risk alerts
        if summary_data.get('high_risk_pairs'):
            message += "\n<b>⚠️ High Risk Pairs:</b>\n"
            for pair in summary_data['high_risk_pairs'][:3]:
                message += f"• {pair['symbol']}: {pair['reason']}\n"
        
        return message


# Update the main notifier to use improved formatting
class TelegramNotifier(ImprovedTelegramNotifier):
    """Backward compatible class"""
    
    def format_manipulation_alert(self, symbol: str, alert_data: Dict) -> str:
        """Convert old format to new advanced alert format"""
        # Build signal data in new format
        signal_data = {
            'action': self._determine_action(alert_data),
            'confidence': alert_data.get('patterns', {}).get('pump_probability', 0.5),
            'market_context': alert_data.get('snapshot', {}),
            'signals': []
        }
        
        # Convert patterns to signals
        patterns = alert_data.get('patterns', {})
        if patterns.get('pump_probability', 0) > 0.5:
            signal_data['signals'].append({
                'type': 'pump_signal',
                'confidence': patterns['pump_probability']
            })
        if patterns.get('dump_risk', 0) > 0.5:
            signal_data['signals'].append({
                'type': 'dump_risk',
                'confidence': patterns['dump_risk']
            })
        
        return self.format_advanced_alert(symbol, signal_data)
    
    def _determine_action(self, alert_data: Dict) -> str:
        """Determine action from alert data"""
        patterns = alert_data.get('patterns', {})
        pump_prob = patterns.get('pump_probability', 0)
        dump_risk = patterns.get('dump_risk', 0)
        
        if pump_prob > 0.7:
            return 'STRONG_BUY'
        elif pump_prob > 0.5:
            return 'BUY'
        elif dump_risk > 0.7:
            return 'STRONG_SELL'
        elif dump_risk > 0.5:
            return 'SELL'
        else:
            return 'WATCH'
    
    def format_extreme_alert(self, symbol: str, alert_type: str, data: Dict) -> str:
        """Convert extreme alerts to simple format"""
        if alert_type == 'volume_spike' and data.get('volume_ratio', 0) > 5:
            return self.format_simple_alert(symbol, 'pump_starting', data)
        elif alert_type == 'rsi_extreme':
            if data.get('rsi', 50) > 70:
                return self.format_simple_alert(symbol, 'dump_warning', data)
            else:
                data['bullish'] = True
                data['rsi_status'] = 'Oversold'
                data['pattern'] = 'Oversold bounce setup'
                data['action'] = 'Watch for reversal confirmation'
                return self.format_simple_alert(symbol, 'reversal_setup', data)
        elif alert_type == 'pump_detected':
            return self.format_simple_alert(symbol, 'pump_starting', data)
        
        # Fallback to basic format
        return f"<b>⚡ {alert_type.upper()} - {symbol}</b>\n{str(data)}"