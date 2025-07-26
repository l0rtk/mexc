#!/usr/bin/env python3
"""
Analyze collected data to find profitable manipulation patterns
"""

import os
import sys
from datetime import datetime, timedelta, timezone
from collections import defaultdict
import numpy as np
import pandas as pd
import pymongo
from dotenv import load_dotenv
import json

# Load environment
load_dotenv('../.env')

# MongoDB connection
MONGODB_URI = os.getenv('MONGODB_URI', 'mongodb://localhost:27017/')
DATABASE_NAME = os.getenv('DATABASE_NAME', 'mexc')


class PatternAnalyzer:
    """Analyze historical data for manipulation patterns"""
    
    def __init__(self):
        self.client = pymongo.MongoClient(MONGODB_URI)
        self.db = self.client[DATABASE_NAME]
        
    def analyze_pump_patterns(self):
        """Find successful pump patterns in historical data"""
        print("\n🔍 Analyzing Pump Patterns...")
        
        # Query for high volume spikes
        pipeline = [
            {
                '$match': {
                    'volume_analysis.spike_magnitude': {'$gt': 2},
                    'timestamp': {'$gte': datetime.now(timezone.utc) - timedelta(days=7)}
                }
            },
            {
                '$sort': {'timestamp': 1}
            },
            {
                '$group': {
                    '_id': '$symbol',
                    'events': {
                        '$push': {
                            'timestamp': '$timestamp',
                            'price': '$ohlcv.close',
                            'volume': '$ohlcv.volume',
                            'spike_magnitude': '$volume_analysis.spike_magnitude',
                            'price_change_5m': '$price_movement.change_5m',
                            'rsi': '$indicators.rsi_14'
                        }
                    }
                }
            }
        ]
        
        results = list(self.db.multi_pair_monitoring.aggregate(pipeline))
        
        successful_pumps = []
        failed_pumps = []
        
        for symbol_data in results:
            symbol = symbol_data['_id']
            events = symbol_data['events']
            
            # Analyze each spike event
            for i, event in enumerate(events):
                if event['spike_magnitude'] > 3:
                    # Look at price action after the spike
                    future_events = [e for e in events[i+1:i+10] if e]  # Next 10 data points
                    
                    if future_events:
                        initial_price = event['price']
                        max_price = max([e['price'] for e in future_events])
                        min_price = min([e['price'] for e in future_events])
                        
                        pump_gain = ((max_price - initial_price) / initial_price) * 100
                        dump_loss = ((min_price - initial_price) / initial_price) * 100
                        
                        pattern = {
                            'symbol': symbol,
                            'timestamp': event['timestamp'],
                            'initial_price': initial_price,
                            'spike_magnitude': event['spike_magnitude'],
                            'price_change_5m': event['price_change_5m'],
                            'rsi': event['rsi'],
                            'pump_gain': pump_gain,
                            'dump_loss': dump_loss,
                            'success': pump_gain > 5  # 5% gain = successful pump
                        }
                        
                        if pattern['success']:
                            successful_pumps.append(pattern)
                        else:
                            failed_pumps.append(pattern)
        
        print(f"\n✅ Successful Pumps: {len(successful_pumps)}")
        print(f"❌ Failed Pumps: {len(failed_pumps)}")
        
        if successful_pumps:
            # Analyze characteristics of successful pumps
            df = pd.DataFrame(successful_pumps)
            
            print("\n📊 Successful Pump Characteristics:")
            print(f"Average spike magnitude: {df['spike_magnitude'].mean():.2f}x")
            print(f"Average initial price change: {df['price_change_5m'].mean():.2f}%")
            print(f"Average RSI before pump: {df['rsi'].mean():.1f}")
            print(f"Average pump gain: {df['pump_gain'].mean():.2f}%")
            
            # Find optimal thresholds
            print("\n🎯 Optimal Signal Thresholds:")
            print(f"Volume spike > {df['spike_magnitude'].quantile(0.25):.1f}x")
            print(f"Price change > {df['price_change_5m'].quantile(0.25):.1f}%")
            print(f"RSI < {df['rsi'].quantile(0.75):.0f} (for oversold pumps)")
        
        return successful_pumps, failed_pumps
    
    def analyze_manipulation_patterns(self):
        """Analyze manipulation detection accuracy"""
        print("\n🎭 Analyzing Manipulation Detection...")
        
        # Get alerts
        alerts = list(self.db.alerts.find({
            'detected_at': {'$gte': datetime.now(timezone.utc) - timedelta(days=7)}
        }).sort('detected_at', 1))
        
        print(f"\nTotal alerts: {len(alerts)}")
        
        # Group by risk level
        risk_levels = defaultdict(list)
        for alert in alerts:
            risk_levels[alert.get('risk_level', 'UNKNOWN')].append(alert)
        
        for level, alerts_list in risk_levels.items():
            print(f"{level}: {len(alerts_list)} alerts")
        
        # Analyze alert outcomes
        profitable_alerts = []
        
        for alert in alerts:
            symbol = alert['symbol']
            alert_time = alert['detected_at']
            
            # Get price action after alert
            future_data = list(self.db.multi_pair_monitoring.find({
                'symbol': symbol,
                'timestamp': {
                    '$gte': alert_time,
                    '$lte': alert_time + timedelta(minutes=30)
                }
            }).sort('timestamp', 1))
            
            if future_data:
                initial_price = alert['snapshot']['price']
                prices = [d['ohlcv']['close'] for d in future_data]
                max_price = max(prices)
                
                profit = ((max_price - initial_price) / initial_price) * 100
                
                if profit > 2:  # 2% profit threshold
                    profitable_alerts.append({
                        'symbol': symbol,
                        'risk_level': alert['risk_level'],
                        'profit': profit,
                        'patterns': alert.get('patterns', {})
                    })
        
        if profitable_alerts:
            print(f"\n💰 Profitable alerts: {len(profitable_alerts)} / {len(alerts)}")
            print(f"Success rate: {(len(profitable_alerts) / len(alerts)) * 100:.1f}%")
        
        return profitable_alerts
    
    def analyze_order_book_patterns(self):
        """Analyze order book manipulation patterns"""
        print("\n📚 Analyzing Order Book Patterns...")
        
        # Query for order book anomalies
        pipeline = [
            {
                '$match': {
                    'order_book': {'$exists': True},
                    'order_book.spoofing_score': {'$gt': 0.3},
                    'timestamp': {'$gte': datetime.now(timezone.utc) - timedelta(days=7)}
                }
            },
            {
                '$project': {
                    'symbol': 1,
                    'timestamp': 1,
                    'price': '$ohlcv.close',
                    'spoofing_score': '$order_book.spoofing_score',
                    'spread_bps': '$order_book.spread_bps',
                    'liquidity_score': '$order_book.liquidity_score',
                    'price_change': '$price_movement.change_5m'
                }
            }
        ]
        
        spoofing_events = list(self.db.enhanced_monitoring.aggregate(pipeline))
        
        if spoofing_events:
            df = pd.DataFrame(spoofing_events)
            
            print(f"\n🚨 Spoofing Events: {len(spoofing_events)}")
            print(f"Average spoofing score: {df['spoofing_score'].mean():.2f}")
            print(f"Average spread during spoofing: {df['spread_bps'].mean():.1f} bps")
            
            # Correlation with price movement
            correlation = df['spoofing_score'].corr(df['price_change'])
            print(f"Correlation with price change: {correlation:.3f}")
        
        return spoofing_events
    
    def find_optimal_signals(self):
        """Find the most profitable signal combinations"""
        print("\n🎯 Finding Optimal Signal Combinations...")
        
        # Get all monitoring data with multiple signals
        pipeline = [
            {
                '$match': {
                    'timestamp': {'$gte': datetime.now(timezone.utc) - timedelta(days=7)},
                    '$or': [
                        {'volume_analysis.spike_magnitude': {'$gt': 2}},
                        {'indicators.rsi_14': {'$lt': 30}},
                        {'indicators.rsi_14': {'$gt': 70}},
                        {'price_movement.change_5m': {'$abs': {'$gt': 2}}}
                    ]
                }
            },
            {
                '$sort': {'timestamp': 1}
            }
        ]
        
        events = list(self.db.multi_pair_monitoring.aggregate(pipeline))
        
        # Analyze signal combinations
        signal_combinations = defaultdict(list)
        
        for event in events:
            signals = []
            
            # Volume signal
            if event.get('volume_analysis', {}).get('spike_magnitude', 0) > 2:
                signals.append(f"VOL>{event['volume_analysis']['spike_magnitude']:.1f}x")
            
            # RSI signal
            rsi = event.get('indicators', {}).get('rsi_14')
            if rsi and rsi < 30:
                signals.append(f"RSI<30({rsi:.0f})")
            elif rsi and rsi > 70:
                signals.append(f"RSI>70({rsi:.0f})")
            
            # Price movement signal
            price_change = event.get('price_movement', {}).get('change_5m', 0)
            if abs(price_change) > 2:
                signals.append(f"PRICE{'+' if price_change > 0 else ''}{price_change:.1f}%")
            
            if signals:
                key = " + ".join(sorted(signals[:2]))  # Max 2 signals
                signal_combinations[key].append(event)
        
        # Calculate profitability for each combination
        print("\n📈 Signal Combination Performance:")
        results = []
        
        for combination, events in signal_combinations.items():
            if len(events) >= 3:  # Minimum sample size
                avg_price_change = np.mean([e.get('price_movement', {}).get('change_5m', 0) for e in events])
                count = len(events)
                
                results.append({
                    'combination': combination,
                    'count': count,
                    'avg_move': avg_price_change
                })
        
        # Sort by average move
        results.sort(key=lambda x: abs(x['avg_move']), reverse=True)
        
        for result in results[:10]:
            print(f"{result['combination']}: {result['count']} events, avg move: {result['avg_move']:+.2f}%")
        
        return results
    
    def generate_recommendations(self):
        """Generate recommendations for better signals"""
        print("\n💡 RECOMMENDATIONS FOR BETTER SIGNALS:")
        
        pumps, _ = self.analyze_pump_patterns()
        
        if pumps:
            # Calculate optimal thresholds
            df = pd.DataFrame(pumps)
            successful_df = df[df['success'] == True]
            
            print("\n1. Volume-Based Signals:")
            print(f"   - Primary: Volume spike > {successful_df['spike_magnitude'].quantile(0.5):.1f}x")
            print(f"   - Confirmation: Price change > {successful_df['price_change_5m'].quantile(0.5):.1f}%")
            
            print("\n2. RSI-Based Signals:")
            oversold_pumps = successful_df[successful_df['rsi'] < 35]
            if len(oversold_pumps) > 0:
                print(f"   - Oversold bounce: RSI < {oversold_pumps['rsi'].max():.0f}")
                print(f"   - Success rate: {(len(oversold_pumps) / len(successful_df)) * 100:.1f}%")
            
            print("\n3. Combined Signals (Higher Confidence):")
            print("   - Volume > 4x + Price > 3% + RSI < 30 = Strong Buy")
            print("   - Volume > 5x + Price > 5% = Pump Alert")
            print("   - RSI > 80 + Volume > 3x = Dump Warning")
            
            print("\n4. Risk Management:")
            print(f"   - Average pump duration: ~5-15 minutes")
            print(f"   - Take profit: {successful_df['pump_gain'].quantile(0.75):.1f}%")
            print(f"   - Stop loss: {abs(successful_df['dump_loss'].quantile(0.25)):.1f}%")


def main():
    """Run pattern analysis"""
    analyzer = PatternAnalyzer()
    
    print("="*60)
    print("MEXC FUTURES PATTERN ANALYSIS")
    print("="*60)
    
    try:
        # Run analyses
        analyzer.analyze_pump_patterns()
        analyzer.analyze_manipulation_patterns()
        analyzer.analyze_order_book_patterns()
        optimal_signals = analyzer.find_optimal_signals()
        analyzer.generate_recommendations()
        
        # Save results
        results = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'optimal_signals': optimal_signals[:10] if optimal_signals else []
        }
        
        with open('pattern_analysis_results.json', 'w') as f:
            json.dump(results, f, indent=2)
        
        print("\n✅ Analysis complete! Results saved to pattern_analysis_results.json")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()