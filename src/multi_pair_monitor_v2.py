"""
Enhanced Multi-Pair Monitor V2 with all advanced features
Integrates funding, liquidations, statistics, and intelligent alerts
"""

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
from telegram_notifier_v2 import EnhancedTelegramNotifier
from logging_config import get_logger
from dotenv import load_dotenv

# New components
from funding_analyzer import FundingAnalyzer, setup_funding_indexes
from liquidation_monitor import LiquidationMonitor, setup_liquidation_indexes
from statistical_analyzer import StatisticalAnalyzer
from advanced_signals_v2 import enhance_alert_detection_v2
from alert_prioritizer import AlertPrioritizer, setup_alert_indexes

# Load environment variables
load_dotenv('../.env')

# Configure logging
logger = get_logger(__name__)


class MultiPairMonitorV2:
    """Enhanced monitor with all advanced features"""
    
    def __init__(self, symbols: List[str], db_connection: MongoDBConnection, 
                 telegram_notifier: EnhancedTelegramNotifier):
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
        
        # Initialize new components
        self.funding_analyzer = FundingAnalyzer(db_connection)
        self.liquidation_monitor = LiquidationMonitor(db_connection)
        self.statistical_analyzer = StatisticalAnalyzer(db_connection)
        self.alert_prioritizer = AlertPrioritizer(db_connection)
        
        # Tracking
        self.stats = {
            'start_time': datetime.now(timezone.utc),
            'total_updates': 0,
            'alerts_by_symbol': defaultdict(int),
            'last_alert_time': {},
            'total_alerts_sent': 0,
            'alerts_blocked': 0
        }
        
        # Thread pool for concurrent processing
        self.executor = ThreadPoolExecutor(max_workers=min(20, len(symbols)))
        
        # Market conditions tracking
        self.market_conditions = {}
        
        # Performance tracking
        self.alert_tracking = {}  # Track alerts for outcome monitoring
        
    async def process_symbol(self, symbol: str) -> Optional[Dict]:
        """Process a single symbol with all analyses"""
        try:
            start_time = time.time()
            logger.debug(f"[{symbol}] Starting enhanced processing")
            
            # 1. Fetch basic candles
            candles = self.fetchers[symbol].fetch_candles(limit=60)
            if not candles:
                logger.warning(f"[{symbol}] No candles returned")
                return None
            
            # 2. Basic analysis
            analysis = self.fetchers[symbol].analyze_candle_data(candles)
            
            # 3. Multi-timeframe analysis (optional, don't block if fails)
            tf_divergence = {}
            try:
                multi_tf_start = time.time()
                multi_tf_data = self.fetchers[symbol].fetch_multi_timeframe()
                tf_divergence = self.fetchers[symbol].detect_timeframe_divergence(multi_tf_data)
                logger.debug(f"[{symbol}] Multi-TF analysis in {time.time() - multi_tf_start:.2f}s")
            except Exception as e:
                logger.debug(f"[{symbol}] Multi-TF analysis failed: {str(e)[:50]}")
            
            # 4. Order book (optional)
            order_book = {}
            try:
                ob_start = time.time()
                order_book = self.enhanced_fetchers[symbol].fetch_order_book(depth=10)
                logger.debug(f"[{symbol}] Order book in {time.time() - ob_start:.2f}s")
            except Exception as e:
                logger.debug(f"[{symbol}] Order book failed: {str(e)[:50]}")
            
            # 5. Funding analysis
            funding_data = {}
            try:
                funding_start = time.time()
                funding_data = self.funding_analyzer.analyze_funding(symbol, analysis)
                logger.debug(f"[{symbol}] Funding analysis in {time.time() - funding_start:.2f}s - "
                           f"Rate: {funding_data.get('current_rate', 0):.4%}, "
                           f"Arb score: {funding_data.get('funding_arb_score', 0):.2f}")
            except Exception as e:
                logger.debug(f"[{symbol}] Funding analysis failed: {str(e)[:50]}")
            
            # 6. Liquidation analysis
            liquidation_data = {}
            try:
                liq_start = time.time()
                liquidation_data = self.liquidation_monitor.analyze_liquidation_risk(
                    symbol, analysis, order_book
                )
                liq_pressure = liquidation_data.get('liquidation_pressure', {})
                logger.debug(f"[{symbol}] Liquidation analysis in {time.time() - liq_start:.2f}s - "
                           f"Cascade prob: {liq_pressure.get('cascade_probability', 0):.2f}")
            except Exception as e:
                logger.debug(f"[{symbol}] Liquidation analysis failed: {str(e)[:50]}")
            
            # 7. Statistical analysis
            stats_data = {}
            try:
                stats_start = time.time()
                base_confidence = 0.5  # Will be updated by signal detection
                stats_data = self.statistical_analyzer.analyze_statistics(
                    symbol, analysis, base_confidence
                )
                logger.debug(f"[{symbol}] Statistical analysis in {time.time() - stats_start:.2f}s - "
                           f"Volume Z: {stats_data.get('zscore', {}).get('volume_zscore', 0):.2f}, "
                           f"Regime: {stats_data.get('market_regime', 'unknown')}")
            except Exception as e:
                logger.debug(f"[{symbol}] Statistical analysis failed: {str(e)[:50]}")
            
            # 8. Enhanced signal detection with ALL data
            signal_start = time.time()
            advanced_signal = enhance_alert_detection_v2(
                analysis, 
                order_book=order_book,
                funding_data=funding_data,
                liquidation_data=liquidation_data.get('liquidation_pressure'),
                stats_data=stats_data,
                tf_divergence=tf_divergence
            )
            signal_time = time.time() - signal_start
            
            logger.debug(f"[{symbol}] Signal detection V2 in {signal_time:.3f}s - "
                        f"Action={advanced_signal['action']}, "
                        f"Risk={advanced_signal['risk_level']}, "
                        f"Confidence={advanced_signal['confidence']:.2f}, "
                        f"Signals={advanced_signal['num_signals']}")
            
            # 9. Store comprehensive market data
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
                } if order_book else None,
                'funding_analysis': funding_data,
                'liquidation_analysis': liquidation_data.get('liquidation_pressure'),
                'statistical_analysis': {
                    'zscore': stats_data.get('zscore'),
                    'market_regime': stats_data.get('market_regime'),
                    'dynamic_threshold': stats_data.get('dynamic_threshold')
                } if stats_data else None,
                'timeframe_divergence': tf_divergence if tf_divergence.get('has_divergence') else None
            }
            
            # Store if not duplicate
            if not self.db.check_duplicate_candle(symbol, analysis['timestamp']):
                self.db.db.multi_pair_monitoring_v2.insert_one(market_record)
            
            # Update market conditions
            self.market_conditions[symbol] = {
                'price': analysis['ohlcv']['close'],
                'change_5m': analysis['price_movement']['change_5m'],
                'volume_ratio': analysis['volume_analysis']['volume_ratio_5m'],
                'rsi': analysis['indicators'].get('rsi_14'),
                'is_spike': analysis['volume_analysis']['is_spike'],
                'funding_rate': funding_data.get('current_rate', 0),
                'regime': stats_data.get('market_regime', 'unknown'),
                'last_update': datetime.now(timezone.utc)
            }
            
            # Check if alert should be sent
            total_time = time.time() - start_time
            logger.debug(f"[{symbol}] Total processing time: {total_time:.2f}s")
            
            if advanced_signal['risk_level'] in ['HIGH', 'EXTREME']:
                # Build comprehensive alert data
                alert_data = {
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
                    'patterns': advanced_signal,
                    'funding_data': funding_data,
                    'liquidation_data': liquidation_data.get('liquidation_pressure'),
                    'statistical_data': stats_data,
                    'candles': candles  # For ATR calculation in alerts
                }
                
                # Calculate priority
                priority = self.alert_prioritizer.calculate_alert_priority(
                    alert_data, 
                    self._get_global_market_conditions()
                )
                alert_data['priority'] = priority
                
                # Check if should send
                dynamic_threshold = stats_data.get('dynamic_threshold', 0.7) if stats_data else 0.7
                should_send = self.alert_prioritizer.should_send_alert(
                    alert_data, priority, dynamic_threshold
                )
                
                if should_send:
                    # Get historical performance for this type of setup
                    perf = self._get_setup_performance(alert_data)
                    alert_data['performance'] = perf
                    
                    return alert_data
                else:
                    logger.debug(f"[{symbol}] Alert blocked by prioritizer - "
                               f"Priority: {priority:.3f} < Threshold: {dynamic_threshold:.3f}")
                    self.stats['alerts_blocked'] += 1
            
            return None
            
        except Exception as e:
            logger.error(f"Error processing {symbol}: {e}", exc_info=True)
            return None
    
    def _get_global_market_conditions(self) -> Dict:
        """Get global market conditions (BTC trend, etc.)"""
        # Simplified - in production, would track BTC separately
        btc_symbol = 'BTC_USDT'
        if btc_symbol in self.market_conditions:
            btc_change = self.market_conditions[btc_symbol].get('change_5m', 0)
            if btc_change > 2:
                btc_trend = 'strong_up'
            elif btc_change > 0.5:
                btc_trend = 'up'
            elif btc_change < -2:
                btc_trend = 'strong_down'
            elif btc_change < -0.5:
                btc_trend = 'down'
            else:
                btc_trend = 'neutral'
        else:
            btc_trend = 'neutral'
        
        return {
            'btc_trend': btc_trend,
            'total_symbols': len(self.symbols),
            'active_symbols': len(self.market_conditions)
        }
    
    def _get_setup_performance(self, alert_data: Dict) -> Dict:
        """Get historical performance for similar setups"""
        # This would query historical data for similar patterns
        # For now, return mock data
        symbol = alert_data['symbol']
        action = alert_data['patterns']['action']
        
        # In production, would query database for similar historical setups
        perf_data = self.alert_prioritizer.symbol_performance.get(symbol, {})
        
        return {
            'similar_setups_count': perf_data.get('total_alerts', 0),
            'wins': perf_data.get('successful_alerts', 0),
            'win_rate': perf_data.get('win_rate', 0.5) * 100,
            'avg_return': 4.2  # Mock average return
        }
    
    async def send_telegram_alert(self, alert_data: Dict):
        """Send enhanced alert to Telegram"""
        symbol = alert_data['symbol']
        
        # Update alert history
        self.alert_prioritizer.update_alert_history(symbol, alert_data)
        
        # Format and send message
        message = self.telegram.format_enhanced_alert(alert_data)
        success = await self.telegram.send_message(message)
        
        if success:
            # Track for outcome monitoring
            self.alert_tracking[f"{symbol}_{alert_data['timestamp']}"] = {
                'symbol': symbol,
                'alert_time': alert_data['timestamp'],
                'action': alert_data['patterns']['action'],
                'entry_price': alert_data['snapshot']['price'],
                'confidence': alert_data['patterns']['confidence']
            }
            
            # Update stats
            self.stats['last_alert_time'][symbol] = datetime.now(timezone.utc)
            self.stats['alerts_by_symbol'][symbol] += 1
            self.stats['total_alerts_sent'] += 1
            
            # Log alert
            logger.warning(f"Enhanced alert sent for {symbol}: {alert_data['risk_level']} risk, "
                         f"Priority: {alert_data['priority']:.3f}")
    
    async def process_all_symbols(self):
        """Process all symbols concurrently"""
        start_time = time.time()
        logger.info(f"Starting enhanced batch processing of {len(self.symbols)} symbols")
        
        # Process all symbols in parallel
        tasks = []
        for symbol in self.symbols:
            task = self.process_symbol(symbol)
            tasks.append(task)
        
        # Wait for all to complete
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        batch_time = time.time() - start_time
        logger.info(f"Enhanced batch processing completed in {batch_time:.2f}s")
        
        # Process results and send alerts
        alerts_to_send = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Error processing {self.symbols[i]}: {result}")
            elif result:  # Alert data returned
                alerts_to_send.append(result)
        
        # Sort alerts by priority
        alerts_to_send.sort(key=lambda x: x['priority'], reverse=True)
        
        # Send top alerts (limit to prevent spam)
        max_alerts_per_batch = 5
        for alert in alerts_to_send[:max_alerts_per_batch]:
            await self.send_telegram_alert(alert)
        
        if len(alerts_to_send) > max_alerts_per_batch:
            logger.info(f"Limited alerts to {max_alerts_per_batch}, skipped {len(alerts_to_send) - max_alerts_per_batch}")
    
    def print_summary(self):
        """Print enhanced monitoring summary"""
        os.system('clear' if os.name == 'posix' else 'cls')
        
        print(f"\n{'='*100}")
        print(f"ENHANCED MULTI-PAIR MONITOR V2 - {len(self.symbols)} SYMBOLS")
        print(f"{'='*100}")
        
        runtime = (datetime.now(timezone.utc) - self.stats['start_time']).seconds
        print(f"Runtime: {runtime // 60}m {runtime % 60}s | Updates: {self.stats['total_updates']} | "
              f"Alerts: {self.stats['total_alerts_sent']} sent, {self.stats['alerts_blocked']} blocked")
        
        # Performance stats
        perf_stats = self.alert_prioritizer.get_alert_statistics()
        print(f"Win Rate: {perf_stats['global_win_rate']:.1%} | "
              f"Active Cooldowns: {perf_stats['active_cooldowns']}")
        
        print(f"\n{'Symbol':<12} {'Price':>10} {'5m%':>8} {'Vol':>8} {'RSI':>6} "
              f"{'Fund%':>8} {'Regime':<10} {'Status':<20}")
        print("-" * 100)
        
        # Sort by activity
        sorted_symbols = sorted(self.market_conditions.items(), 
                              key=lambda x: abs(x[1].get('change_5m', 0)), 
                              reverse=True)
        
        for symbol, condition in sorted_symbols[:20]:  # Top 20 most active
            price = condition.get('price', 0)
            change = condition.get('change_5m', 0)
            vol_ratio = condition.get('volume_ratio', 0)
            rsi = condition.get('rsi', 0)
            funding = condition.get('funding_rate', 0) * 100  # As percentage
            regime = condition.get('regime', 'unknown')[:8]
            
            # Status indicators
            status = []
            if condition.get('is_spike'):
                status.append('VOL')
            if rsi and (rsi < 30 or rsi > 70):
                status.append('RSI')
            if abs(change) > 3:
                status.append('MOVE')
            if abs(funding) > 0.1:
                status.append('FUND')
            
            # Color coding
            change_str = f"{change:+.2f}%"
            if abs(change) > 5:
                change_str = f"*{change_str}*"
            
            funding_str = f"{funding:+.3f}%"
            if abs(funding) > 0.15:
                funding_str = f"*{funding_str}*"
            
            status_str = ', '.join(status) if status else 'Normal'
            
            print(f"{symbol:<12} ${price:>9.6f} {change_str:>8} {vol_ratio:>7.1f}x "
                  f"{rsi:>5.0f} {funding_str:>8} {regime:<10} {status_str:<20}")
        
        if len(self.symbols) > 20:
            print(f"\n... and {len(self.symbols) - 20} more pairs")
        
        print(f"\n{'='*100}")
    
    async def monitor_loop(self):
        """Main enhanced monitoring loop"""
        self.running = True
        last_summary = datetime.now(timezone.utc)
        last_outcome_check = datetime.now(timezone.utc)
        summary_interval = timedelta(hours=1)
        outcome_interval = timedelta(minutes=15)
        
        logger.info(f"Starting enhanced multi-pair monitoring for {len(self.symbols)} symbols")
        
        # Initial setup message
        await self.telegram.send_message(
            f"<b>🚀 Enhanced Monitor V2 Started</b>\n\n"
            f"• Tracking {len(self.symbols)} pairs\n"
            f"• Funding analysis enabled\n"
            f"• Liquidation monitoring active\n"
            f"• Statistical filtering on\n"
            f"• Smart prioritization enabled\n\n"
            f"<i>Expect higher quality, actionable alerts!</i>"
        )
        
        while self.running:
            try:
                self.stats['total_updates'] += 1
                
                # Process all symbols
                await self.process_all_symbols()
                
                # Print summary
                self.print_summary()
                
                # Check alert outcomes periodically
                if datetime.now(timezone.utc) - last_outcome_check > outcome_interval:
                    await self._check_alert_outcomes()
                    last_outcome_check = datetime.now(timezone.utc)
                
                # Send periodic summary
                if datetime.now(timezone.utc) - last_summary > summary_interval:
                    await self.send_periodic_summary()
                    last_summary = datetime.now(timezone.utc)
                
                # Check for extreme funding opportunities
                if self.stats['total_updates'] % 30 == 0:  # Every 5 minutes
                    await self._check_extreme_funding()
                
                # Wait before next cycle
                await asyncio.sleep(10)  # 10 seconds
                
            except Exception as e:
                logger.error(f"Error in monitor loop: {e}", exc_info=True)
                await asyncio.sleep(10)
    
    async def _check_alert_outcomes(self):
        """Check outcomes of recent alerts for performance tracking"""
        cutoff_time = datetime.now(timezone.utc) - timedelta(minutes=60)
        
        for alert_key, alert_info in list(self.alert_tracking.items()):
            if alert_info['alert_time'] < cutoff_time:
                # Check outcome
                symbol = alert_info['symbol']
                entry_price = alert_info['entry_price']
                
                # Get current price
                current_condition = self.market_conditions.get(symbol, {})
                current_price = current_condition.get('price', entry_price)
                
                # Calculate move
                price_move = ((current_price - entry_price) / entry_price) * 100
                
                # Determine outcome based on action and move
                action = alert_info['action']
                if action in ['BUY', 'STRONG_BUY', 'FUNDING_LONG']:
                    if price_move > 1:
                        outcome = 'success'
                    elif price_move < -1:
                        outcome = 'failure'
                    else:
                        outcome = 'neutral'
                else:  # SELL actions
                    if price_move < -1:
                        outcome = 'success'
                    elif price_move > 1:
                        outcome = 'failure'
                    else:
                        outcome = 'neutral'
                
                # Track outcome
                self.alert_prioritizer.track_alert_outcome(
                    symbol, alert_info['alert_time'], outcome, abs(price_move)
                )
                
                # Remove from tracking
                del self.alert_tracking[alert_key]
                
                logger.info(f"Alert outcome for {symbol}: {outcome} ({price_move:+.2f}% move)")
    
    async def _check_extreme_funding(self):
        """Check for extreme funding opportunities across all pairs"""
        extreme_pairs = self.funding_analyzer.get_extreme_funding_pairs(threshold=0.0015)
        
        if extreme_pairs:
            logger.info(f"Found {len(extreme_pairs)} pairs with extreme funding")
            # These will be picked up in normal processing with high priority
    
    async def send_periodic_summary(self):
        """Send enhanced periodic summary"""
        # Similar to original but with more metrics
        summary_data = {
            'hours': 1,
            'total_pairs': len(self.symbols),
            'total_alerts': self.stats['total_alerts_sent'],
            'alerts_blocked': self.stats['alerts_blocked'],
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
                    summary_data['strong_signals'] += 1
        
        # Find biggest movers
        movers = []
        for symbol, condition in self.market_conditions.items():
            change = condition.get('change_5m', 0)
            if abs(change) > 2:
                movers.append({'symbol': symbol, 'change': change})
        
        summary_data['biggest_movers'] = sorted(movers, key=lambda x: abs(x['change']), reverse=True)[:5]
        
        # Performance summary
        perf_stats = self.alert_prioritizer.get_alert_statistics()
        summary_data['win_rate'] = perf_stats['global_win_rate']
        
        # Send summary
        message = self.telegram.format_summary_alert(summary_data)
        await self.telegram.send_message(message)
    
    def stop(self):
        """Stop monitoring"""
        self.running = False
        self.executor.shutdown(wait=True)
        logger.info("Enhanced multi-pair monitor stopped")


async def main():
    """Main entry point for V2 monitor"""
    # Load symbols
    try:
        with open('../mexc_low_volume_pairs_20250726_151810.json', 'r') as f:
            all_pairs = json.load(f)
        
        # Enhanced selection criteria
        selected_pairs = []
        for pair in all_pairs:
            if (pair['max_leverage'] >= 50 and 
                pair['volume_24h_millions'] < 50 and
                pair['is_active']):
                selected_pairs.append(pair['symbol'])
        
        # Limit to top 100
        selected_pairs = selected_pairs[:100]
        
        logger.info(f"Selected {len(selected_pairs)} pairs for enhanced monitoring")
        
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
    
    # Create all necessary indexes
    try:
        # Original indexes
        db.db.multi_pair_monitoring_v2.create_index([("symbol", 1), ("timestamp", -1)])
        db.db.multi_pair_monitoring_v2.create_index([("monitoring_session", 1)])
        
        # New indexes
        setup_funding_indexes(db)
        setup_liquidation_indexes(db)
        setup_alert_indexes(db)
    except Exception as e:
        logger.error(f"Error creating indexes: {e}")
    
    # Setup Telegram
    telegram = EnhancedTelegramNotifier()
    await telegram.initialize()
    
    # Create enhanced monitor
    monitor = MultiPairMonitorV2(selected_pairs, db, telegram)
    
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
    print("\n🚀 Enhanced Multi-Pair Monitor V2")
    print("=" * 50)
    print("Features:")
    print("  ✅ Funding rate analysis & arbitrage")
    print("  ✅ Liquidation cascade detection")
    print("  ✅ Multi-timeframe divergence")
    print("  ✅ Statistical significance testing")
    print("  ✅ Dynamic thresholds")
    print("  ✅ Smart alert prioritization")
    print("  ✅ Performance tracking")
    print("  ✅ Enhanced trade setups")
    print("=" * 50)
    print("\nStarting enhanced monitor...\n")
    
    asyncio.run(main())