#!/usr/bin/env python3
"""
Simple Volume Monitor - No database required
Quick volume analysis with console output
"""

import sys
import os
import argparse
import asyncio
import time
from datetime import datetime
from typing import Dict, List, Optional
import numpy as np
from collections import deque

# Add src to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from data_fetcher import SinglePairDataFetcher
from enhanced_data_fetcher import EnhancedDataFetcher
from logging_config import get_logger
from dotenv import load_dotenv

# Load environment
load_dotenv('../.env')
logger = get_logger(__name__)


class SimpleVolumeAnalyzer:
    """Simple volume analyzer for quick monitoring"""
    
    def __init__(self, symbol: str):
        self.symbol = symbol
        self.fetcher = SinglePairDataFetcher(symbol)
        self.enhanced_fetcher = EnhancedDataFetcher(symbol)
        
        # Track recent alerts
        self.recent_alerts = deque(maxlen=10)
    
    def calculate_price_change(self, candles: List[Dict], minutes: int) -> float:
        """Calculate price change over specified minutes"""
        if not candles or len(candles) < minutes:
            return 0.0
        
        current_price = float(candles[-1]['close'])
        past_price = float(candles[-minutes]['close'])
        
        if past_price == 0:
            return 0.0
            
        return ((current_price - past_price) / past_price) * 100
        
    def analyze(self) -> Optional[Dict]:
        """Perform complete volume analysis"""
        try:
            # 1. Get candle data
            candles = self.fetcher.fetch_candles(limit=50)
            if not candles:
                return None
            
            # 2. Calculate volume metrics
            volumes = [float(c['volume']) for c in candles]
            current_vol = volumes[-1]
            avg_vol = np.mean(volumes[:-1])  # Exclude current
            volume_ratio = current_vol / avg_vol if avg_vol > 0 else 0
            
            # Price info
            current_price = float(candles[-1]['close'])
            price_change_5m = self.calculate_price_change(candles, 5)
            
            # 3. Get recent trades (buy/sell pressure)
            buy_volume = 0
            sell_volume = 0
            large_trades = []
            
            try:
                trades = self.enhanced_fetcher.fetch_recent_trades(limit=50)
                if trades:
                    for trade in trades:
                        size = float(trade.get('qty', 0)) * float(trade.get('price', 0))
                        if trade.get('isBuyerMaker', False) == False:  # Buy
                            buy_volume += size
                        else:  # Sell
                            sell_volume += size
                        
                        # Track large trades (>$10k)
                        if size > 10000:
                            large_trades.append({
                                'size': size,
                                'type': 'BUY' if not trade.get('isBuyerMaker', False) else 'SELL',
                                'time': trade.get('time', 0)
                            })
            except:
                pass  # Trades might fail, continue anyway
            
            total_trade_vol = buy_volume + sell_volume
            buy_ratio = buy_volume / total_trade_vol if total_trade_vol > 0 else 0.5
            
            # 4. Determine alert level
            alert_level = None
            alert_reason = []
            
            # Check for volume spike
            if volume_ratio >= 5.0:
                alert_level = "EXTREME"
                alert_reason.append(f"Extreme volume spike: {volume_ratio:.1f}x")
            elif volume_ratio >= 3.0:
                alert_level = "HIGH"
                alert_reason.append(f"High volume spike: {volume_ratio:.1f}x")
            elif volume_ratio >= 2.0:
                alert_level = "MEDIUM"
                alert_reason.append(f"Volume spike: {volume_ratio:.1f}x")
            
            # Check buy/sell imbalance
            if buy_ratio > 0.75:
                if not alert_level or alert_level == "MEDIUM":
                    alert_level = "HIGH"
                alert_reason.append(f"Heavy buying: {buy_ratio*100:.0f}%")
            elif buy_ratio < 0.25:
                if not alert_level or alert_level == "MEDIUM":
                    alert_level = "HIGH"
                alert_reason.append(f"Heavy selling: {(1-buy_ratio)*100:.0f}%")
            
            # Check whale activity
            if len(large_trades) >= 3:
                if not alert_level:
                    alert_level = "MEDIUM"
                alert_reason.append(f"Whale activity: {len(large_trades)} large trades")
            
            return {
                'symbol': self.symbol,
                'price': current_price,
                'price_change_5m': price_change_5m,
                'volume_ratio': volume_ratio,
                'current_volume': current_vol,
                'avg_volume': avg_vol,
                'buy_volume': buy_volume,
                'sell_volume': sell_volume,
                'buy_ratio': buy_ratio,
                'large_trades': large_trades,
                'alert_level': alert_level,
                'alert_reason': alert_reason,
                'timestamp': datetime.now()
            }
            
        except Exception as e:
            logger.error(f"Error analyzing {self.symbol}: {e}")
            return None


async def monitor_symbols(symbols: List[str], update_interval: int = 30):
    """Monitor multiple symbols"""
    # Create analyzers
    analyzers = {symbol: SimpleVolumeAnalyzer(symbol) for symbol in symbols}
    
    print("\n" + "="*80)
    print(f"VOLUME MONITOR - Monitoring {len(symbols)} symbols")
    print(f"Update interval: {update_interval} seconds")
    print("="*80 + "\n")
    
    iteration = 0
    while True:
        iteration += 1
        start_time = time.time()
        
        # Clear screen for clean display
        if iteration > 1:
            print("\033[H\033[J", end='')  # Clear screen
        
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Update #{iteration}")
        print("-" * 80)
        
        # Analyze all symbols
        alerts = []
        normal_updates = []
        
        for symbol, analyzer in analyzers.items():
            result = analyzer.analyze()
            if result:
                if result['alert_level']:
                    alerts.append(result)
                else:
                    normal_updates.append(result)
        
        # Show alerts first
        if alerts:
            print("\n🚨 ALERTS:")
            for alert in sorted(alerts, key=lambda x: ['MEDIUM', 'HIGH', 'EXTREME'].index(x['alert_level'])):
                print(f"\n{alert['symbol']} - {alert['alert_level']} ALERT")
                print(f"  Price: ${alert['price']:.6f} ({alert['price_change_5m']:+.2f}% 5m)")
                print(f"  Volume: {alert['volume_ratio']:.1f}x average")
                print(f"  Buy/Sell: {alert['buy_ratio']*100:.0f}%/{(1-alert['buy_ratio'])*100:.0f}%")
                if alert['buy_volume'] > 0:
                    print(f"  Volume $: Buy ${alert['buy_volume']:,.0f} | Sell ${alert['sell_volume']:,.0f}")
                for reason in alert['alert_reason']:
                    print(f"  ⚠️  {reason}")
                if alert['large_trades']:
                    print(f"  🐋 {len(alert['large_trades'])} whale trades detected")
        
        # Show normal updates (condensed)
        if normal_updates:
            print("\n📊 Normal Activity:")
            print(f"{'Symbol':<15} {'Price':>10} {'5m%':>8} {'Vol Ratio':>10} {'Buy%':>8}")
            print("-" * 60)
            for update in sorted(normal_updates, key=lambda x: x['volume_ratio'], reverse=True):
                print(f"{update['symbol']:<15} "
                      f"${update['price']:>9.6f} "
                      f"{update['price_change_5m']:>7.2f}% "
                      f"{update['volume_ratio']:>9.1f}x "
                      f"{update['buy_ratio']*100:>7.0f}%")
        
        # Stats
        process_time = time.time() - start_time
        print(f"\n⏱️  Processed {len(symbols)} symbols in {process_time:.2f}s")
        
        # Wait for next update
        await asyncio.sleep(update_interval)


async def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description='Simple Volume Monitor - Real-time buy/sell volume analysis'
    )
    
    parser.add_argument('symbols', nargs='*', help='Symbols to monitor')
    parser.add_argument('--interval', '-i', type=int, default=30, 
                       help='Update interval in seconds (default: 30)')
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
        # Default high volatility symbols
        symbols = ['AIXBT_USDT', 'FIS_USDT', 'ZORA_USDT', 'SUPRA_USDT', 'USUAL_USDT']
    
    # Validate symbols
    valid_symbols = []
    for s in symbols:
        s = s.upper().strip()
        if not s.endswith('_USDT'):
            s += '_USDT'
        valid_symbols.append(s)
    
    try:
        await monitor_symbols(valid_symbols, args.interval)
    except KeyboardInterrupt:
        print("\n\nMonitor stopped by user")
    except Exception as e:
        print(f"\nError: {e}")


if __name__ == "__main__":
    asyncio.run(main())