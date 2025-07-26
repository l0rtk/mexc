"""
Funding rate analysis for MEXC futures
Tracks funding rates, trends, and arbitrage opportunities
"""

import os
import time
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple
import numpy as np
from pymongo import MongoClient, DESCENDING
import requests

from logging_config import get_logger

logger = get_logger(__name__)


class FundingAnalyzer:
    """Analyzes funding rates for arbitrage opportunities"""
    
    def __init__(self, db_connection):
        self.db = db_connection
        self.base_url = "https://contract.mexc.com"
        self.session = requests.Session()
        
        # Funding happens every 8 hours (00:00, 08:00, 16:00 UTC)
        self.funding_interval = 8 * 3600  # 8 hours in seconds
        
        # Cache for funding data
        self.funding_cache = {}
        self.cache_duration = 300  # 5 minutes
        
    def get_hours_to_funding(self) -> float:
        """Calculate hours until next funding payment"""
        now = datetime.now(timezone.utc)
        hour = now.hour
        
        # Funding times: 0, 8, 16
        if hour < 8:
            next_funding = now.replace(hour=8, minute=0, second=0, microsecond=0)
        elif hour < 16:
            next_funding = now.replace(hour=16, minute=0, second=0, microsecond=0)
        else:
            # Next funding is at 00:00 tomorrow
            next_funding = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        
        time_diff = (next_funding - now).total_seconds() / 3600
        return round(time_diff, 2)
    
    def fetch_funding_rate(self, symbol: str) -> Optional[Dict]:
        """Fetch current funding rate with caching"""
        # Check cache
        if symbol in self.funding_cache:
            cached_data, cache_time = self.funding_cache[symbol]
            if time.time() - cache_time < self.cache_duration:
                return cached_data
        
        endpoint = f"/api/v1/contract/funding_rate/{symbol}"
        
        try:
            response = self.session.get(f"{self.base_url}{endpoint}", timeout=5)
            response.raise_for_status()
            
            data = response.json()
            if data.get('success'):
                funding_data = data.get('data', {})
                # Handle different response formats
                if 'data' in funding_data:
                    funding_data = funding_data['data']
                
                # Try different field names
                funding_rate = funding_data.get('fundingRate') or funding_data.get('funding_rate') or funding_data.get('rate') or 0
                if isinstance(funding_rate, str):
                    funding_rate = float(funding_rate)
                elif funding_rate is None:
                    funding_rate = 0
                    
                result = {
                    'symbol': symbol,
                    'timestamp': datetime.now(timezone.utc),
                    'funding_rate': float(funding_rate),
                    'max_funding_rate': float(funding_data.get('maxFundingRate', 0)),
                    'hours_to_funding': self.get_hours_to_funding()
                }
                
                # Cache the result
                self.funding_cache[symbol] = (result, time.time())
                
                return result
            else:
                logger.debug(f"Funding API returned unsuccessful response for {symbol}: {data}")
                # Return empty funding data instead of None to prevent KeyError
                return {
                    'symbol': symbol,
                    'timestamp': datetime.now(timezone.utc),
                    'funding_rate': 0.0,
                    'max_funding_rate': 0.0,
                    'hours_to_funding': 8.0
                }
                
        except Exception as e:
            logger.debug(f"Error fetching funding rate for {symbol}: {e}")
            # Return empty funding data instead of None
            return {
                'symbol': symbol,
                'timestamp': datetime.now(timezone.utc),
                'funding_rate': 0.0,
                'max_funding_rate': 0.0,
                'hours_to_funding': 8.0
            }
    
    def get_funding_history(self, symbol: str, hours: int = 24) -> List[Dict]:
        """Get funding rate history from database"""
        try:
            since = datetime.now(timezone.utc) - timedelta(hours=hours)
            
            cursor = self.db.db.funding_history.find(
                {
                    'symbol': symbol,
                    'timestamp': {'$gte': since}
                }
            ).sort('timestamp', DESCENDING)
            
            return list(cursor)
        except Exception as e:
            logger.error(f"Error fetching funding history: {e}")
            return []
    
    def calculate_funding_trend(self, symbol: str) -> Dict:
        """Calculate funding rate trend and statistics"""
        # Get 24h history
        history = self.get_funding_history(symbol, hours=24)
        
        if len(history) < 3:  # Need at least 3 data points
            return {
                'trend': 'unknown',
                'avg_24h': 0,
                'current_vs_avg': 0,
                'volatility': 0
            }
        
        rates = [h['funding_rate'] for h in history]
        current_rate = rates[0] if rates else 0
        
        # Calculate statistics
        avg_rate = np.mean(rates)
        std_rate = np.std(rates)
        
        # Determine trend
        recent_rates = rates[:3]  # Last 3 readings
        older_rates = rates[3:6] if len(rates) > 6 else rates[3:]
        
        if not older_rates:
            trend = 'stable'
        else:
            recent_avg = np.mean(recent_rates)
            older_avg = np.mean(older_rates)
            
            if recent_avg > older_avg * 1.2:
                trend = 'increasing'
            elif recent_avg < older_avg * 0.8:
                trend = 'decreasing'
            else:
                trend = 'stable'
        
        return {
            'trend': trend,
            'avg_24h': round(avg_rate, 6),
            'current_vs_avg': round((current_rate - avg_rate) / avg_rate * 100, 2) if avg_rate else 0,
            'volatility': round(std_rate, 6),
            'current_rate': current_rate
        }
    
    def calculate_funding_arbitrage_score(self, funding_data: Dict, market_data: Dict) -> float:
        """
        Calculate arbitrage opportunity score (0-1)
        High score = good opportunity to collect funding
        """
        funding_rate = funding_data.get('funding_rate', 0)
        hours_to_funding = funding_data.get('hours_to_funding', 8)
        
        # Base score from funding rate magnitude
        # 0.1% funding = 0.3% daily = significant
        if funding_rate > 0:  # Longs pay shorts
            base_score = min(abs(funding_rate) / 0.002, 1.0)  # Cap at 0.2%
            favorable_position = 'short'
        else:  # Shorts pay longs
            base_score = min(abs(funding_rate) / 0.002, 1.0)
            favorable_position = 'long'
        
        # Adjust for time to funding (prefer closer to funding time)
        time_multiplier = 1.0
        if hours_to_funding < 1:
            time_multiplier = 1.5  # Very close to funding
        elif hours_to_funding < 2:
            time_multiplier = 1.3
        elif hours_to_funding < 4:
            time_multiplier = 1.1
        elif hours_to_funding > 6:
            time_multiplier = 0.8  # Too far away
        
        # Adjust for market conditions
        market_multiplier = 1.0
        rsi = market_data.get('indicators', {}).get('rsi_14', 50)
        
        if favorable_position == 'short' and rsi > 70:
            market_multiplier = 1.3  # Overbought, good for shorts
        elif favorable_position == 'long' and rsi < 30:
            market_multiplier = 1.3  # Oversold, good for longs
        elif (favorable_position == 'short' and rsi < 30) or (favorable_position == 'long' and rsi > 70):
            market_multiplier = 0.7  # Against market momentum
        
        # Calculate final score
        arb_score = base_score * time_multiplier * market_multiplier
        
        return min(round(arb_score, 2), 1.0)
    
    def analyze_funding(self, symbol: str, market_data: Dict) -> Dict:
        """Complete funding analysis for a symbol"""
        # Fetch current funding
        funding_data = self.fetch_funding_rate(symbol)
        if not funding_data:
            return {}
        
        # Validate funding_data has required fields
        if 'funding_rate' not in funding_data:
            logger.debug(f"Invalid funding data for {symbol}: {funding_data}")
            return {}
            
        # Calculate trend
        trend_data = self.calculate_funding_trend(symbol)
        
        # Calculate arbitrage score
        arb_score = self.calculate_funding_arbitrage_score(funding_data, market_data)
        
        # Store in database
        funding_record = {
            'symbol': symbol,
            'timestamp': datetime.now(timezone.utc),
            'funding_rate': funding_data.get('funding_rate', 0),  # Changed from current_rate to funding_rate
            'hours_to_funding': funding_data.get('hours_to_funding', 8),
            'trend': trend_data['trend'],
            'avg_24h': trend_data['avg_24h'],
            'current_vs_avg': trend_data['current_vs_avg'],
            'arbitrage_score': arb_score
        }
        
        try:
            self.db.db.funding_history.insert_one(funding_record)
        except Exception as e:
            logger.error(f"Error storing funding data: {e}")
        
        return {
            'current_rate': funding_data['funding_rate'],
            'rate_trend': trend_data['trend'],
            'hours_to_funding': funding_data['hours_to_funding'],
            'funding_arb_score': arb_score,
            'avg_24h_rate': trend_data['avg_24h'],
            'rate_vs_average': trend_data['current_vs_avg'],
            'favorable_position': 'short' if funding_data['funding_rate'] > 0 else 'long'
        }
    
    def get_extreme_funding_pairs(self, threshold: float = 0.001) -> List[Dict]:
        """Find pairs with extreme funding rates"""
        extreme_pairs = []
        
        # Get all active symbols from database
        try:
            # Get unique symbols from recent market data
            pipeline = [
                {
                    '$match': {
                        'timestamp': {
                            '$gte': datetime.now(timezone.utc) - timedelta(minutes=10)
                        }
                    }
                },
                {
                    '$group': {
                        '_id': '$symbol'
                    }
                }
            ]
            
            symbols = [doc['_id'] for doc in self.db.db.multi_pair_monitoring.aggregate(pipeline)]
            
            for symbol in symbols:
                funding_data = self.fetch_funding_rate(symbol)
                if funding_data and abs(funding_data['funding_rate']) >= threshold:
                    extreme_pairs.append({
                        'symbol': symbol,
                        'funding_rate': funding_data['funding_rate'],
                        'hours_to_funding': funding_data['hours_to_funding'],
                        'daily_rate': funding_data['funding_rate'] * 3  # 3 funding periods per day
                    })
            
            # Sort by absolute funding rate
            extreme_pairs.sort(key=lambda x: abs(x['funding_rate']), reverse=True)
            
        except Exception as e:
            logger.error(f"Error finding extreme funding pairs: {e}")
        
        return extreme_pairs


# Indexes for funding collection
def setup_funding_indexes(db):
    """Create indexes for funding data collection"""
    try:
        # Funding history indexes
        db.db.funding_history.create_index([("symbol", 1), ("timestamp", -1)])
        db.db.funding_history.create_index([("timestamp", -1)])
        db.db.funding_history.create_index([("arbitrage_score", -1)])
        
        # TTL index to clean old data (30 days)
        db.db.funding_history.create_index(
            [("timestamp", 1)], 
            expireAfterSeconds=30*24*3600
        )
        
        logger.info("Funding indexes created successfully")
    except Exception as e:
        logger.error(f"Error creating funding indexes: {e}")