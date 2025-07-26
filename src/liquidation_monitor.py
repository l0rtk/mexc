"""
Liquidation monitoring and cascade detection
Tracks liquidation volumes and predicts cascade events
"""

import os
import time
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple
import numpy as np
from pymongo import MongoClient, DESCENDING
import requests
import aiohttp
import asyncio

from logging_config import get_logger

logger = get_logger(__name__)


class LiquidationMonitor:
    """Monitors liquidations and detects cascade risks"""
    
    def __init__(self, db_connection):
        self.db = db_connection
        self.base_url = "https://contract.mexc.com"
        self.session = requests.Session()
        
        # Cache for liquidation data
        self.liquidation_cache = {}
        self.cache_duration = 60  # 1 minute cache
        
        # Liquidation zones tracking
        self.liquidation_zones = {}
        
    async def fetch_liquidations_async(self, symbol: str) -> Optional[Dict]:
        """Fetch recent liquidations asynchronously"""
        endpoint = f"/api/v1/contract/liquidation/{symbol}"
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(f"{self.base_url}{endpoint}", timeout=5) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get('success'):
                            return self._process_liquidation_data(symbol, data.get('data', []))
                    return None
            except Exception as e:
                logger.error(f"Error fetching liquidations for {symbol}: {e}")
                return None
    
    def fetch_liquidations(self, symbol: str) -> Optional[Dict]:
        """Fetch recent liquidations (synchronous version)"""
        # Check cache first
        if symbol in self.liquidation_cache:
            cached_data, cache_time = self.liquidation_cache[symbol]
            if time.time() - cache_time < self.cache_duration:
                return cached_data
        
        endpoint = f"/api/v1/contract/liquidation/{symbol}"
        
        try:
            response = self.session.get(f"{self.base_url}{endpoint}", timeout=5)
            
            # Handle 404 - no liquidations endpoint, use alternative
            if response.status_code == 404:
                return self._estimate_liquidations_from_trades(symbol)
            
            response.raise_for_status()
            data = response.json()
            
            if data.get('success'):
                result = self._process_liquidation_data(symbol, data.get('data', []))
                self.liquidation_cache[symbol] = (result, time.time())
                return result
            
            return None
            
        except Exception as e:
            logger.debug(f"Liquidation API not available for {symbol}, using estimation")
            return self._estimate_liquidations_from_trades(symbol)
    
    def _estimate_liquidations_from_trades(self, symbol: str) -> Dict:
        """Estimate liquidations from large trades and price movements"""
        try:
            # Get recent price and volume data
            recent_data = list(self.db.db.multi_pair_monitoring.find(
                {'symbol': symbol},
                {'price_movement': 1, 'volume_analysis': 1, 'ohlcv': 1, 'timestamp': 1}
            ).sort('timestamp', DESCENDING).limit(60))
            
            if len(recent_data) < 10:
                return self._empty_liquidation_data()
            
            # Detect potential liquidations from price/volume spikes
            long_liquidations = 0
            short_liquidations = 0
            
            for i in range(1, len(recent_data)):
                current = recent_data[i-1]
                previous = recent_data[i]
                
                # Large volume spike with price movement
                vol_spike = current.get('volume_analysis', {}).get('spike_magnitude', 1)
                price_change = current.get('price_movement', {}).get('change_1m', 0)
                
                if vol_spike > 3:  # Significant volume
                    volume = current.get('ohlcv', {}).get('volume', 0)
                    
                    if price_change < -0.5:  # Sharp drop = long liquidations
                        long_liquidations += volume * 0.3  # Estimate 30% as liquidations
                    elif price_change > 0.5:  # Sharp rise = short liquidations
                        short_liquidations += volume * 0.3
            
            # Calculate metrics
            total_liquidations = long_liquidations + short_liquidations
            
            return {
                'symbol': symbol,
                'timestamp': datetime.now(timezone.utc),
                'long_liquidations_1h': round(long_liquidations, 2),
                'short_liquidations_1h': round(short_liquidations, 2),
                'total_liquidations_1h': round(total_liquidations, 2),
                'liquidation_ratio': round(long_liquidations / short_liquidations, 2) if short_liquidations > 0 else 10,
                'estimated': True
            }
            
        except Exception as e:
            logger.error(f"Error estimating liquidations: {e}")
            return self._empty_liquidation_data()
    
    def _empty_liquidation_data(self) -> Dict:
        """Return empty liquidation data structure"""
        return {
            'long_liquidations_1h': 0,
            'short_liquidations_1h': 0,
            'total_liquidations_1h': 0,
            'liquidation_ratio': 1,
            'estimated': True
        }
    
    def _process_liquidation_data(self, symbol: str, raw_data: List) -> Dict:
        """Process raw liquidation data"""
        now = datetime.now(timezone.utc)
        one_hour_ago = now - timedelta(hours=1)
        
        long_liquidations = 0
        short_liquidations = 0
        liquidation_prices = []
        
        for liq in raw_data:
            try:
                # Parse liquidation data
                timestamp = datetime.fromtimestamp(liq.get('timestamp', 0) / 1000, tz=timezone.utc)
                
                if timestamp >= one_hour_ago:
                    size = float(liq.get('size', 0))
                    price = float(liq.get('price', 0))
                    side = liq.get('side', '').lower()
                    
                    if side == 'buy' or side == 'long':
                        long_liquidations += size
                    else:
                        short_liquidations += size
                    
                    liquidation_prices.append(price)
                    
            except Exception as e:
                logger.error(f"Error processing liquidation entry: {e}")
                continue
        
        # Calculate metrics
        total_liquidations = long_liquidations + short_liquidations
        liquidation_ratio = long_liquidations / short_liquidations if short_liquidations > 0 else 10
        
        return {
            'symbol': symbol,
            'timestamp': now,
            'long_liquidations_1h': round(long_liquidations, 2),
            'short_liquidations_1h': round(short_liquidations, 2),
            'total_liquidations_1h': round(total_liquidations, 2),
            'liquidation_ratio': round(liquidation_ratio, 2),
            'liquidation_prices': liquidation_prices,
            'estimated': False
        }
    
    def calculate_cascade_probability(self, symbol: str, current_price: float, 
                                    liquidation_data: Dict, order_book: Dict = None) -> Dict:
        """Calculate probability of liquidation cascade"""
        long_liqs = liquidation_data.get('long_liquidations_1h', 0)
        short_liqs = liquidation_data.get('short_liquidations_1h', 0)
        ratio = liquidation_data.get('liquidation_ratio', 1)
        
        # Base probability from liquidation imbalance
        if ratio > 5:  # Heavy long liquidations
            base_prob = 0.7
            cascade_direction = 'down'
        elif ratio < 0.2:  # Heavy short liquidations
            base_prob = 0.7
            cascade_direction = 'up'
        elif ratio > 2:
            base_prob = 0.5
            cascade_direction = 'down'
        elif ratio < 0.5:
            base_prob = 0.5
            cascade_direction = 'up'
        else:
            base_prob = 0.3
            cascade_direction = 'neutral'
        
        # Adjust for order book (if available)
        if order_book:
            liquidity_score = order_book.get('liquidity_score', 1)
            
            # Low liquidity increases cascade risk
            if liquidity_score < 0.3:
                base_prob *= 1.5
            elif liquidity_score < 0.5:
                base_prob *= 1.2
        
        # Find nearest liquidation zone
        nearest_zone = self._find_nearest_liquidation_zone(symbol, current_price, cascade_direction)
        
        return {
            'cascade_probability': min(round(base_prob, 2), 0.95),
            'cascade_direction': cascade_direction,
            'nearest_liquidation_zone': nearest_zone,
            'risk_level': 'extreme' if base_prob > 0.7 else 'high' if base_prob > 0.5 else 'medium'
        }
    
    def _find_nearest_liquidation_zone(self, symbol: str, current_price: float, 
                                     direction: str) -> Optional[float]:
        """Find nearest significant liquidation zone"""
        try:
            # Get recent high/low points where liquidations occurred
            recent_data = list(self.db.db.multi_pair_monitoring.find(
                {
                    'symbol': symbol,
                    'volume_analysis.spike_magnitude': {'$gt': 3}
                },
                {'ohlcv': 1, 'price_movement': 1}
            ).sort('timestamp', DESCENDING).limit(100))
            
            if not recent_data:
                return None
            
            # Find price levels with high volume (potential liquidation zones)
            price_levels = []
            for data in recent_data:
                if abs(data.get('price_movement', {}).get('change_1m', 0)) > 1:
                    price = data.get('ohlcv', {}).get('close', 0)
                    if price > 0:
                        price_levels.append(price)
            
            if not price_levels:
                return None
            
            # Cluster price levels
            price_levels = sorted(price_levels)
            clusters = []
            current_cluster = [price_levels[0]]
            
            for price in price_levels[1:]:
                if price <= current_cluster[-1] * 1.005:  # Within 0.5%
                    current_cluster.append(price)
                else:
                    if len(current_cluster) >= 3:  # Significant cluster
                        clusters.append(np.mean(current_cluster))
                    current_cluster = [price]
            
            if len(current_cluster) >= 3:
                clusters.append(np.mean(current_cluster))
            
            if not clusters:
                return None
            
            # Find nearest cluster based on direction
            if direction == 'down':
                # Find nearest support below
                supports = [c for c in clusters if c < current_price * 0.99]
                return max(supports) if supports else None
            elif direction == 'up':
                # Find nearest resistance above
                resistances = [c for c in clusters if c > current_price * 1.01]
                return min(resistances) if resistances else None
            
            return None
            
        except Exception as e:
            logger.error(f"Error finding liquidation zones: {e}")
            return None
    
    def analyze_liquidation_risk(self, symbol: str, market_data: Dict, 
                               order_book: Dict = None) -> Dict:
        """Complete liquidation risk analysis"""
        # Fetch liquidation data
        liq_data = self.fetch_liquidations(symbol)
        if not liq_data:
            liq_data = self._empty_liquidation_data()
        
        # Get current price
        current_price = market_data.get('ohlcv', {}).get('close', 0)
        
        # Calculate cascade probability
        cascade_analysis = self.calculate_cascade_probability(
            symbol, current_price, liq_data, order_book
        )
        
        # Store in database
        risk_record = {
            'symbol': symbol,
            'timestamp': datetime.now(timezone.utc),
            'liquidations': liq_data,
            'cascade_analysis': cascade_analysis,
            'current_price': current_price
        }
        
        try:
            self.db.db.liquidation_risks.insert_one(risk_record)
        except Exception as e:
            logger.error(f"Error storing liquidation risk: {e}")
        
        return {
            'liquidation_pressure': {
                'long_liquidations_1h': liq_data['long_liquidations_1h'],
                'short_liquidations_1h': liq_data['short_liquidations_1h'],
                'liquidation_ratio': liq_data['liquidation_ratio'],
                'cascade_probability': cascade_analysis['cascade_probability'],
                'cascade_direction': cascade_analysis['cascade_direction'],
                'nearest_liquidation_zone': cascade_analysis['nearest_liquidation_zone'],
                'risk_level': cascade_analysis['risk_level']
            }
        }


# Indexes for liquidation data
def setup_liquidation_indexes(db):
    """Create indexes for liquidation data collection"""
    try:
        # Liquidation risks indexes
        db.db.liquidation_risks.create_index([("symbol", 1), ("timestamp", -1)])
        db.db.liquidation_risks.create_index([("timestamp", -1)])
        db.db.liquidation_risks.create_index([("cascade_analysis.cascade_probability", -1)])
        
        # TTL index to clean old data (7 days)
        db.db.liquidation_risks.create_index(
            [("timestamp", 1)], 
            expireAfterSeconds=7*24*3600
        )
        
        logger.info("Liquidation indexes created successfully")
    except Exception as e:
        logger.error(f"Error creating liquidation indexes: {e}")