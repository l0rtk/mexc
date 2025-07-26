"""
Alert prioritization system with intelligent filtering and performance tracking
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Set
from collections import defaultdict
import numpy as np

from logging_config import get_logger

logger = get_logger(__name__)


class AlertPrioritizer:
    """Intelligent alert filtering based on performance and market conditions"""
    
    def __init__(self, db_connection):
        self.db = db_connection
        
        # Performance tracking
        self.symbol_performance = defaultdict(lambda: {
            'total_alerts': 0,
            'successful_alerts': 0,
            'win_rate': 0.5,
            'last_alert_time': None,
            'recent_failures': []
        })
        
        # Alert history for pattern detection
        self.recent_alerts = defaultdict(list)  # symbol -> list of recent alerts
        self.alert_cooldowns = {}  # symbol -> cooldown end time
        
        # Load historical performance
        self._load_performance_history()
    
    def _load_performance_history(self):
        """Load historical alert performance from database"""
        try:
            # Get performance data from last 30 days
            since = datetime.now(timezone.utc) - timedelta(days=30)
            
            cursor = self.db.db.alert_performance.find(
                {'timestamp': {'$gte': since}}
            )
            
            for record in cursor:
                symbol = record['symbol']
                self.symbol_performance[symbol] = {
                    'total_alerts': record.get('total_alerts', 0),
                    'successful_alerts': record.get('successful_alerts', 0),
                    'win_rate': record.get('win_rate', 0.5),
                    'last_alert_time': record.get('last_alert_time'),
                    'recent_failures': record.get('recent_failures', [])
                }
            
            logger.info(f"Loaded performance history for {len(self.symbol_performance)} symbols")
            
        except Exception as e:
            logger.error(f"Error loading performance history: {e}")
    
    def calculate_alert_priority(self, alert_data: Dict, market_conditions: Dict = None) -> float:
        """
        Calculate priority score for an alert
        Higher score = higher priority = more likely to be sent
        """
        symbol = alert_data['symbol']
        base_confidence = alert_data.get('patterns', {}).get('confidence', 0.5)
        
        # Start with base confidence
        priority = base_confidence
        
        # Adjustments based on various factors
        adjustments = 0
        
        # 1. Symbol performance adjustment
        perf = self.symbol_performance[symbol]
        win_rate = perf['win_rate']
        
        if win_rate > 0.7:
            adjustments += 0.2  # High win rate symbol
        elif win_rate > 0.6:
            adjustments += 0.1
        elif win_rate < 0.3:
            adjustments -= 0.3  # Poor performing symbol
        elif win_rate < 0.4:
            adjustments -= 0.1
        
        # 2. Recent alert frequency
        if symbol not in self.recent_alerts or len(self.recent_alerts[symbol]) == 0:
            adjustments += 0.2  # No recent alerts, fresh opportunity
        elif len(self.recent_alerts[symbol]) > 5:
            adjustments -= 0.2  # Too many recent alerts
        
        # 3. Statistical significance (if available)
        if 'statistical_data' in alert_data:
            stats = alert_data['statistical_data']
            if stats.get('volume_zscore', 0) > 4:
                adjustments += 0.3  # Extreme volume outlier
            elif stats.get('volume_zscore', 0) > 3:
                adjustments += 0.2
            
            if stats.get('is_outlier'):
                adjustments += 0.1
        
        # 4. Funding opportunity
        if alert_data.get('patterns', {}).get('action', '').startswith('FUNDING'):
            funding_data = alert_data.get('funding_data', {})
            if funding_data:
                rate = abs(funding_data.get('current_rate', 0))
                if rate > 0.002:  # > 0.2%
                    adjustments += 0.3
                elif rate > 0.001:  # > 0.1%
                    adjustments += 0.2
        
        # 5. Liquidation risk
        if 'liquidation_data' in alert_data:
            liq = alert_data['liquidation_data']
            cascade_prob = liq.get('cascade_probability', 0)
            if cascade_prob > 0.8:
                adjustments += 0.3
            elif cascade_prob > 0.6:
                adjustments += 0.2
        
        # 6. Multi-signal confluence
        num_signals = alert_data.get('patterns', {}).get('num_signals', 0)
        if num_signals >= 4:
            adjustments += 0.2
        elif num_signals >= 3:
            adjustments += 0.1
        
        # 7. Recent failure penalty
        recent_failures = perf.get('recent_failures', [])
        if recent_failures:
            # Count failures in last 2 hours
            two_hours_ago = datetime.now(timezone.utc) - timedelta(hours=2)
            recent_fail_count = sum(1 for fail_time in recent_failures 
                                  if fail_time > two_hours_ago)
            
            if recent_fail_count >= 3:
                adjustments -= 0.4  # Multiple recent failures
            elif recent_fail_count >= 2:
                adjustments -= 0.2
        
        # 8. Market conditions adjustment
        if market_conditions:
            # Global market fear/greed can affect alert quality
            btc_trend = market_conditions.get('btc_trend', 'neutral')
            if btc_trend == 'strong_down' and alert_data.get('patterns', {}).get('action', '').endswith('BUY'):
                adjustments -= 0.2  # Don't fight the trend
            elif btc_trend == 'strong_up' and alert_data.get('patterns', {}).get('action', '').endswith('SELL'):
                adjustments -= 0.2
        
        # Calculate final priority
        priority = base_confidence * (1 + adjustments)
        
        # Ensure priority stays in reasonable bounds
        priority = max(0.1, min(priority, 1.5))
        
        return round(priority, 3)
    
    def should_send_alert(self, alert_data: Dict, priority: float, 
                         dynamic_threshold: float = 0.7) -> bool:
        """
        Determine if alert should be sent based on priority and cooldowns
        """
        symbol = alert_data['symbol']
        risk_level = alert_data.get('risk_level', 'MEDIUM')
        
        # Always send EXTREME alerts with very high priority
        if risk_level == 'EXTREME' and priority > 0.9:
            return True
        
        # Check cooldown
        if symbol in self.alert_cooldowns:
            if datetime.now(timezone.utc) < self.alert_cooldowns[symbol]:
                # Still in cooldown, need higher priority
                if priority < dynamic_threshold * 1.5:
                    return False
        
        # Check priority against threshold
        if priority < dynamic_threshold:
            return False
        
        # Additional checks for specific patterns
        action = alert_data.get('patterns', {}).get('action', '')
        
        # Funding alerts have different criteria
        if action.startswith('FUNDING'):
            funding_data = alert_data.get('funding_data', {})
            hours_to_funding = funding_data.get('hours_to_funding', 8)
            
            # Only send funding alerts close to funding time
            if hours_to_funding > 2:
                return False
        
        return True
    
    def update_alert_history(self, symbol: str, alert_data: Dict):
        """Update alert history after sending"""
        now = datetime.now(timezone.utc)
        
        # Add to recent alerts
        self.recent_alerts[symbol].append({
            'time': now,
            'action': alert_data.get('patterns', {}).get('action', ''),
            'confidence': alert_data.get('patterns', {}).get('confidence', 0),
            'priority': alert_data.get('priority', 0)
        })
        
        # Keep only last 10 alerts
        if len(self.recent_alerts[symbol]) > 10:
            self.recent_alerts[symbol] = self.recent_alerts[symbol][-10:]
        
        # Update cooldown based on risk level
        risk_level = alert_data.get('risk_level', 'MEDIUM')
        if risk_level == 'EXTREME':
            cooldown_minutes = 3
        elif risk_level == 'HIGH':
            cooldown_minutes = 5
        else:
            cooldown_minutes = 10
        
        self.alert_cooldowns[symbol] = now + timedelta(minutes=cooldown_minutes)
        
        # Update performance tracking
        self.symbol_performance[symbol]['total_alerts'] += 1
        self.symbol_performance[symbol]['last_alert_time'] = now
        
        # Store in database
        try:
            self.db.db.alert_history.insert_one({
                'symbol': symbol,
                'timestamp': now,
                'alert_data': alert_data,
                'priority': alert_data.get('priority', 0)
            })
        except Exception as e:
            logger.error(f"Error storing alert history: {e}")
    
    def track_alert_outcome(self, symbol: str, alert_time: datetime, 
                          outcome: str, max_move: float = None):
        """
        Track the outcome of an alert for performance feedback
        
        Args:
            symbol: Trading symbol
            alert_time: When alert was sent
            outcome: 'success', 'failure', 'neutral'
            max_move: Maximum price move after alert (percentage)
        """
        perf = self.symbol_performance[symbol]
        
        if outcome == 'success':
            perf['successful_alerts'] += 1
        elif outcome == 'failure':
            perf['recent_failures'].append(alert_time)
            # Keep only failures from last 24 hours
            cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
            perf['recent_failures'] = [t for t in perf['recent_failures'] if t > cutoff]
        
        # Update win rate
        if perf['total_alerts'] > 0:
            perf['win_rate'] = perf['successful_alerts'] / perf['total_alerts']
        
        # Store outcome in database
        try:
            self.db.db.alert_performance.update_one(
                {'symbol': symbol},
                {
                    '$set': {
                        'symbol': symbol,
                        'timestamp': datetime.now(timezone.utc),
                        'total_alerts': perf['total_alerts'],
                        'successful_alerts': perf['successful_alerts'],
                        'win_rate': perf['win_rate'],
                        'last_alert_time': perf['last_alert_time'],
                        'recent_failures': perf['recent_failures']
                    }
                },
                upsert=True
            )
            
            # Also store individual outcome
            self.db.db.alert_outcomes.insert_one({
                'symbol': symbol,
                'alert_time': alert_time,
                'outcome_time': datetime.now(timezone.utc),
                'outcome': outcome,
                'max_move': max_move
            })
            
        except Exception as e:
            logger.error(f"Error tracking alert outcome: {e}")
    
    def get_alert_statistics(self, symbol: str = None) -> Dict:
        """Get alert performance statistics"""
        if symbol:
            perf = self.symbol_performance[symbol]
            return {
                'symbol': symbol,
                'total_alerts': perf['total_alerts'],
                'win_rate': round(perf['win_rate'], 3),
                'last_alert': perf['last_alert_time'],
                'recent_alert_count': len(self.recent_alerts.get(symbol, []))
            }
        else:
            # Global statistics
            total_alerts = sum(p['total_alerts'] for p in self.symbol_performance.values())
            total_wins = sum(p['successful_alerts'] for p in self.symbol_performance.values())
            
            return {
                'total_symbols': len(self.symbol_performance),
                'total_alerts_sent': total_alerts,
                'global_win_rate': round(total_wins / total_alerts, 3) if total_alerts > 0 else 0,
                'active_cooldowns': len(self.alert_cooldowns)
            }


# Setup indexes for alert tracking
def setup_alert_indexes(db):
    """Create indexes for alert performance tracking"""
    try:
        # Alert history
        db.db.alert_history.create_index([("symbol", 1), ("timestamp", -1)])
        db.db.alert_history.create_index([("timestamp", -1)])
        
        # Alert performance
        db.db.alert_performance.create_index([("symbol", 1)])
        db.db.alert_performance.create_index([("win_rate", -1)])
        
        # Alert outcomes
        db.db.alert_outcomes.create_index([("symbol", 1), ("alert_time", -1)])
        db.db.alert_outcomes.create_index([("outcome", 1)])
        
        # TTL for old alert history (30 days)
        db.db.alert_history.create_index(
            [("timestamp", 1)], 
            expireAfterSeconds=30*24*3600
        )
        
        logger.info("Alert indexes created successfully")
    except Exception as e:
        logger.error(f"Error creating alert indexes: {e}")