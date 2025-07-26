"""
Statistical analysis for detecting significant market movements
Uses Z-scores and rolling statistics for outlier detection
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple
import numpy as np
from collections import deque
from pymongo import DESCENDING

from logging_config import get_logger

logger = get_logger(__name__)


class StatisticalAnalyzer:
    """Performs statistical analysis on market data"""
    
    def __init__(self, db_connection):
        self.db = db_connection
        
        # Rolling statistics cache
        self.rolling_stats = {}
        self.window_size = 1440  # 24 hours of minutes
        
        # Market regime detection
        self.market_regimes = {}
        
    def update_rolling_statistics(self, symbol: str, market_data: Dict):
        """Update rolling statistics for a symbol"""
        if symbol not in self.rolling_stats:
            self.rolling_stats[symbol] = {
                'prices': deque(maxlen=self.window_size),
                'volumes': deque(maxlen=self.window_size),
                'price_changes': deque(maxlen=self.window_size),
                'last_update': datetime.now(timezone.utc)
            }
        
        stats = self.rolling_stats[symbol]
        
        # Add new data
        stats['prices'].append(market_data['ohlcv']['close'])
        stats['volumes'].append(market_data['ohlcv']['volume'])
        stats['price_changes'].append(market_data['price_movement']['change_1m'])
        stats['last_update'] = datetime.now(timezone.utc)
        
        # Initialize from database if needed
        if len(stats['prices']) < 100:
            self._initialize_from_database(symbol)
    
    def _initialize_from_database(self, symbol: str):
        """Initialize rolling statistics from historical data"""
        try:
            # Get last 24 hours of data
            since = datetime.now(timezone.utc) - timedelta(hours=24)
            
            cursor = self.db.db.multi_pair_monitoring.find(
                {
                    'symbol': symbol,
                    'timestamp': {'$gte': since}
                },
                {
                    'ohlcv.close': 1,
                    'ohlcv.volume': 1,
                    'price_movement.change_1m': 1
                }
            ).sort('timestamp', DESCENDING).limit(self.window_size)
            
            data = list(cursor)
            if len(data) > 100:
                stats = self.rolling_stats[symbol]
                
                # Prepend historical data (in reverse order)
                for doc in reversed(data[100:]):
                    stats['prices'].appendleft(doc['ohlcv']['close'])
                    stats['volumes'].appendleft(doc['ohlcv']['volume'])
                    stats['price_changes'].appendleft(doc['price_movement']['change_1m'])
                
                logger.info(f"Initialized {len(data)} historical points for {symbol}")
                
        except Exception as e:
            logger.error(f"Error initializing statistics for {symbol}: {e}")
    
    def calculate_zscore(self, symbol: str, market_data: Dict) -> Dict:
        """Calculate Z-scores for volume and price movements"""
        # Update rolling stats first
        self.update_rolling_statistics(symbol, market_data)
        
        if symbol not in self.rolling_stats:
            return {
                'volume_zscore': 0,
                'price_zscore': 0,
                'is_outlier': False,
                'confidence_multiplier': 1.0
            }
        
        stats = self.rolling_stats[symbol]
        
        # Need sufficient data
        if len(stats['volumes']) < 100:
            return {
                'volume_zscore': 0,
                'price_zscore': 0,
                'is_outlier': False,
                'confidence_multiplier': 1.0
            }
        
        # Calculate statistics
        volumes = np.array(stats['volumes'])
        price_changes = np.array(stats['price_changes'])
        
        # Volume Z-score
        current_volume = market_data['ohlcv']['volume']
        volume_mean = np.mean(volumes[:-1])  # Exclude current
        volume_std = np.std(volumes[:-1])
        
        if volume_std > 0:
            volume_zscore = (current_volume - volume_mean) / volume_std
        else:
            volume_zscore = 0
        
        # Price change Z-score
        current_change = market_data['price_movement']['change_1m']
        change_mean = np.mean(price_changes[:-1])
        change_std = np.std(price_changes[:-1])
        
        if change_std > 0:
            price_zscore = (current_change - change_mean) / change_std
        else:
            price_zscore = 0
        
        # Determine if outlier
        is_outlier = abs(volume_zscore) > 3 or abs(price_zscore) > 2.5
        
        # Calculate confidence multiplier
        confidence_multiplier = 1.0
        if abs(volume_zscore) > 4:
            confidence_multiplier *= 1.5
        elif abs(volume_zscore) > 3:
            confidence_multiplier *= 1.3
        elif abs(volume_zscore) > 2:
            confidence_multiplier *= 1.1
        
        if abs(price_zscore) > 3:
            confidence_multiplier *= 1.4
        elif abs(price_zscore) > 2:
            confidence_multiplier *= 1.2
        
        return {
            'volume_zscore': round(volume_zscore, 2),
            'price_zscore': round(price_zscore, 2),
            'is_outlier': is_outlier,
            'confidence_multiplier': round(min(confidence_multiplier, 2.0), 2),
            'volume_mean_24h': round(volume_mean, 2),
            'volume_std_24h': round(volume_std, 2),
            'price_change_mean_24h': round(change_mean, 4),
            'price_change_std_24h': round(change_std, 4)
        }
    
    def detect_market_regime(self, symbol: str) -> str:
        """Detect current market regime (trending/ranging/volatile)"""
        if symbol not in self.rolling_stats:
            return 'unknown'
        
        stats = self.rolling_stats[symbol]
        
        if len(stats['prices']) < 100:
            return 'unknown'
        
        prices = np.array(stats['prices'])
        
        # Calculate trend strength (using linear regression)
        x = np.arange(len(prices))
        slope, _ = np.polyfit(x, prices, 1)
        
        # Normalize slope by average price
        avg_price = np.mean(prices)
        normalized_slope = abs(slope) / avg_price * 100
        
        # Calculate volatility
        returns = np.diff(prices) / prices[:-1]
        volatility = np.std(returns) * 100
        
        # Calculate efficiency ratio (directional movement / total movement)
        price_change = abs(prices[-1] - prices[0])
        path_length = np.sum(np.abs(np.diff(prices)))
        efficiency = price_change / path_length if path_length > 0 else 0
        
        # Determine regime
        if normalized_slope > 0.1 and efficiency > 0.3:
            regime = 'trending'
        elif volatility > 2:
            regime = 'volatile'
        elif efficiency < 0.2:
            regime = 'ranging'
        else:
            regime = 'mixed'
        
        # Cache the result
        self.market_regimes[symbol] = {
            'regime': regime,
            'trend_strength': normalized_slope,
            'volatility': volatility,
            'efficiency': efficiency,
            'timestamp': datetime.now(timezone.utc)
        }
        
        return regime
    
    def calculate_dynamic_threshold(self, base_threshold: float, 
                                  market_regime: str, volatility: float) -> float:
        """Calculate dynamic threshold based on market conditions"""
        # ATR-based adjustment (simplified using volatility)
        volatility_multiplier = 1.0
        
        if volatility > 3:  # High volatility
            volatility_multiplier = 0.8  # Lower threshold
        elif volatility > 2:
            volatility_multiplier = 0.9
        elif volatility < 0.5:  # Low volatility
            volatility_multiplier = 1.2  # Higher threshold
        
        # Regime-based adjustment
        regime_multiplier = 1.0
        
        if market_regime == 'ranging':
            regime_multiplier = 0.85  # More sensitive in ranges
        elif market_regime == 'trending':
            regime_multiplier = 1.1  # Less sensitive in trends
        elif market_regime == 'volatile':
            regime_multiplier = 0.75  # Very sensitive in volatile markets
        
        # Calculate final threshold
        dynamic_threshold = base_threshold * volatility_multiplier * regime_multiplier
        
        return round(dynamic_threshold, 3)
    
    def analyze_statistics(self, symbol: str, market_data: Dict, 
                         base_confidence: float) -> Dict:
        """Complete statistical analysis with dynamic adjustments"""
        # Calculate Z-scores
        zscore_data = self.calculate_zscore(symbol, market_data)
        
        # Detect market regime
        regime = self.detect_market_regime(symbol)
        regime_data = self.market_regimes.get(symbol, {})
        
        # Calculate dynamic threshold
        volatility = regime_data.get('volatility', 1.0)
        dynamic_threshold = self.calculate_dynamic_threshold(0.7, regime, volatility)
        
        # Adjust confidence based on statistics
        adjusted_confidence = base_confidence * zscore_data['confidence_multiplier']
        
        # Determine if signal should trigger
        should_alert = adjusted_confidence >= dynamic_threshold
        
        return {
            'zscore': zscore_data,
            'market_regime': regime,
            'regime_details': regime_data,
            'dynamic_threshold': dynamic_threshold,
            'adjusted_confidence': round(adjusted_confidence, 3),
            'should_alert': should_alert,
            'statistical_significance': zscore_data['is_outlier']
        }
    
    def get_percentile_rank(self, symbol: str, value: float, 
                          metric: str = 'volume') -> float:
        """Get percentile rank of current value vs historical"""
        if symbol not in self.rolling_stats:
            return 50.0
        
        stats = self.rolling_stats[symbol]
        
        if metric == 'volume':
            data = stats['volumes']
        elif metric == 'price_change':
            data = stats['price_changes']
        else:
            return 50.0
        
        if len(data) < 100:
            return 50.0
        
        # Calculate percentile
        data_array = np.array(data)
        percentile = (np.sum(data_array <= value) / len(data_array)) * 100
        
        return round(percentile, 1)


# Statistical helper functions
def calculate_atr(prices: List[float], period: int = 14) -> float:
    """Calculate Average True Range"""
    if len(prices) < period + 1:
        return 0
    
    high_low = []
    for i in range(1, len(prices)):
        # Simplified ATR using just price changes
        high_low.append(abs(prices[i] - prices[i-1]))
    
    if len(high_low) >= period:
        return np.mean(high_low[-period:])
    
    return np.mean(high_low) if high_low else 0


def calculate_bollinger_bands(prices: List[float], period: int = 20, 
                            num_std: float = 2) -> Tuple[float, float, float]:
    """Calculate Bollinger Bands"""
    if len(prices) < period:
        return 0, 0, 0
    
    prices_array = np.array(prices[-period:])
    middle = np.mean(prices_array)
    std = np.std(prices_array)
    
    upper = middle + (std * num_std)
    lower = middle - (std * num_std)
    
    return round(upper, 6), round(middle, 6), round(lower, 6)