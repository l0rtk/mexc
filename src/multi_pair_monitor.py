import asyncio
import logging
import signal
import sys
import os
import json
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Set
import time
from concurrent.futures import ThreadPoolExecutor
from collections import defaultdict

from data_fetcher import SinglePairDataFetcher
from enhanced_data_fetcher import EnhancedDataFetcher
from database import MongoDBConnection
from improved_telegram_notifier import TelegramNotifier
from logging_config import get_logger
from dotenv import load_dotenv
from advanced_signals import enhance_alert_detection

# Load environment variables
load_dotenv('../.env')

# Configure logging
logger = get_logger(__name__)


class MultiPairMonitor:
    """Monitor multiple trading pairs simultaneously with Telegram alerts"""
    
    def __init__(self, symbols: List[str], db_connection: MongoDBConnection, telegram_notifier: TelegramNotifier):
        self.symbols = symbols
        self.db = db_connection
        self.telegram = telegram_notifier
        self.running = False
        
        # Create fetchers for each symbol
        self.fetchers = {}
        self.enhanced_fetchers = {}
        for symbol in symbols:
            self.fetchers[symbol] = SinglePairDataFetcher(symbol)
            self.enhanced_fetchers[symbol] = EnhancedDataFetcher(symbol)
        
        # Tracking
        self.stats = {
            'start_time': datetime.now(timezone.utc),
            'total_updates': 0,
            'alerts_by_symbol': defaultdict(int),
            'last_alert_time': {},
            'total_alerts_sent': 0
        }
        
        # Alert cooldown to prevent spam (5 minutes per symbol)
        self.alert_cooldown = timedelta(minutes=5)
        
        # Thread pool for concurrent processing
        self.executor = ThreadPoolExecutor(max_workers=min(10, len(symbols)))
        
        # Track market conditions
        self.market_conditions = {}
        
    def should_send_alert(self, symbol: str, risk_level: str) -> bool:
        """Check if we should send an alert based on cooldown and risk level"""
        # Always send EXTREME alerts
        if risk_level == 'EXTREME':
            return True
        
        # Check cooldown for other alerts
        last_alert = self.stats['last_alert_time'].get(symbol)
        if last_alert:
            if datetime.now(timezone.utc) - last_alert < self.alert_cooldown:
                return False
        
        # Only send HIGH alerts after cooldown
        return risk_level == 'HIGH'
    
    async def process_symbol(self, symbol: str) -> Optional[Dict]:
        """Process a single symbol and return alert data if needed"""
        try:
            # Fetch data
            candles = self.fetchers[symbol].fetch_candles(limit=60)
            if not candles:
                return None
            
            # Basic analysis
            analysis = self.fetchers[symbol].analyze_candle_data(candles)
            
            # Add delay to avoid rate limiting when fetching order books
            await asyncio.sleep(0.2)  # Increased from 0.1
            
            # Try to get order book (optional)
            order_book = {}
            try:
                order_book = self.enhanced_fetchers[symbol].fetch_order_book(depth=10)
            except Exception as e:
                logger.debug(f"Order book fetch failed for {symbol}: {e}")
            
            # Store market data
            market_record = {
                'symbol': symbol,
                'timestamp': analysis['timestamp'],
                'monitoring_session': self.stats['start_time'],
                'ohlcv': analysis['ohlcv'],
                'volume_analysis': analysis['volume_analysis'],
                'price_movement': analysis['price_movement'],
                'indicators': analysis['indicators'],
                'order_book_summary': {
                    'spread_bps': order_book.get('spread_bps'),
                    'liquidity_score': order_book.get('liquidity_score'),
                    'spoofing_score': order_book.get('spoofing_score')
                } if order_book else None
            }
            
            # Check for duplicates
            if not self.db.check_duplicate_candle(symbol, analysis['timestamp']):
                self.db.db.multi_pair_monitoring.insert_one(market_record)
            
            # Update market conditions
            self.market_conditions[symbol] = {
                'price': analysis['ohlcv']['close'],
                'change_5m': analysis['price_movement']['change_5m'],
                'volume_ratio': analysis['volume_analysis']['volume_ratio_5m'],
                'rsi': analysis['indicators'].get('rsi_14'),
                'is_spike': analysis['volume_analysis']['is_spike'],
                'last_update': datetime.now(timezone.utc)
            }
            
            # Check for alerts
            alerts = self._check_alert_conditions(symbol, analysis, order_book)
            
            return alerts
            
        except Exception as e:
            logger.error(f"Error processing {symbol}: {e}")
            return None
    
    def _check_alert_conditions(self, symbol: str, analysis: Dict, order_book: Dict) -> Optional[Dict]:
        """Check for alert conditions using both basic and advanced signals"""
        
        # First, use advanced signal detection
        advanced_signal = enhance_alert_detection(analysis, order_book)
        
        # If advanced signals trigger with high confidence
        if advanced_signal['risk_level'] in ['HIGH', 'EXTREME']:
            return {
                'symbol': symbol,
                'timestamp': datetime.now(timezone.utc),
                'risk_level': advanced_signal['risk_level'],
                'alerts': advanced_signal['signals'],
                'snapshot': {
                    'price': analysis['ohlcv']['close'],
                    'price_change_5m': analysis['price_movement']['change_5m'],
                    'volume_ratio': analysis['volume_analysis']['spike_magnitude'],
                    'rsi': analysis['indicators'].get('rsi_14'),
                    'spread_bps': order_book.get('spread_bps') if order_book else None
                },
                'patterns': {
                    'action': advanced_signal['action'],
                    'confidence': advanced_signal['confidence'],
                    'num_signals': advanced_signal['num_signals'],
                    'description': advanced_signal['description'],
                    'signals': advanced_signal['signals']
                }
            }
        
        # Fallback to original alert logic for basic patterns
    def _check_alert_conditions_original(self, symbol: str, analysis: Dict, order_book: Dict) -> Optional[Dict]:
        """Check for alert conditions and return alert data"""
        alerts = []
        
        # 1. Volume spike alert
        if analysis['volume_analysis']['is_spike']:
            spike_magnitude = analysis['volume_analysis']['spike_magnitude']
            if spike_magnitude > 5:  # Restored original threshold
                alerts.append({
                    'type': 'volume_spike',
                    'severity': 'HIGH',
                    'data': {
                        'volume_ratio': spike_magnitude,
                        'price': analysis['ohlcv']['close'],
                        'price_change': analysis['price_movement']['change_5m']
                    }
                })
        
        # 2. RSI extreme alert
        rsi = analysis['indicators'].get('rsi_14')
        if rsi:
            if rsi < 20:  # Restored original threshold
                alerts.append({
                    'type': 'rsi_extreme',
                    'severity': 'HIGH',
                    'data': {'rsi': rsi}
                })
            elif rsi > 80:  # Restored original threshold
                alerts.append({
                    'type': 'rsi_extreme',
                    'severity': 'HIGH',
                    'data': {'rsi': rsi}
                })
            elif rsi < 30:
                alerts.append({
                    'type': 'rsi_extreme',
                    'severity': 'MEDIUM',
                    'data': {'rsi': rsi}
                })
            elif rsi > 70:
                alerts.append({
                    'type': 'rsi_extreme',
                    'severity': 'MEDIUM',
                    'data': {'rsi': rsi}
                })
        
        # 3. Pump detection
        if (analysis['volume_analysis']['spike_magnitude'] > 3 and
            analysis['price_movement']['change_5m'] > 3):
            alerts.append({
                'type': 'pump_detected',
                'severity': 'EXTREME',
                'data': {
                    'price_change': analysis['price_movement']['change_5m'],
                    'volume_ratio': analysis['volume_analysis']['spike_magnitude'],
                    'price': analysis['ohlcv']['close']
                }
            })
        
        # 4. Manipulation patterns (simplified)
        risk_level = 'LOW'
        pump_probability = 0
        dump_risk = 0
        
        if analysis['volume_analysis']['spike_magnitude'] > 3:
            pump_probability += 0.3
        if rsi and rsi > 70:
            dump_risk += 0.3
        if rsi and rsi < 30:
            pump_probability += 0.2
        
        if order_book:
            if order_book.get('spoofing_score', 0) > 0.5:
                pump_probability += 0.2
            if order_book.get('liquidity_score', 1) < 0.5:
                dump_risk += 0.2
        
        # Determine risk level
        max_risk = max(pump_probability, dump_risk)
        if max_risk > 0.7:
            risk_level = 'EXTREME'
        elif max_risk > 0.5:
            risk_level = 'HIGH'
        elif max_risk > 0.3:
            risk_level = 'MEDIUM'
        
        # Create comprehensive alert if needed
        if risk_level in ['HIGH', 'EXTREME'] or alerts:
            return {
                'symbol': symbol,
                'timestamp': datetime.now(timezone.utc),
                'risk_level': risk_level,
                'alerts': alerts,
                'snapshot': {
                    'price': analysis['ohlcv']['close'],
                    'price_change_5m': analysis['price_movement']['change_5m'],
                    'volume_ratio': analysis['volume_analysis']['spike_magnitude'],
                    'rsi': rsi,
                    'spread_bps': order_book.get('spread_bps') if order_book else None
                },
                'patterns': {
                    'pump_probability': pump_probability,
                    'dump_risk': dump_risk,
                    'wash_trading_detected': False,  # Simplified
                    'spoofing_detected': order_book.get('spoofing_score', 0) > 0.5 if order_book else False,
                    'signals': [alert for alert in alerts]
                }
            }
        
        return None
    
    async def send_telegram_alert(self, alert_data: Dict):
        """Send alert to Telegram"""
        symbol = alert_data['symbol']
        
        # Check if we should send this alert
        if not self.should_send_alert(symbol, alert_data['risk_level']):
            logger.debug(f"Skipping alert for {symbol} due to cooldown")
            return
        
        # For advanced signal alerts, send the formatted message
        if 'patterns' in alert_data and 'action' in alert_data['patterns']:
            # Build signal data for advanced formatting
            signal_data = {
                'action': alert_data['patterns']['action'],
                'confidence': alert_data['patterns']['confidence'],
                'market_context': alert_data['snapshot'],
                'signals': alert_data['patterns']['signals']
            }
            
            message = self.telegram.format_advanced_alert(symbol, signal_data)
            await self.telegram.send_message(message)
        else:
            # Fallback for basic alerts
            # Only send one consolidated message per symbol
            if alert_data['risk_level'] in ['HIGH', 'EXTREME']:
                message = self.telegram.format_manipulation_alert(symbol, alert_data)
                await self.telegram.send_message(message)
        
        # Update stats
        self.stats['last_alert_time'][symbol] = datetime.now(timezone.utc)
        self.stats['alerts_by_symbol'][symbol] += 1
        self.stats['total_alerts_sent'] += 1
        
        # Log alert
        logger.warning(f"Telegram alert sent for {symbol}: {alert_data['risk_level']} risk")
    
    async def process_all_symbols(self):
        """Process all symbols concurrently"""
        # Process all symbols in parallel with proper async
        tasks = []
        for symbol in self.symbols:
            task = self.process_symbol(symbol)
            tasks.append(task)
        
        # Wait for all to complete
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results and send alerts
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Error processing {self.symbols[i]}: {result}")
            elif result:  # Alert data returned
                await self.send_telegram_alert(result)
    
    def print_summary(self):
        """Print monitoring summary to console"""
        os.system('clear' if os.name == 'posix' else 'cls')
        
        print(f"\n{'='*80}")
        print(f"MULTI-PAIR MONITOR - {len(self.symbols)} SYMBOLS")
        print(f"{'='*80}")
        print(f"Running for: {(datetime.now(timezone.utc) - self.stats['start_time']).seconds // 60} minutes")
        print(f"Total updates: {self.stats['total_updates']}")
        print(f"Alerts sent: {self.stats['total_alerts_sent']}")
        
        print(f"\n{'Symbol':<15} {'Price':>10} {'5m Change':>10} {'Volume':>10} {'RSI':>8} {'Status':<20}")
        print("-" * 80)
        
        for symbol, condition in sorted(self.market_conditions.items()):
            price = condition.get('price', 0)
            change = condition.get('change_5m', 0)
            vol_ratio = condition.get('volume_ratio', 0)
            rsi = condition.get('rsi', 0)
            
            # Status indicators
            status = []
            if condition.get('is_spike'):
                status.append('VOL_SPIKE')
            if rsi and (rsi < 30 or rsi > 70):
                status.append('RSI_EXT')
            if abs(change) > 3:
                status.append('MOVING')
            
            status_str = ', '.join(status) if status else 'Normal'
            
            # Color coding for console
            change_str = f"{change:+.2f}%"
            if abs(change) > 3:
                change_str = f"*{change_str}*"
            
            print(f"{symbol:<15} ${price:>9.6f} {change_str:>10} {vol_ratio:>9.1f}x "
                  f"{rsi:>7.1f} {status_str:<20}")
        
        print(f"\n{'='*80}")
        
        # Log summary
        logger.info(f"Multi-pair summary - Symbols: {len(self.symbols)}, "
                   f"Updates: {self.stats['total_updates']}, "
                   f"Alerts: {self.stats['total_alerts_sent']}")
    
    async def send_periodic_summary(self):
        """Send periodic summary to Telegram"""
        # Calculate summary data
        summary_data = {
            'hours': 1,
            'total_pairs': len(self.symbols),
            'total_alerts': self.stats['total_alerts_sent'],
            'strong_signals': 0,
            'top_opportunities': [],
            'biggest_movers': [],
            'high_risk_pairs': []
        }
        
        # Analyze recent alerts for opportunities
        for symbol, last_alert_time in self.stats['last_alert_time'].items():
            if datetime.now(timezone.utc) - last_alert_time < timedelta(hours=1):
                condition = self.market_conditions.get(symbol, {})
                if condition:
                    # Determine opportunity type
                    rsi = condition.get('rsi', 50)
                    change = condition.get('change_5m', 0)
                    volume_ratio = condition.get('volume_ratio', 1)
                    
                    confidence = 0
                    action = 'Watch'
                    opp_type = 'neutral'
                    
                    if rsi and rsi < 30 and volume_ratio > 2:
                        confidence = 80
                        action = 'Oversold bounce setup'
                        opp_type = 'buy'
                        summary_data['strong_signals'] += 1
                    elif volume_ratio > 5 and change > 2:
                        confidence = 75
                        action = 'Pump in progress'
                        opp_type = 'buy'
                        summary_data['strong_signals'] += 1
                    elif rsi and rsi > 80:
                        confidence = 70
                        action = 'Overbought - watch for dump'
                        opp_type = 'sell'
                    
                    if confidence > 60:
                        summary_data['top_opportunities'].append({
                            'symbol': symbol,
                            'type': opp_type,
                            'action': action,
                            'confidence': confidence
                        })
        
        # Find biggest movers
        movers = []
        for symbol, condition in self.market_conditions.items():
            change = condition.get('change_5m', 0)
            if abs(change) > 2:
                movers.append({'symbol': symbol, 'change': change})
        
        summary_data['biggest_movers'] = sorted(movers, key=lambda x: abs(x['change']), reverse=True)[:5]
        
        # Identify high risk pairs
        for symbol, condition in self.market_conditions.items():
            rsi = condition.get('rsi', 50)
            volume_ratio = condition.get('volume_ratio', 1)
            
            if rsi and rsi > 85:
                summary_data['high_risk_pairs'].append({
                    'symbol': symbol,
                    'reason': f'Extremely overbought (RSI {rsi:.0f})'
                })
            elif volume_ratio > 10:
                summary_data['high_risk_pairs'].append({
                    'symbol': symbol,
                    'reason': f'Abnormal volume ({volume_ratio:.1f}x)'
                })
        
        # Sort opportunities by confidence
        summary_data['top_opportunities'].sort(key=lambda x: x['confidence'], reverse=True)
        
        # Send summary
        if summary_data['total_alerts'] > 0 or len(summary_data['biggest_movers']) > 0:
            message = self.telegram.format_hourly_summary(summary_data)
            await self.telegram.send_message(message)
    
    async def monitor_loop(self):
        """Main monitoring loop"""
        self.running = True
        last_summary = datetime.now(timezone.utc)
        summary_interval = timedelta(hours=1)
        
        logger.info(f"Starting multi-pair monitoring for {len(self.symbols)} symbols")
        await self.telegram.send_message(
            f"<b>🚀 Monitoring Started</b>\n"
            f"Tracking {len(self.symbols)} pairs\n"
            f"Alert threshold: HIGH/EXTREME only"
        )
        
        while self.running:
            try:
                self.stats['total_updates'] += 1
                
                # Process all symbols
                await self.process_all_symbols()
                
                # Print summary
                self.print_summary()
                
                # Send periodic summary
                if datetime.now(timezone.utc) - last_summary > summary_interval:
                    await self.send_periodic_summary()
                    last_summary = datetime.now(timezone.utc)
                
                # Wait before next cycle
                await asyncio.sleep(30)  # 30 seconds between updates
                
            except Exception as e:
                logger.error(f"Error in monitor loop: {e}")
                await asyncio.sleep(30)
    
    def stop(self):
        """Stop monitoring"""
        self.running = False
        self.executor.shutdown(wait=True)
        logger.info("Multi-pair monitor stopped")


async def main():
    """Main entry point"""
    # Load symbols from low volume pairs
    try:
        with open('../mexc_low_volume_pairs_20250726_151810.json', 'r') as f:
            all_pairs = json.load(f)
        
        # Select interesting pairs
        selected_pairs = []
        for pair in all_pairs:
            # High leverage, low to medium volume pairs (expanded criteria)
            if (pair['max_leverage'] >= 50 and 
                pair['volume_24h_millions'] < 50 and  # Increased from 10
                pair['is_active']):
                selected_pairs.append(pair['symbol'])
        
        # Limit to top 100 most interesting
        selected_pairs = selected_pairs[:100]
        
        logger.info(f"Selected {len(selected_pairs)} pairs for monitoring")
        
    except Exception as e:
        logger.error(f"Error loading pairs: {e}")
        # Fallback pairs
        selected_pairs = [
            'AIXBT_USDT', 'USUAL_USDT', 'CULT_USDT', 
            'GRT_USDT', 'XMR_USDT', 'BAKE_USDT'
        ]
    
    # Setup database
    db = MongoDBConnection()
    if not db.connect():
        logger.error("Failed to connect to database")
        return
    
    # Create indexes
    try:
        db.db.multi_pair_monitoring.create_index([("symbol", 1), ("timestamp", -1)])
        db.db.multi_pair_monitoring.create_index([("monitoring_session", 1)])
    except:
        pass
    
    # Setup Telegram
    telegram = TelegramNotifier()
    await telegram.initialize()
    
    # Create monitor
    monitor = MultiPairMonitor(selected_pairs, db, telegram)
    
    # Signal handler
    def signal_handler(signum, frame):
        logger.info("Shutdown signal received")
        monitor.stop()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        await monitor.monitor_loop()
    finally:
        monitor.stop()
        await telegram.close()
        db.disconnect()


if __name__ == "__main__":
    print("\n🚀 Multi-Pair Monitor with Telegram Alerts")
    print("=" * 50)
    print("Configure in .env:")
    print("  TELEGRAM_BOT_TOKEN=your_bot_token")
    print("  TELEGRAM_CHANNEL_ID=@your_channel or chat_id")
    print("=" * 50)
    print("\nStarting monitor...")
    
    asyncio.run(main())