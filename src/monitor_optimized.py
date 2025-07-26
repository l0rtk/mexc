#!/usr/bin/env python3
"""
Optimized Monitor - Fixed performance issues, configurable features
"""

import sys
import os
import argparse
import asyncio
import json
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional
from collections import defaultdict

# Add src to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from data_fetcher import SinglePairDataFetcher
from enhanced_data_fetcher import EnhancedDataFetcher
from database import MongoDBConnection
from telegram_notifier_v2 import EnhancedTelegramNotifier
from logging_config import get_logger
from dotenv import load_dotenv

# Import components conditionally
from funding_analyzer import FundingAnalyzer
from statistical_analyzer import StatisticalAnalyzer
from advanced_signals_v2 import enhance_alert_detection_v2
# from advanced_signals import enhance_alert_detection  # Removed, using V2
from monitor_config import get_config, set_config_mode

# Load environment
load_dotenv('../.env')
logger = get_logger(__name__)


class OptimizedMonitor:
    """Performance-optimized monitor with configurable features"""
    
    def __init__(self, symbols: List[str], db_connection: MongoDBConnection, 
                 telegram_notifier: EnhancedTelegramNotifier, config_mode: str = "balanced"):
        self.symbols = symbols
        self.db = db_connection
        self.telegram = telegram_notifier
        self.running = False
        
        # Set configuration
        set_config_mode(config_mode)
        self.config = get_config()
        logger.info(f"Monitor config:\n{self.config.summary()}")
        
        # Create fetchers
        self.fetchers = {}
        self.enhanced_fetchers = {}
        for symbol in symbols:
            self.fetchers[symbol] = SinglePairDataFetcher(symbol)
            self.enhanced_fetchers[symbol] = EnhancedDataFetcher(symbol)
        
        # Initialize components based on config
        if self.config.get("enable_funding"):
            self.funding_analyzer = FundingAnalyzer(db_connection)
        else:
            self.funding_analyzer = None
            
        if self.config.get("enable_statistics"):
            self.statistical_analyzer = StatisticalAnalyzer(db_connection)
        else:
            self.statistical_analyzer = None
        
        # Tracking
        self.stats = {
            'start_time': datetime.now(timezone.utc),
            'total_updates': 0,
            'total_alerts': 0,
            'processing_times': defaultdict(list)
        }
        
        # Simple alert cooldown
        self.last_alert_time = {}
        self.alert_cooldown = timedelta(minutes=5)
        
        # Market conditions cache
        self.market_conditions = {}
        
        # Performance tracking
        self.slow_operations = set()  # Track operations that are too slow
        
        # Rate limiting for order book
        self.order_book_last_fetch = {}
        self.order_book_min_interval = 2.0  # Minimum seconds between order book requests per symbol
        self.order_book_batch_limit = 5  # Max order book requests per batch
        self.order_book_request_count = 0  # Track requests in current batch
        
    async def process_symbol(self, symbol: str) -> Optional[Dict]:
        """Optimized symbol processing"""
        try:
            start_time = time.time()
            timings = {}
            
            # 1. Fetch candles (ALWAYS)
            t0 = time.time()
            candles = self.fetchers[symbol].fetch_candles(
                limit=self.config.get("candle_limit", 60)
            )
            if not candles:
                return None
            timings['candles'] = time.time() - t0
            
            # 2. Basic analysis (ALWAYS)
            t0 = time.time()
            analysis = self.fetchers[symbol].analyze_candle_data(candles)
            timings['analysis'] = time.time() - t0
            
            # Quick check if this symbol is worth deeper analysis
            is_active = (
                analysis['volume_analysis']['spike_magnitude'] > 1.5 or
                abs(analysis['price_movement']['change_5m']) > 0.5 or
                (analysis['indicators'].get('rsi_14', 50) < 35 or 
                 analysis['indicators'].get('rsi_14', 50) > 65)
            )
            
            # 3. Order book (CONDITIONAL with rate limiting)
            order_book = {}
            if self.config.get("enable_order_book") and is_active:
                # Check both per-symbol rate limit and batch limit
                last_fetch = self.order_book_last_fetch.get(symbol, 0)
                if (time.time() - last_fetch >= self.order_book_min_interval and 
                    self.order_book_request_count < self.order_book_batch_limit):
                    if 'order_book' not in self.slow_operations:
                        try:
                            t0 = time.time()
                            order_book = self.enhanced_fetchers[symbol].fetch_order_book(
                                depth=self.config.get("order_book_depth", 10)
                            )
                            ob_time = time.time() - t0
                            timings['order_book'] = ob_time
                            
                            # Update last fetch time and count
                            self.order_book_last_fetch[symbol] = time.time()
                            self.order_book_request_count += 1
                            
                            # Mark as slow if taking too long
                            if ob_time > 2:
                                logger.warning(f"Order book slow for {symbol}: {ob_time:.2f}s")
                                self.slow_operations.add('order_book')
                        except Exception as e:
                            logger.debug(f"Order book failed for {symbol}: {str(e)[:50]}")
            
            # 4. Multi-timeframe (CONDITIONAL)
            tf_divergence = {}
            if self.config.get("enable_multi_timeframe") and is_active:
                if 'multi_tf' not in self.slow_operations:
                    try:
                        t0 = time.time()
                        multi_tf_data = self.fetchers[symbol].fetch_multi_timeframe()
                        tf_divergence = self.fetchers[symbol].detect_timeframe_divergence(multi_tf_data)
                        mtf_time = time.time() - t0
                        timings['multi_tf'] = mtf_time
                        
                        if mtf_time > 3:
                            logger.warning(f"Multi-TF slow for {symbol}: {mtf_time:.2f}s")
                            self.slow_operations.add('multi_tf')
                    except Exception as e:
                        logger.debug(f"Multi-TF failed for {symbol}: {str(e)[:50]}")
            
            # 5. Funding (CONDITIONAL - but cached so fast)
            funding_data = {}
            if self.config.get("enable_funding") and self.funding_analyzer:
                try:
                    t0 = time.time()
                    funding_data = self.funding_analyzer.analyze_funding(symbol, analysis)
                    timings['funding'] = time.time() - t0
                except Exception as e:
                    logger.debug(f"Funding failed for {symbol}: {str(e)[:50]}")
            
            # 6. Statistics (CONDITIONAL)
            stats_data = {}
            if self.config.get("enable_statistics") and self.statistical_analyzer:
                try:
                    t0 = time.time()
                    # Use simple confidence for now
                    stats_data = self.statistical_analyzer.analyze_statistics(
                        symbol, analysis, 0.5
                    )
                    timings['statistics'] = time.time() - t0
                except Exception as e:
                    logger.debug(f"Statistics failed for {symbol}: {str(e)[:50]}")
            
            # 7. Signal detection (choose based on config)
            t0 = time.time()
            if self.config.get("enable_statistics") and stats_data:
                # Use V2 with all data
                signal = enhance_alert_detection_v2(
                    analysis,
                    order_book=order_book,
                    funding_data=funding_data,
                    liquidation_data=None,  # Always skip - too slow
                    stats_data=stats_data,
                    tf_divergence=tf_divergence
                )
            else:
                # Use V2 with minimal data (simpler, faster)
                signal = enhance_alert_detection_v2(analysis, order_book)
            timings['signal'] = time.time() - t0
            
            # Update market conditions
            self.market_conditions[symbol] = {
                'price': analysis['ohlcv']['close'],
                'change_5m': analysis['price_movement']['change_5m'],
                'volume_ratio': analysis['volume_analysis']['volume_ratio_5m'],
                'rsi': analysis['indicators'].get('rsi_14'),
                'is_active': is_active,
                'last_update': datetime.now(timezone.utc)
            }
            
            # Store in database (simple, no duplicates check for speed)
            if is_active:
                try:
                    self.db.db.optimized_monitoring.insert_one({
                        'symbol': symbol,
                        'timestamp': analysis['timestamp'],
                        'config_mode': self.config.mode,
                        'analysis': analysis,
                        'signal': signal,
                        'timings': timings
                    })
                except:
                    pass
            
            # Log performance
            total_time = time.time() - start_time
            self.stats['processing_times'][symbol].append(total_time)
            
            if total_time > 5:
                logger.warning(f"[{symbol}] Slow processing: {total_time:.2f}s - {timings}")
            else:
                logger.debug(f"[{symbol}] Processed in {total_time:.2f}s - "
                           f"Action: {signal['action']}, Risk: {signal['risk_level']}")
            
            # Check for alerts
            confidence_threshold = self.config.get("confidence_threshold", 0.6)
            if signal['risk_level'] in ['HIGH', 'EXTREME'] and signal['confidence'] >= confidence_threshold:
                # Check cooldown
                last_alert = self.last_alert_time.get(symbol)
                if not last_alert or datetime.now(timezone.utc) - last_alert > self.alert_cooldown:
                    return {
                        'symbol': symbol,
                        'signal': signal,
                        'analysis': analysis,
                        'order_book': order_book,
                        'funding_data': funding_data
                    }
            
            return None
            
        except Exception as e:
            logger.error(f"Error processing {symbol}: {e}")
            return None
    
    async def process_batch(self):
        """Process all symbols in parallel"""
        start = time.time()
        
        # Reset order book request count for this batch
        self.order_book_request_count = 0
        
        # Create tasks for all symbols
        tasks = []
        for symbol in self.symbols:
            task = asyncio.create_task(self.process_symbol(symbol))
            tasks.append(task)
        
        # Wait for all to complete
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results
        alerts = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Task failed for {self.symbols[i]}: {result}")
            elif result:
                alerts.append(result)
        
        # Send alerts (more for 100 pairs)
        max_alerts = 5 if len(self.symbols) > 50 else 3
        for alert_data in alerts[:max_alerts]:
            await self.send_alert(alert_data)
        
        elapsed = time.time() - start
        logger.info(f"Batch processed {len(self.symbols)} symbols in {elapsed:.2f}s")
        
        # Adjust features based on performance and pair count
        if len(self.symbols) > 50:
            # For 100 pairs, be more aggressive with optimization
            if elapsed > 30:
                logger.warning("Processing too slow for 100 pairs, optimizing...")
                if self.config.get("enable_multi_timeframe"):
                    self.config.update({"enable_multi_timeframe": False})
                    logger.info("Disabled multi-timeframe analysis")
                if self.config.get("enable_order_book"):
                    self.config.update({"enable_order_book": False})
                    logger.info("Disabled order book analysis")
        elif elapsed > 15 and len(self.symbols) <= 5:
            logger.warning("Processing too slow, disabling some features")
            if self.config.get("enable_multi_timeframe"):
                self.config.update({"enable_multi_timeframe": False})
                logger.info("Disabled multi-timeframe analysis")
        
        return len(alerts)
    
    async def send_alert(self, alert_data: Dict):
        """Send alert to Telegram"""
        symbol = alert_data['symbol']
        signal = alert_data['signal']
        analysis = alert_data['analysis']
        
        # Build alert data for formatter
        alert_info = {
            'symbol': symbol,
            'patterns': signal,
            'snapshot': {
                'price': analysis['ohlcv']['close'],
                'price_change_5m': analysis['price_movement']['change_5m'],
                'volume_ratio': analysis['volume_analysis']['spike_magnitude'],
                'rsi': analysis['indicators'].get('rsi_14')
            }
        }
        
        # Add funding if available
        if alert_data.get('funding_data'):
            alert_info['funding_data'] = alert_data['funding_data']
        
        message = self.telegram.format_enhanced_alert(alert_info)
        success = await self.telegram.send_message(message)
        
        if success:
            self.last_alert_time[symbol] = datetime.now(timezone.utc)
            self.stats['total_alerts'] += 1
            logger.warning(f"Alert sent for {symbol}: {signal['action']} "
                         f"({signal['confidence']*100:.0f}% confidence)")
    
    def print_summary(self):
        """Print performance summary"""
        print(f"\r[{datetime.now().strftime('%H:%M:%S')}] "
              f"Mode: {self.config.mode} | "
              f"Updates: {self.stats['total_updates']} | "
              f"Alerts: {self.stats['total_alerts']} | ", end='')
        
        # Show average processing time
        all_times = []
        for times in self.stats['processing_times'].values():
            all_times.extend(times[-10:])  # Last 10 per symbol
        
        if all_times:
            avg_time = sum(all_times) / len(all_times)
            print(f"Avg: {avg_time:.2f}s", end='')
        
        # Show most active
        if self.market_conditions:
            active = sorted(self.market_conditions.items(),
                          key=lambda x: abs(x[1].get('change_5m', 0)),
                          reverse=True)
            if active:
                symbol, data = active[0]
                print(f" | Top: {symbol} {data['change_5m']:+.2f}%", end='')
        
        print("", flush=True)
    
    async def run(self):
        """Main monitoring loop"""
        self.running = True
        
        logger.info(f"Starting optimized monitor for {len(self.symbols)} symbols")
        
        # Send startup message
        startup_msg = f"<b>⚡ Optimized Monitor Started</b>\n\n"
        startup_msg += f"Mode: <b>{self.config.mode}</b>\n"
        startup_msg += f"Symbols: {', '.join(self.symbols)}\n"
        startup_msg += f"Update interval: {self.config.get('update_interval')}s\n\n"
        startup_msg += f"<i>{self.config.summary()}</i>"
        
        await self.telegram.send_message(startup_msg)
        
        while self.running:
            try:
                self.stats['total_updates'] += 1
                
                # Process batch
                alert_count = await self.process_batch()
                
                # Print summary
                self.print_summary()
                
                # Clear slow operations periodically
                if self.stats['total_updates'] % 20 == 0:
                    self.slow_operations.clear()
                
                # Sleep
                await asyncio.sleep(self.config.get("update_interval", 10))
                
            except KeyboardInterrupt:
                break
            except Exception as e:
                logger.error(f"Monitor error: {e}", exc_info=True)
                await asyncio.sleep(10)
        
        logger.info("Optimized monitor stopped")


async def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description='Optimized MEXC Monitor',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Modes:
  fast     - Speed optimized (5s updates, minimal features)
  balanced - Good balance of speed and accuracy (default)
  thorough - All features enabled (slower)
  startup  - For first run without history (sensitive thresholds)

Examples:
  # Fast mode for 3 pairs
  python monitor_optimized.py --mode fast AIXBT_USDT USUAL_USDT XMR_USDT
  
  # Startup mode for testing
  python monitor_optimized.py --mode startup AIXBT_USDT
  
  # Balanced mode from file
  python monitor_optimized.py --file watchlist.txt
        """
    )
    
    parser.add_argument('symbols', nargs='*', help='Symbols to monitor')
    parser.add_argument('--mode', '-m', choices=['fast', 'balanced', 'thorough', 'startup'],
                       default='balanced', help='Monitoring mode')
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
                        # Remove any comments after the symbol
                        symbol = line.split('#')[0].strip()
                        if symbol:
                            symbols.append(symbol)
        except Exception as e:
            print(f"Error loading file: {e}")
            return
    
    if not symbols:
        print("No symbols specified!")
        parser.print_help()
        return
    
    # Validate symbols
    valid_symbols = []
    for s in symbols:
        s = s.upper().strip()
        if not s.endswith('_USDT'):
            s += '_USDT'
        valid_symbols.append(s)
    
    print(f"\nMonitoring {len(valid_symbols)} symbols in {args.mode} mode")
    print("-" * 50)
    
    # Setup
    db = MongoDBConnection()
    if not db.connect():
        print("Database connection failed")
        return
    
    telegram = EnhancedTelegramNotifier()
    await telegram.initialize()
    
    # Create and run monitor
    monitor = OptimizedMonitor(valid_symbols, db, telegram, args.mode)
    
    try:
        await monitor.run()
    finally:
        await telegram.close()
        db.disconnect()


if __name__ == "__main__":
    asyncio.run(main())