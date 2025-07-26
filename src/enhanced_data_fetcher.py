import requests
import json
from datetime import datetime, timezone
import time
from typing import Dict, List, Optional, Tuple
import numpy as np
import logging
from logging_config import get_logger

logger = get_logger(__name__)


class EnhancedDataFetcher:
    """Enhanced fetcher with order book, trade flow, and advanced analysis"""
    
    def __init__(self, symbol: str):
        self.symbol = symbol
        self.base_url = "https://contract.mexc.com"
        self.session = requests.Session()
        self.session.timeout = 5  # 5 second timeout
        
        # Cache for recent data
        self.recent_trades = []
        self.max_trades = 100
        
    def fetch_order_book(self, depth: int = 20) -> Dict:
        """
        Fetch order book depth data
        
        Args:
            depth: Number of price levels to fetch (max 20)
        """
        endpoint = f"/api/v1/contract/depth/{self.symbol}"
        params = {"limit": depth}
        
        try:
            response = self.session.get(f"{self.base_url}{endpoint}", params=params, timeout=5)
            response.raise_for_status()
            
            data = response.json()
            if data.get('success'):
                book_data = data.get('data', {})
                
                # Process order book
                bids = book_data.get('bids', [])
                asks = book_data.get('asks', [])
                
                if not bids or not asks:
                    return {}
                
                # Calculate metrics
                best_bid = float(bids[0][0]) if bids else 0
                best_ask = float(asks[0][0]) if asks else 0
                spread = best_ask - best_bid
                spread_bps = (spread / best_bid * 10000) if best_bid > 0 else 0
                
                # Calculate depth within 10 basis points
                bid_depth_10bps = sum(float(bid[1]) for bid in bids 
                                     if float(bid[0]) >= best_bid * 0.999)
                ask_depth_10bps = sum(float(ask[1]) for ask in asks 
                                     if float(ask[0]) <= best_ask * 1.001)
                
                # Detect order book imbalance
                total_bid_size = sum(float(bid[1]) for bid in bids[:5])
                total_ask_size = sum(float(ask[1]) for ask in asks[:5])
                imbalance_ratio = total_bid_size / total_ask_size if total_ask_size > 0 else 0
                
                # Detect potential spoofing (large orders far from best price)
                spoofing_score = self._calculate_spoofing_score(bids, asks)
                
                return {
                    'timestamp': datetime.now(timezone.utc),
                    'best_bid': best_bid,
                    'best_ask': best_ask,
                    'spread': spread,
                    'spread_bps': round(spread_bps, 1),
                    'bid_depth_10bps': bid_depth_10bps,
                    'ask_depth_10bps': ask_depth_10bps,
                    'bid_count': len(bids),
                    'ask_count': len(asks),
                    'imbalance_ratio': round(imbalance_ratio, 2),
                    'spoofing_score': round(spoofing_score, 2),
                    'liquidity_score': self._calculate_liquidity_score(bids, asks),
                    'raw_bids': bids[:5],  # Top 5 levels
                    'raw_asks': asks[:5]
                }
            else:
                logger.error(f"Order book API error for {self.symbol}: {data.get('message', 'Unknown')}")
                return {}
                
        except Exception as e:
            logger.error(f"Error fetching order book for {self.symbol}: {e}", exc_info=True)
            return {}
    
    def fetch_recent_trades(self, limit: int = 100) -> List[Dict]:
        """Fetch recent trades to analyze trade flow"""
        endpoint = f"/api/v1/contract/deals/{self.symbol}"  # Use deals endpoint instead
        params = {"limit": limit}
        
        try:
            response = self.session.get(f"{self.base_url}{endpoint}", params=params, timeout=3)
            response.raise_for_status()
            
            data = response.json()
            if data.get('success'):
                trades = data.get('data', [])
                
                # Process trades (deals format)
                processed_trades = []
                for i, trade in enumerate(trades):
                    # Deals format: [timestamp, price, volume, side, id]
                    processed_trades.append({
                        'timestamp': datetime.fromtimestamp(trade[0] / 1000, tz=timezone.utc),
                        'price': float(trade[1]),
                        'volume': float(trade[2]),
                        'side': 'buy' if trade[3] == 1 else 'sell',
                        'trade_id': str(trade[4]) if len(trade) > 4 else str(i)
                    })
                
                # Update cache
                self.recent_trades = processed_trades[:self.max_trades]
                
                return processed_trades
            else:
                logger.error(f"Trades API error for {self.symbol}: {data.get('message', 'Unknown')}")
                return []
                
        except requests.exceptions.Timeout:
            logger.warning(f"Trades endpoint timed out for {self.symbol}, returning empty list")
            return []
        except Exception as e:
            logger.error(f"Error fetching trades for {self.symbol}: {e}", exc_info=True)
            return []
    
    def analyze_trade_flow(self, trades: List[Dict]) -> Dict:
        """Analyze trade flow for manipulation patterns"""
        if not trades:
            return {}
        
        # Separate buy and sell trades
        buy_trades = [t for t in trades if t['side'] == 'buy']
        sell_trades = [t for t in trades if t['side'] == 'sell']
        
        # Calculate volumes
        buy_volume = sum(t['volume'] for t in buy_trades)
        sell_volume = sum(t['volume'] for t in sell_trades)
        total_volume = buy_volume + sell_volume
        
        # Trade statistics
        trade_sizes = [t['volume'] for t in trades]
        avg_trade_size = np.mean(trade_sizes) if trade_sizes else 0
        max_trade_size = max(trade_sizes) if trade_sizes else 0
        
        # Detect wash trading patterns
        wash_score = self._detect_wash_trading(trades)
        
        # Calculate aggressor ratio
        aggressor_ratio = buy_volume / sell_volume if sell_volume > 0 else 0
        
        # Time clustering analysis
        time_diffs = []
        for i in range(1, len(trades)):
            diff = (trades[i-1]['timestamp'] - trades[i]['timestamp']).total_seconds()
            time_diffs.append(diff)
        
        avg_time_between_trades = np.mean(time_diffs) if time_diffs else 0
        
        return {
            'trade_count': len(trades),
            'buy_volume': round(buy_volume, 2),
            'sell_volume': round(sell_volume, 2),
            'net_flow': round(buy_volume - sell_volume, 2),
            'buy_count': len(buy_trades),
            'sell_count': len(sell_trades),
            'avg_trade_size': round(avg_trade_size, 2),
            'max_trade_size': round(max_trade_size, 2),
            'aggressor_ratio': round(aggressor_ratio, 2),
            'wash_trading_score': round(wash_score, 2),
            'avg_time_between_trades': round(avg_time_between_trades, 1),
            'volume_concentration': round(max_trade_size / total_volume, 2) if total_volume > 0 else 0
        }
    
    def fetch_open_interest(self) -> Dict:
        """Fetch open interest data"""
        endpoint = f"/api/v1/contract/open_interest/{self.symbol}"
        
        try:
            response = self.session.get(f"{self.base_url}{endpoint}", timeout=5)
            response.raise_for_status()
            
            data = response.json()
            if data.get('success'):
                oi_data = data.get('data', {})
                return {
                    'timestamp': datetime.now(timezone.utc),
                    'open_interest': float(oi_data.get('openInterest', 0)),
                    'open_interest_value': float(oi_data.get('openInterestValue', 0))
                }
            else:
                logger.error(f"Open interest API error: {data.get('message', 'Unknown')}")
                return {}
                
        except Exception as e:
            logger.error(f"Error fetching open interest: {e}")
            return {}
    
    def _calculate_spoofing_score(self, bids: List, asks: List) -> float:
        """Calculate probability of spoofing in order book"""
        if len(bids) < 5 or len(asks) < 5:
            return 0
        
        # Look for large orders away from best price
        best_bid = float(bids[0][0])
        best_ask = float(asks[0][0])
        
        # Check for unusually large orders beyond 0.5% from best price
        large_bid_score = 0
        large_ask_score = 0
        
        for bid in bids[2:]:  # Skip best 2 levels
            price = float(bid[0])
            size = float(bid[1])
            if price < best_bid * 0.995:  # More than 0.5% away
                if size > float(bids[0][1]) * 3:  # 3x best bid size
                    large_bid_score += 1
        
        for ask in asks[2:]:
            price = float(ask[0])
            size = float(ask[1])
            if price > best_ask * 1.005:
                if size > float(asks[0][1]) * 3:
                    large_ask_score += 1
        
        return min((large_bid_score + large_ask_score) / 10, 1.0)
    
    def _calculate_liquidity_score(self, bids: List, asks: List) -> float:
        """Calculate overall liquidity score (0-1)"""
        if not bids or not asks:
            return 0
        
        # Factor 1: Spread tightness
        spread = float(asks[0][0]) - float(bids[0][0])
        mid_price = (float(asks[0][0]) + float(bids[0][0])) / 2
        spread_score = max(0, 1 - (spread / mid_price * 100))  # Lower spread = higher score
        
        # Factor 2: Depth
        total_bid_depth = sum(float(bid[1]) for bid in bids[:5])
        total_ask_depth = sum(float(ask[1]) for ask in asks[:5])
        depth_score = min((total_bid_depth + total_ask_depth) / 10000, 1.0)  # Normalize
        
        # Factor 3: Level count
        level_score = min((len(bids) + len(asks)) / 40, 1.0)  # Max 20 each side
        
        return round((spread_score * 0.4 + depth_score * 0.4 + level_score * 0.2), 2)
    
    def _detect_wash_trading(self, trades: List[Dict]) -> float:
        """Detect wash trading patterns in recent trades"""
        if len(trades) < 10:
            return 0
        
        score = 0
        
        # Pattern 1: Identical trade sizes
        trade_sizes = [t['volume'] for t in trades[:20]]
        size_counts = {}
        for size in trade_sizes:
            size_counts[size] = size_counts.get(size, 0) + 1
        
        # If same size appears multiple times
        max_count = max(size_counts.values())
        if max_count >= 3:
            score += 0.3
        
        # Pattern 2: Rapid back-and-forth trading
        for i in range(2, min(10, len(trades))):
            if (trades[i]['side'] != trades[i-1]['side'] and 
                trades[i]['side'] == trades[i-2]['side'] and
                abs(trades[i]['volume'] - trades[i-2]['volume']) < 10):
                score += 0.2
        
        # Pattern 3: Round number trades
        round_trades = sum(1 for t in trades[:10] if t['volume'] % 100 == 0)
        if round_trades >= 5:
            score += 0.2
        
        return min(score, 1.0)
    
    def calculate_market_microstructure(self, order_book: Dict, trades: List[Dict]) -> Dict:
        """Calculate advanced market microstructure metrics"""
        if not order_book or not trades:
            return {}
        
        # Effective spread (actual execution cost)
        recent_trades = trades[:10]
        if recent_trades:
            mid_price = (order_book['best_bid'] + order_book['best_ask']) / 2
            effective_spreads = []
            for trade in recent_trades:
                if trade['side'] == 'buy':
                    effective_spread = (trade['price'] - mid_price) / mid_price * 2
                else:
                    effective_spread = (mid_price - trade['price']) / mid_price * 2
                effective_spreads.append(abs(effective_spread))
            
            avg_effective_spread = np.mean(effective_spreads) if effective_spreads else 0
        else:
            avg_effective_spread = order_book['spread_bps'] / 10000
        
        # Price impact estimation
        price_impact_100 = self._estimate_price_impact(order_book, 100)
        price_impact_1000 = self._estimate_price_impact(order_book, 1000)
        
        # Market resilience (how quickly price recovers)
        resilience = min(order_book['liquidity_score'] * 2, 1.0)
        
        # Toxicity score (probability of adverse selection)
        toxicity = 1 - resilience
        if order_book['imbalance_ratio'] > 2 or order_book['imbalance_ratio'] < 0.5:
            toxicity = min(toxicity + 0.3, 1.0)
        
        return {
            'effective_spread': round(avg_effective_spread * 10000, 1),  # in bps
            'price_impact_100_usd': round(price_impact_100, 2),
            'price_impact_1000_usd': round(price_impact_1000, 2),
            'resilience_score': round(resilience, 2),
            'toxicity_score': round(toxicity, 2)
        }
    
    def _estimate_price_impact(self, order_book: Dict, usd_amount: float) -> float:
        """Estimate price impact for a given USD amount"""
        if not order_book.get('raw_asks'):
            return 0
        
        mid_price = (order_book['best_bid'] + order_book['best_ask']) / 2
        remaining_amount = usd_amount
        executed_amount = 0
        weighted_price = 0
        
        # Walk through ask levels
        for ask in order_book['raw_asks']:
            price = float(ask[0])
            size = float(ask[1])
            level_value = price * size
            
            if remaining_amount <= level_value:
                # Partial fill at this level
                fill_size = remaining_amount / price
                weighted_price += price * fill_size
                executed_amount += fill_size
                break
            else:
                # Full fill at this level
                weighted_price += price * size
                executed_amount += size
                remaining_amount -= level_value
        
        if executed_amount > 0:
            avg_execution_price = weighted_price / executed_amount
            price_impact = ((avg_execution_price - mid_price) / mid_price) * 100
            return abs(price_impact)
        
        return 0