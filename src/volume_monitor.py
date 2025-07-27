#!/usr/bin/env python3
"""
Volume Monitor - Dedicated buy/sell volume analysis with alerts
Monitors volume imbalances, sudden spikes, and accumulation/distribution patterns
"""

import sys
import os
import argparse
import asyncio
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple
from collections import deque
import numpy as np

# Add src to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from data_fetcher import SinglePairDataFetcher
from enhanced_data_fetcher import EnhancedDataFetcher
from database import MongoDBConnection
from telegram_notifier_v2 import EnhancedTelegramNotifier
from logging_config import get_logger
from dotenv import load_dotenv

# Load environment
load_dotenv('../.env')
logger = get_logger(__name__)


class VolumeAnalyzer:
    """Analyzes buy/sell volume patterns"""
    
    def __init__(self, symbol: str):
        self.symbol = symbol
        self.fetcher = SinglePairDataFetcher(symbol)
        self.enhanced_fetcher = EnhancedDataFetcher(symbol)
        
        # Volume tracking
        self.volume_history = deque(maxlen=100)  # Last 100 candles
        self.trade_history = deque(maxlen=1000)  # Last 1000 trades
        self.order_book_history = deque(maxlen=20)  # Last 20 order book snapshots
        
        # Thresholds
        self.min_volume_spike = 3.0  # 3x average volume
        self.min_imbalance_ratio = 2.0  # 2:1 buy/sell ratio
        self.min_trade_size_multiplier = 5.0  # 5x average trade size
        
    def analyze_candle_volume(self, candles: List[Dict]) -> Dict:
        """Analyze volume from candle data"""
        if len(candles) < 10:
            return {}
            
        # Extract volumes
        volumes = [float(c['volume']) for c in candles]
        timestamps = [c['timestamp'] for c in candles]
        
        # Calculate statistics
        current_vol = volumes[-1]
        avg_vol_20 = np.mean(volumes[-20:]) if len(volumes) >= 20 else np.mean(volumes)
        avg_vol_50 = np.mean(volumes[-50:]) if len(volumes) >= 50 else np.mean(volumes)
        
        # Volume spike detection
        volume_ratio_20 = current_vol / avg_vol_20 if avg_vol_20 > 0 else 0
        volume_ratio_50 = current_vol / avg_vol_50 if avg_vol_50 > 0 else 0
        
        # Volume trend (increasing/decreasing)
        recent_vols = volumes[-5:]
        older_vols = volumes[-10:-5] if len(volumes) >= 10 else volumes[:5]
        volume_trend = np.mean(recent_vols) / np.mean(older_vols) if np.mean(older_vols) > 0 else 1
        
        # Detect volume patterns
        is_spike = volume_ratio_20 >= self.min_volume_spike
        is_climax = volume_ratio_50 >= self.min_volume_spike * 1.5  # Even bigger spike
        is_drying_up = volume_ratio_20 < 0.3  # Very low volume
        
        return {
            'current_volume': current_vol,
            'avg_volume_20': avg_vol_20,
            'avg_volume_50': avg_vol_50,
            'volume_ratio_20': round(volume_ratio_20, 2),
            'volume_ratio_50': round(volume_ratio_50, 2),
            'volume_trend': round(volume_trend, 2),
            'is_spike': is_spike,
            'is_climax': is_climax,
            'is_drying_up': is_drying_up,
            'timestamp': timestamps[-1]
        }
    
    def analyze_trades(self, limit: int = 100) -> Dict:
        """Analyze recent trades for buy/sell pressure"""
        try:
            trades = self.enhanced_fetcher.fetch_recent_trades(limit=limit)
            if not trades:
                return {}
            
            # Separate buy/sell trades
            buy_trades = [t for t in trades if t.get('isBuyerMaker', False) == False]
            sell_trades = [t for t in trades if t.get('isBuyerMaker', False) == True]
            
            # Calculate volumes
            buy_volume = sum(float(t.get('qty', 0)) * float(t.get('price', 0)) for t in buy_trades)
            sell_volume = sum(float(t.get('qty', 0)) * float(t.get('price', 0)) for t in sell_trades)
            total_volume = buy_volume + sell_volume
            
            # Calculate counts
            buy_count = len(buy_trades)
            sell_count = len(sell_trades)
            
            # Buy/sell ratio
            buy_ratio = buy_volume / total_volume if total_volume > 0 else 0.5
            volume_imbalance = buy_volume / sell_volume if sell_volume > 0 else float('inf')
            
            # Large trade detection
            all_sizes = [float(t.get('qty', 0)) * float(t.get('price', 0)) for t in trades]
            avg_size = np.mean(all_sizes) if all_sizes else 0
            large_trades = [t for t in trades if float(t.get('qty', 0)) * float(t.get('price', 0)) > avg_size * self.min_trade_size_multiplier]
            
            # Analyze large trades
            large_buy_volume = sum(float(t.get('qty', 0)) * float(t.get('price', 0)) 
                                 for t in large_trades if t.get('isBuyerMaker', False) == False)
            large_sell_volume = sum(float(t.get('qty', 0)) * float(t.get('price', 0)) 
                                  for t in large_trades if t.get('isBuyerMaker', False) == True)
            
            return {
                'buy_volume': buy_volume,
                'sell_volume': sell_volume,
                'total_volume': total_volume,
                'buy_ratio': round(buy_ratio, 3),
                'volume_imbalance': round(volume_imbalance, 2),
                'buy_count': buy_count,
                'sell_count': sell_count,
                'large_trades_count': len(large_trades),
                'large_buy_volume': large_buy_volume,
                'large_sell_volume': large_sell_volume,
                'avg_trade_size': avg_size,
                'is_buying_pressure': volume_imbalance >= self.min_imbalance_ratio,
                'is_selling_pressure': volume_imbalance <= 1/self.min_imbalance_ratio,
                'has_whale_activity': len(large_trades) > 0
            }
            
        except Exception as e:
            logger.error(f"Error analyzing trades for {self.symbol}: {e}")
            return {}
    
    def analyze_order_book(self) -> Dict:
        """Analyze order book for volume imbalances"""
        try:
            order_book = self.enhanced_fetcher.fetch_order_book(depth=20)
            if not order_book or 'bids' not in order_book or 'asks' not in order_book:
                return {}
            
            bids = order_book['bids']
            asks = order_book['asks']
            
            # Calculate bid/ask volumes at different levels
            bid_volume_5 = sum(float(price) * float(qty) for price, qty in bids[:5])
            ask_volume_5 = sum(float(price) * float(qty) for price, qty in asks[:5])
            
            bid_volume_10 = sum(float(price) * float(qty) for price, qty in bids[:10])
            ask_volume_10 = sum(float(price) * float(qty) for price, qty in asks[:10])
            
            bid_volume_20 = sum(float(price) * float(qty) for price, qty in bids[:20])
            ask_volume_20 = sum(float(price) * float(qty) for price, qty in asks[:20])
            
            # Calculate imbalances
            imbalance_5 = bid_volume_5 / ask_volume_5 if ask_volume_5 > 0 else float('inf')
            imbalance_10 = bid_volume_10 / ask_volume_10 if ask_volume_10 > 0 else float('inf')
            imbalance_20 = bid_volume_20 / ask_volume_20 if ask_volume_20 > 0 else float('inf')
            
            # Detect walls
            bid_wall = max(bids[:5], key=lambda x: float(x[1])) if bids else None
            ask_wall = max(asks[:5], key=lambda x: float(x[1])) if asks else None
            
            # Calculate average order sizes
            avg_bid_size = np.mean([float(qty) for _, qty in bids[:10]]) if bids else 0
            avg_ask_size = np.mean([float(qty) for _, qty in asks[:10]]) if asks else 0
            
            return {
                'bid_volume_5': bid_volume_5,
                'ask_volume_5': ask_volume_5,
                'imbalance_5': round(imbalance_5, 2),
                'imbalance_10': round(imbalance_10, 2),
                'imbalance_20': round(imbalance_20, 2),
                'bid_wall': {'price': float(bid_wall[0]), 'size': float(bid_wall[1])} if bid_wall else None,
                'ask_wall': {'price': float(ask_wall[0]), 'size': float(ask_wall[1])} if ask_wall else None,
                'avg_bid_size': avg_bid_size,
                'avg_ask_size': avg_ask_size,
                'has_bid_support': imbalance_5 >= self.min_imbalance_ratio,
                'has_ask_pressure': imbalance_5 <= 1/self.min_imbalance_ratio
            }
            
        except Exception as e:
            logger.debug(f"Error analyzing order book for {self.symbol}: {e}")
            return {}
    
    def detect_volume_patterns(self, candle_analysis: Dict, trade_analysis: Dict, 
                             order_book_analysis: Dict, price_data: Dict) -> Dict:
        """Detect specific volume patterns and generate alerts"""
        patterns = []
        confidence = 0
        severity = "LOW"
        
        # 1. Volume Spike with Buying Pressure
        if (candle_analysis.get('is_spike') and 
            trade_analysis.get('is_buying_pressure')):
            patterns.append("VOLUME_SURGE_BUYING")
            confidence += 0.3
            severity = "HIGH"
            
        # 2. Volume Spike with Selling Pressure
        if (candle_analysis.get('is_spike') and 
            trade_analysis.get('is_selling_pressure')):
            patterns.append("VOLUME_SURGE_SELLING")
            confidence += 0.3
            severity = "HIGH"
            
        # 3. Climax Volume (extreme spike)
        if candle_analysis.get('is_climax'):
            patterns.append("CLIMAX_VOLUME")
            confidence += 0.4
            severity = "EXTREME"
            
        # 4. Whale Activity
        if (trade_analysis.get('has_whale_activity') and 
            trade_analysis.get('large_trades_count', 0) >= 3):
            patterns.append("WHALE_ACTIVITY")
            confidence += 0.3
            
            # Check whale direction
            if trade_analysis.get('large_buy_volume', 0) > trade_analysis.get('large_sell_volume', 0) * 2:
                patterns.append("WHALE_ACCUMULATION")
                severity = "HIGH"
            elif trade_analysis.get('large_sell_volume', 0) > trade_analysis.get('large_buy_volume', 0) * 2:
                patterns.append("WHALE_DISTRIBUTION")
                severity = "HIGH"
                
        # 5. Order Book Imbalance
        if order_book_analysis.get('has_bid_support'):
            patterns.append("STRONG_BID_SUPPORT")
            confidence += 0.2
        elif order_book_analysis.get('has_ask_pressure'):
            patterns.append("STRONG_ASK_PRESSURE")
            confidence += 0.2
            
        # 6. Volume Dry Up (very low volume)
        if candle_analysis.get('is_drying_up'):
            patterns.append("VOLUME_DRY_UP")
            confidence += 0.2
            severity = "MEDIUM"
            
        # 7. Hidden Accumulation/Distribution
        if (not candle_analysis.get('is_spike') and 
            trade_analysis.get('volume_imbalance', 1) > 3):
            patterns.append("HIDDEN_ACCUMULATION")
            confidence += 0.25
        elif (not candle_analysis.get('is_spike') and 
              trade_analysis.get('volume_imbalance', 1) < 0.33):
            patterns.append("HIDDEN_DISTRIBUTION")
            confidence += 0.25
            
        # Adjust confidence
        confidence = min(confidence, 1.0)
        
        # Determine action
        action = "MONITOR"
        if severity == "EXTREME" and confidence >= 0.6:
            action = "IMMEDIATE_ACTION"
        elif severity == "HIGH" and confidence >= 0.5:
            action = "PREPARE_POSITION"
        elif confidence >= 0.4:
            action = "WATCH_CLOSELY"
            
        return {
            'patterns': patterns,
            'confidence': round(confidence, 2),
            'severity': severity,
            'action': action,
            'timestamp': datetime.now(timezone.utc)
        }


class VolumeMonitor:
    """Main volume monitoring system"""
    
    def __init__(self, symbols: List[str], db_connection: MongoDBConnection, 
                 telegram_notifier: EnhancedTelegramNotifier):
        self.symbols = symbols
        self.db = db_connection
        self.telegram = telegram_notifier
        self.running = False
        
        # Create analyzers for each symbol
        self.analyzers = {symbol: VolumeAnalyzer(symbol) for symbol in symbols}
        
        # Alert tracking
        self.last_alert_time = {}
        self.alert_cooldown = timedelta(minutes=10)  # Longer cooldown for volume alerts
        
        # Stats
        self.stats = {
            'start_time': datetime.now(timezone.utc),
            'total_updates': 0,
            'total_alerts': 0,
            'patterns_detected': {}
        }
        
    async def analyze_symbol(self, symbol: str) -> Optional[Dict]:
        """Analyze volume for a single symbol"""
        try:
            analyzer = self.analyzers[symbol]
            
            # Fetch candle data
            candles = analyzer.fetcher.fetch_candles(limit=100)
            if not candles:
                return None
                
            # Get current price data
            current_candle = candles[-1]
            price_data = {
                'current_price': float(current_candle['close']),
                'price_change_1h': analyzer.fetcher.calculate_price_change(candles, 60),
                'price_change_5m': analyzer.fetcher.calculate_price_change(candles, 5)
            }
            
            # Analyze volume from different sources
            candle_analysis = analyzer.analyze_candle_volume(candles)
            trade_analysis = analyzer.analyze_trades()
            order_book_analysis = analyzer.analyze_order_book()
            
            # Detect patterns
            patterns = analyzer.detect_volume_patterns(
                candle_analysis, trade_analysis, order_book_analysis, price_data
            )
            
            # Store in database
            if patterns['patterns']:
                self.db.db.volume_monitoring.insert_one({
                    'symbol': symbol,
                    'timestamp': datetime.now(timezone.utc),
                    'candle_analysis': candle_analysis,
                    'trade_analysis': trade_analysis,
                    'order_book_analysis': order_book_analysis,
                    'price_data': price_data,
                    'patterns': patterns
                })
            
            # Check if alert needed
            if (patterns['action'] in ['IMMEDIATE_ACTION', 'PREPARE_POSITION'] and
                patterns['confidence'] >= 0.5):
                
                # Check cooldown
                last_alert = self.last_alert_time.get(symbol)
                if not last_alert or datetime.now(timezone.utc) - last_alert > self.alert_cooldown:
                    return {
                        'symbol': symbol,
                        'patterns': patterns,
                        'candle_analysis': candle_analysis,
                        'trade_analysis': trade_analysis,
                        'order_book_analysis': order_book_analysis,
                        'price_data': price_data
                    }
                    
            return None
            
        except Exception as e:
            logger.error(f"Error analyzing {symbol}: {e}")
            return None
    
    async def send_volume_alert(self, alert_data: Dict):
        """Send volume alert to Telegram"""
        symbol = alert_data['symbol']
        patterns = alert_data['patterns']
        candle_vol = alert_data['candle_analysis']
        trades = alert_data['trade_analysis']
        ob = alert_data['order_book_analysis']
        price = alert_data['price_data']
        
        # Build alert message
        message = f"<b>🔊 VOLUME ALERT - {symbol}</b>\n"
        message += f"<b>Severity: {patterns['severity']} | Confidence: {patterns['confidence']*100:.0f}%</b>\n\n"
        
        # Patterns detected
        message += "<b>Patterns Detected:</b>\n"
        for pattern in patterns['patterns']:
            emoji = {
                'VOLUME_SURGE_BUYING': '📈',
                'VOLUME_SURGE_SELLING': '📉',
                'CLIMAX_VOLUME': '🌋',
                'WHALE_ACTIVITY': '🐋',
                'WHALE_ACCUMULATION': '🐋📈',
                'WHALE_DISTRIBUTION': '🐋📉',
                'STRONG_BID_SUPPORT': '🛡️',
                'STRONG_ASK_PRESSURE': '⚔️',
                'VOLUME_DRY_UP': '🏜️',
                'HIDDEN_ACCUMULATION': '🤫📈',
                'HIDDEN_DISTRIBUTION': '🤫📉'
            }.get(pattern, '•')
            message += f"{emoji} {pattern.replace('_', ' ').title()}\n"
        
        message += "\n<b>Volume Analysis:</b>\n"
        message += f"• Current Vol: {candle_vol.get('volume_ratio_20', 0):.1f}x avg (20)\n"
        message += f"• Buy/Sell Ratio: {trades.get('volume_imbalance', 1):.2f}:1\n"
        message += f"• Buy Volume: ${trades.get('buy_volume', 0):,.0f}\n"
        message += f"• Sell Volume: ${trades.get('sell_volume', 0):,.0f}\n"
        
        if trades.get('has_whale_activity'):
            message += f"\n<b>🐋 Whale Activity:</b>\n"
            message += f"• Large Trades: {trades.get('large_trades_count', 0)}\n"
            message += f"• Whale Buy: ${trades.get('large_buy_volume', 0):,.0f}\n"
            message += f"• Whale Sell: ${trades.get('large_sell_volume', 0):,.0f}\n"
        
        if ob:
            message += f"\n<b>Order Book:</b>\n"
            message += f"• Bid/Ask Imbalance: {ob.get('imbalance_5', 1):.2f}:1\n"
            if ob.get('bid_wall'):
                message += f"• Bid Wall: {ob['bid_wall']['size']:,.0f} @ ${ob['bid_wall']['price']:.4f}\n"
            if ob.get('ask_wall'):
                message += f"• Ask Wall: {ob['ask_wall']['size']:,.0f} @ ${ob['ask_wall']['price']:.4f}\n"
        
        message += f"\n<b>Price:</b> ${price['current_price']:.6f}"
        message += f" ({price['price_change_5m']:+.2f}% 5m)\n"
        
        message += f"\n<b>Action: {patterns['action'].replace('_', ' ').title()}</b>"
        
        # Send alert
        success = await self.telegram.send_message(message)
        if success:
            self.last_alert_time[symbol] = datetime.now(timezone.utc)
            self.stats['total_alerts'] += 1
            logger.warning(f"Volume alert sent for {symbol}: {patterns['patterns']}")
    
    async def process_batch(self):
        """Process all symbols"""
        tasks = []
        for symbol in self.symbols:
            task = asyncio.create_task(self.analyze_symbol(symbol))
            tasks.append(task)
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process alerts
        alerts = [r for r in results if r and not isinstance(r, Exception)]
        
        # Send top alerts (limit to prevent spam)
        alerts.sort(key=lambda x: x['patterns']['confidence'], reverse=True)
        for alert in alerts[:3]:  # Max 3 alerts per cycle
            await self.send_volume_alert(alert)
            
        return len(alerts)
    
    def print_status(self):
        """Print current status"""
        runtime = (datetime.now(timezone.utc) - self.stats['start_time']).total_seconds()
        print(f"\r[{datetime.now().strftime('%H:%M:%S')}] "
              f"Volume Monitor | Updates: {self.stats['total_updates']} | "
              f"Alerts: {self.stats['total_alerts']} | "
              f"Runtime: {int(runtime)}s", end='', flush=True)
    
    async def run(self):
        """Main monitoring loop"""
        self.running = True
        
        logger.info(f"Starting Volume Monitor for {len(self.symbols)} symbols")
        
        # Send startup message
        startup_msg = f"<b>🔊 Volume Monitor Started</b>\n\n"
        startup_msg += f"Monitoring: {len(self.symbols)} symbols\n"
        startup_msg += f"Focus: Buy/Sell volume imbalances\n"
        startup_msg += f"Update interval: 30 seconds\n"
        startup_msg += f"Alert cooldown: 10 minutes per symbol"
        
        await self.telegram.send_message(startup_msg)
        
        while self.running:
            try:
                self.stats['total_updates'] += 1
                
                # Process all symbols
                alert_count = await self.process_batch()
                
                # Print status
                self.print_status()
                
                # Sleep
                await asyncio.sleep(30)  # 30 second updates
                
            except KeyboardInterrupt:
                break
            except Exception as e:
                logger.error(f"Monitor error: {e}", exc_info=True)
                await asyncio.sleep(60)
        
        logger.info("Volume Monitor stopped")


async def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description='MEXC Volume Monitor - Buy/Sell Volume Analysis',
        epilog="""
This monitor focuses exclusively on volume analysis:
- Volume spikes and climax patterns
- Buy/sell volume imbalances
- Whale activity detection
- Order book volume analysis
- Hidden accumulation/distribution

Examples:
  # Monitor specific symbols
  python volume_monitor.py AIXBT_USDT FIS_USDT ZORA_USDT
  
  # Monitor from file
  python volume_monitor.py --file watchlist.txt
        """
    )
    
    parser.add_argument('symbols', nargs='*', help='Symbols to monitor')
    parser.add_argument('--file', '-f', help='Load symbols from file')
    
    args = parser.parse_args()
    
    # Get symbols
    symbols = []
    if args.symbols:
        symbols.extend(args.symbols)
    
    if args.file:
        try:
            with open(args.file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        symbol = line.split('#')[0].strip()
                        if symbol:
                            symbols.append(symbol)
        except Exception as e:
            print(f"Error loading file: {e}")
            return
    
    if not symbols:
        # Default to some interesting symbols
        symbols = ['AIXBT_USDT', 'FIS_USDT', 'ZORA_USDT', 'SUPRA_USDT', 'USUAL_USDT']
    
    # Validate symbols
    valid_symbols = []
    for s in symbols:
        s = s.upper().strip()
        if not s.endswith('_USDT'):
            s += '_USDT'
        valid_symbols.append(s)
    
    print(f"\nStarting Volume Monitor for {len(valid_symbols)} symbols")
    print("=" * 60)
    
    # Setup
    db = MongoDBConnection()
    if not db.connect():
        print("Database connection failed")
        return
    
    telegram = EnhancedTelegramNotifier()
    await telegram.initialize()
    
    # Create and run monitor
    monitor = VolumeMonitor(valid_symbols, db, telegram)
    
    try:
        await monitor.run()
    finally:
        await telegram.close()
        db.disconnect()


if __name__ == "__main__":
    asyncio.run(main())