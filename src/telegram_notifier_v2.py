"""
Enhanced Telegram notifier with detailed trade setups and performance tracking
"""

import os
import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional
import aiohttp
from dotenv import load_dotenv

from statistical_analyzer import calculate_atr

load_dotenv('../.env')
logger = logging.getLogger(__name__)


class EnhancedTelegramNotifier:
    """Send detailed trading alerts with entry/exit setups"""
    
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
            logger.info(f"Enhanced Telegram notifier initialized")
    
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
    
    def format_enhanced_alert(self, alert_data: Dict) -> str:
        """Format enhanced alert with full trade setup"""
        symbol = alert_data['symbol']
        patterns = alert_data.get('patterns', {})
        action = patterns.get('action', 'WATCH')
        confidence = patterns.get('confidence', 0) * 100
        
        # Get market data
        snapshot = alert_data.get('snapshot', {})
        price = snapshot.get('price', 0)
        price_change = snapshot.get('price_change_5m', 0)
        volume_ratio = snapshot.get('volume_ratio', 0)
        rsi = snapshot.get('rsi', 50)
        
        # Determine emoji and action type
        if action == 'STRONG_BUY':
            emoji = '🟢🚀'
            action_text = 'STRONG BUY'
            position_type = 'LONG'
        elif action == 'BUY':
            emoji = '🟢'
            action_text = 'BUY'
            position_type = 'LONG'
        elif action == 'STRONG_SELL':
            emoji = '🔴💥'
            action_text = 'STRONG SELL'
            position_type = 'SHORT'
        elif action == 'SELL':
            emoji = '🔴'
            action_text = 'SELL'
            position_type = 'SHORT'
        elif action == 'FUNDING_SHORT':
            emoji = '💰🔴'
            action_text = 'FUNDING SHORT'
            position_type = 'SHORT'
        elif action == 'FUNDING_LONG':
            emoji = '💰🟢'
            action_text = 'FUNDING LONG'
            position_type = 'LONG'
        else:
            emoji = '👀'
            action_text = action
            position_type = 'NEUTRAL'
        
        # Calculate setup quality score
        setup_quality = self._calculate_setup_quality(alert_data)
        
        # Header
        message = f"<b>{emoji} {action_text} - {symbol}</b>\n"
        message += "═" * 35 + "\n\n"
        
        # Setup quality
        message += f"<b>📊 Setup Quality: {setup_quality}/100</b>\n"
        
        # Market snapshot
        message += f"├─ Price: ${price:.6f} ({price_change:+.2f}%)\n"
        
        # Volume analysis
        if volume_ratio > 1:
            if volume_ratio > 5:
                vol_emoji = "🔥"
            elif volume_ratio > 3:
                vol_emoji = "⚡"
            else:
                vol_emoji = "📈"
            message += f"├─ Volume: {vol_emoji} {volume_ratio:.1f}x average\n"
        
        # RSI
        if rsi:
            if rsi > 70:
                rsi_text = f"🔴 {rsi:.0f} (overbought)"
            elif rsi < 30:
                rsi_text = f"🟢 {rsi:.0f} (oversold)"
            else:
                rsi_text = f"{rsi:.0f}"
            message += f"├─ RSI(14): {rsi_text}\n"
        
        # Funding rate if available
        funding_data = alert_data.get('funding_data', {})
        if funding_data:
            funding_rate = funding_data.get('current_rate', 0)
            hours_to_funding = funding_data.get('hours_to_funding', 0)
            if abs(funding_rate) > 0.0001:
                message += f"└─ Funding: {funding_rate:.3%} ({hours_to_funding:.1f}h left)\n"
        
        # Confluence factors
        signals = patterns.get('signals', [])
        if signals:
            message += f"\n<b>🔍 Signals ({len(signals)}/{self._count_total_signals()} triggered):</b>\n"
            
            # Sort by confidence
            signals.sort(key=lambda x: x['confidence'], reverse=True)
            
            for i, signal in enumerate(signals[:5]):  # Top 5 signals
                if i == len(signals) - 1:
                    prefix = "└"
                else:
                    prefix = "├"
                
                # Add appropriate emoji for signal type
                signal_emoji = self._get_signal_emoji(signal['type'])
                message += f"{prefix} {signal_emoji} {signal['description']}\n"
        
        # Trade setup
        if position_type != 'NEUTRAL':
            trade_setup = self._calculate_trade_setup(price, position_type, alert_data)
            
            message += f"\n<b>📈 Trade Setup:</b>\n"
            message += f"• Entry: ${trade_setup['entry_min']:.6f}-${trade_setup['entry_max']:.6f}\n"
            message += f"• Stop Loss: ${trade_setup['stop_loss']:.6f} ({trade_setup['risk_pct']:.1f}% risk)\n"
            message += f"• Target 1: ${trade_setup['target_1']:.6f} ({trade_setup['reward_1']:.1f}% / {trade_setup['rr_1']:.1f}R)\n"
            message += f"• Target 2: ${trade_setup['target_2']:.6f} ({trade_setup['reward_2']:.1f}% / {trade_setup['rr_2']:.1f}R)\n"
            
            # Funding bonus if applicable
            if action.startswith('FUNDING') and funding_data:
                funding_bonus = abs(funding_rate) * (hours_to_funding / 8) * 100
                message += f"• Funding: +{funding_bonus:.2f}% if held {hours_to_funding:.1f}h\n"
        
        # Historical performance
        perf = alert_data.get('performance', {})
        if perf and perf.get('similar_setups_count', 0) > 0:
            message += f"\n<b>⚡ Historical Performance:</b>\n"
            message += f"Win Rate: {perf['win_rate']:.0f}% ({perf['wins']}/{perf['similar_setups_count']} trades)\n"
            message += f"Avg Return: {perf['avg_return']:+.1f}% per trade\n"
        
        # Liquidation warning if present
        liq_data = alert_data.get('liquidation_data', {})
        if liq_data and liq_data.get('cascade_probability', 0) > 0.6:
            message += f"\n<b>⚠️ Liquidation Risk:</b>\n"
            message += f"Cascade probability: {liq_data['cascade_probability']:.0%}\n"
            if liq_data.get('nearest_liquidation_zone'):
                message += f"Key level: ${liq_data['nearest_liquidation_zone']:.6f}\n"
        
        # Footer with timestamp and validity
        message += f"\n<b>⏰ Valid for: 5 minutes</b>\n"
        message += f"<i>{datetime.now(timezone.utc).strftime('%H:%M:%S UTC')}</i>"
        
        return message
    
    def _calculate_setup_quality(self, alert_data: Dict) -> int:
        """Calculate overall setup quality score (0-100)"""
        score = 50  # Base score
        
        patterns = alert_data.get('patterns', {})
        
        # Confidence factor (up to 30 points)
        confidence = patterns.get('confidence', 0.5)
        score += int(confidence * 30)
        
        # Number of signals (up to 20 points)
        num_signals = patterns.get('num_signals', 0)
        score += min(num_signals * 4, 20)
        
        # Statistical significance (up to 10 points)
        if alert_data.get('statistical_data', {}).get('is_outlier'):
            score += 10
        
        # Volume significance (up to 10 points)
        volume_ratio = alert_data.get('snapshot', {}).get('volume_ratio', 1)
        if volume_ratio > 5:
            score += 10
        elif volume_ratio > 3:
            score += 7
        elif volume_ratio > 2:
            score += 5
        
        # Funding opportunity (up to 10 points)
        if patterns.get('action', '').startswith('FUNDING'):
            funding_rate = abs(alert_data.get('funding_data', {}).get('current_rate', 0))
            if funding_rate > 0.002:
                score += 10
            elif funding_rate > 0.001:
                score += 7
        
        # Priority adjustment (up to 10 points)
        priority = alert_data.get('priority', 0.7)
        if priority > 1.0:
            score += 10
        elif priority > 0.9:
            score += 7
        elif priority > 0.8:
            score += 5
        
        # Historical performance (can add or subtract up to 10 points)
        perf = alert_data.get('performance', {})
        if perf:
            win_rate = perf.get('win_rate', 50)
            if win_rate > 70:
                score += 10
            elif win_rate > 60:
                score += 5
            elif win_rate < 30:
                score -= 10
            elif win_rate < 40:
                score -= 5
        
        return min(max(score, 0), 100)
    
    def _calculate_trade_setup(self, current_price: float, position_type: str, 
                             alert_data: Dict) -> Dict:
        """Calculate entry, stop loss, and targets"""
        # Get ATR if available (simplified calculation)
        recent_prices = []
        try:
            # Extract recent prices from any available data
            if 'candles' in alert_data:
                recent_prices = [c['close'] for c in alert_data['candles'][-20:]]
            else:
                recent_prices = [current_price]
        except:
            recent_prices = [current_price]
        
        # Calculate ATR or use default
        atr = calculate_atr(recent_prices) if len(recent_prices) > 14 else current_price * 0.01
        
        if position_type == 'LONG':
            # Entry zone
            entry_min = current_price
            entry_max = current_price * 1.002  # 0.2% above
            
            # Stop loss (1.5 ATR below entry)
            stop_loss = entry_min - (atr * 1.5)
            
            # Targets
            target_1 = entry_min + (atr * 2)  # 2 ATR
            target_2 = entry_min + (atr * 4)  # 4 ATR
            
        else:  # SHORT
            # Entry zone
            entry_max = current_price
            entry_min = current_price * 0.998  # 0.2% below
            
            # Stop loss (1.5 ATR above entry)
            stop_loss = entry_max + (atr * 1.5)
            
            # Targets
            target_1 = entry_max - (atr * 2)
            target_2 = entry_max - (atr * 4)
        
        # Calculate risk/reward
        risk = abs(stop_loss - entry_min)
        risk_pct = (risk / entry_min) * 100
        
        reward_1 = abs(target_1 - entry_min)
        reward_2 = abs(target_2 - entry_min)
        
        rr_1 = reward_1 / risk if risk > 0 else 0
        rr_2 = reward_2 / risk if risk > 0 else 0
        
        return {
            'entry_min': round(entry_min, 6),
            'entry_max': round(entry_max, 6),
            'stop_loss': round(stop_loss, 6),
            'target_1': round(target_1, 6),
            'target_2': round(target_2, 6),
            'risk_pct': round(risk_pct, 2),
            'reward_1': round((reward_1 / entry_min) * 100, 2),
            'reward_2': round((reward_2 / entry_min) * 100, 2),
            'rr_1': round(rr_1, 1),
            'rr_2': round(rr_2, 1)
        }
    
    def _get_signal_emoji(self, signal_type: str) -> str:
        """Get emoji for signal type"""
        emoji_map = {
            'volume_explosion': '💥',
            'rsi_divergence': '📊',
            'momentum_shift': '🚀',
            'liquidity_trap': '🪤',
            'accumulation': '📈',
            'liquidation_squeeze': '💀',
            'funding_arbitrage': '💰',
            'hidden_accumulation': '🤫',
            'timeframe_divergence': '⏱️'
        }
        return emoji_map.get(signal_type, '✅')
    
    def _count_total_signals(self) -> int:
        """Return total number of possible signals"""
        return 9  # Based on current implementation
    
    def format_summary_alert(self, summary_data: Dict) -> str:
        """Format hourly/daily summary"""
        hours = summary_data.get('hours', 1)
        
        message = f"<b>📊 {hours}H Summary Report</b>\n"
        message += "═" * 35 + "\n\n"
        
        message += f"<b>Overview:</b>\n"
        message += f"• Pairs monitored: {summary_data['total_pairs']}\n"
        message += f"• Alerts sent: {summary_data['total_alerts']}\n"
        message += f"• Strong signals: {summary_data['strong_signals']}\n"
        
        # Top opportunities
        if summary_data['top_opportunities']:
            message += f"\n<b>🎯 Top Opportunities:</b>\n"
            for i, opp in enumerate(summary_data['top_opportunities'][:3]):
                emoji = '🟢' if opp['type'] == 'buy' else '🔴'
                message += f"{i+1}. {emoji} {opp['symbol']} - {opp['action']}\n"
                message += f"   Confidence: {opp['confidence']}%\n"
        
        # Biggest movers
        if summary_data['biggest_movers']:
            message += f"\n<b>🔥 Biggest Movers:</b>\n"
            for mover in summary_data['biggest_movers'][:3]:
                emoji = '📈' if mover['change'] > 0 else '📉'
                message += f"{emoji} {mover['symbol']}: {mover['change']:+.2f}%\n"
        
        # High risk warnings
        if summary_data['high_risk_pairs']:
            message += f"\n<b>⚠️ Risk Warnings:</b>\n"
            for risk in summary_data['high_risk_pairs'][:3]:
                message += f"• {risk['symbol']}: {risk['reason']}\n"
        
        message += f"\n<i>Next summary in {hours} hour(s)</i>"
        
        return message


# Backward compatibility
TelegramNotifier = EnhancedTelegramNotifier