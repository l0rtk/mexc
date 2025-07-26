import os
import requests
import json
import hmac
import hashlib
from datetime import datetime, timedelta
import time
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlencode
import pandas as pd
import numpy as np
import logging

logger = logging.getLogger(__name__)


class SinglePairDataFetcher:
    """Fetches and analyzes data for a single MEXC futures trading pair"""
    
    def __init__(self, symbol: str):
        self.symbol = symbol
        self.base_url = "https://contract.mexc.com"
        self.session = requests.Session()
        self.candles_buffer = []  # Store recent candles for calculations
        self.max_buffer_size = 60  # Keep last 60 candles for 1-hour calculations
        
        # Load API credentials for better rate limits
        self.access_key = os.getenv('MEXC_ACCESS_KEY')
        self.secret_key = os.getenv('MEXC_SECRET_KEY')
        self.authenticated = bool(self.access_key and self.secret_key)
        
        if self.authenticated:
            logger.info(f"MEXC API authenticated mode enabled for {symbol}")
        
    def _generate_signature(self, params: Dict, timestamp: str) -> str:
        """Generate HMAC signature for authenticated requests"""
        sorted_params = sorted(params.items())
        query_string = urlencode(sorted_params)
        signature_string = f"{self.access_key}{timestamp}{query_string}"
        
        signature = hmac.new(
            self.secret_key.encode('utf-8'),
            signature_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        return signature
    
    def _make_request(self, endpoint: str, params: Dict = None) -> Dict:
        """Make API request with optional authentication"""
        if params is None:
            params = {}
        
        url = f"{self.base_url}{endpoint}"
        
        # Add authentication if available
        if self.authenticated:
            timestamp = str(int(time.time() * 1000))
            params['api_key'] = self.access_key
            params['req_time'] = timestamp
            params['sign'] = self._generate_signature(params, timestamp)
        
        response = self.session.get(url, params=params)
        response.raise_for_status()
        return response.json()
        
    def fetch_candles(self, interval: str = "Min1", limit: int = 60) -> List[Dict]:
        """
        Fetch kline/candle data for the symbol
        
        Args:
            interval: Time interval (Min1, Min5, Min15, Min30, Min60, etc.)
            limit: Number of candles to fetch (max 1000)
        
        Returns:
            List of candle dictionaries
        """
        endpoint = f"/api/v1/contract/kline/{self.symbol}"
        params = {
            "interval": interval,
            "limit": limit
        }
        
        try:
            logger.debug(f"[{self.symbol}] Fetching {limit} candles, interval={interval}")
            data = self._make_request(endpoint, params)
            if data.get('success'):
                candle_data = data.get('data', {})
                # Convert to more readable format
                formatted_candles = []
                
                # MEXC returns data as arrays for each field
                times = candle_data.get('time', [])
                opens = candle_data.get('open', [])
                highs = candle_data.get('high', [])
                lows = candle_data.get('low', [])
                closes = candle_data.get('close', [])
                volumes = candle_data.get('vol', [])
                amounts = candle_data.get('amount', [])  # Quote volume
                
                for i in range(len(times)):
                    formatted_candles.append({
                        'timestamp': datetime.fromtimestamp(times[i]),
                        'open': float(opens[i]),
                        'high': float(highs[i]),
                        'low': float(lows[i]),
                        'close': float(closes[i]),
                        'volume': float(volumes[i]),
                        'quote_volume': float(amounts[i]) if i < len(amounts) else 0
                    })
                return formatted_candles
            else:
                print(f"API error: {data.get('message', 'Unknown error')}")
                return []
                
        except Exception as e:
            print(f"Error fetching candles: {e}")
            return []
    
    def fetch_multi_timeframe(self) -> Dict[str, List[Dict]]:
        """
        Fetch candles for multiple timeframes
        
        Returns:
            Dictionary with timeframe as key and candles as value
        """
        timeframes = {
            '1m': ('Min1', 60),    # 60 1-minute candles
            '5m': ('Min5', 60),    # 60 5-minute candles (5 hours)
            '15m': ('Min15', 40),  # 40 15-minute candles (10 hours)
        }
        
        multi_tf_data = {}
        
        for tf_key, (interval, limit) in timeframes.items():
            try:
                candles = self.fetch_candles(interval=interval, limit=limit)
                if candles:
                    multi_tf_data[tf_key] = candles
                    logger.debug(f"[{self.symbol}] Fetched {len(candles)} candles for {tf_key}")
            except Exception as e:
                logger.error(f"Error fetching {tf_key} candles for {self.symbol}: {e}")
                multi_tf_data[tf_key] = []
        
        return multi_tf_data
    
    def detect_timeframe_divergence(self, multi_tf_data: Dict[str, List[Dict]]) -> Dict:
        """
        Detect divergences across timeframes
        
        Returns:
            Dictionary with divergence analysis
        """
        divergences = {
            'has_divergence': False,
            'divergence_type': None,
            'divergence_strength': 0,
            'details': {}
        }
        
        # Need all timeframes
        if not all(tf in multi_tf_data and len(multi_tf_data[tf]) > 0 for tf in ['1m', '5m', '15m']):
            return divergences
        
        try:
            # Get latest prices and calculate short-term trends
            trends = {}
            
            for tf in ['1m', '5m', '15m']:
                candles = multi_tf_data[tf]
                if len(candles) >= 5:
                    recent_prices = [c['close'] for c in candles[-5:]]
                    
                    # Simple trend: compare average of last 2 vs previous 3
                    recent_avg = np.mean(recent_prices[-2:])
                    older_avg = np.mean(recent_prices[:3])
                    
                    trend_pct = ((recent_avg - older_avg) / older_avg) * 100
                    trends[tf] = {
                        'direction': 'up' if trend_pct > 0 else 'down',
                        'strength': abs(trend_pct)
                    }
            
            # Check for divergences
            if len(trends) == 3:
                # Bullish divergence: higher TF down, lower TF up
                if (trends['15m']['direction'] == 'down' and 
                    trends['1m']['direction'] == 'up' and 
                    trends['1m']['strength'] > 1):
                    
                    divergences['has_divergence'] = True
                    divergences['divergence_type'] = 'bullish'
                    divergences['divergence_strength'] = trends['1m']['strength'] / max(trends['15m']['strength'], 0.1)
                    
                # Bearish divergence: higher TF up, lower TF down
                elif (trends['15m']['direction'] == 'up' and 
                      trends['1m']['direction'] == 'down' and 
                      trends['1m']['strength'] > 1):
                    
                    divergences['has_divergence'] = True
                    divergences['divergence_type'] = 'bearish'
                    divergences['divergence_strength'] = trends['1m']['strength'] / max(trends['15m']['strength'], 0.1)
                
                divergences['details'] = trends
                
        except Exception as e:
            logger.error(f"Error detecting timeframe divergence: {e}")
        
        return divergences
    
    def calculate_rsi(self, prices: List[float], period: int = 14) -> Optional[float]:
        """Calculate RSI (Relative Strength Index)"""
        if len(prices) < period + 1:
            return None
            
        prices_array = np.array(prices)
        deltas = np.diff(prices_array)
        gains = deltas.copy()
        losses = deltas.copy()
        
        gains[gains < 0] = 0
        losses[losses > 0] = 0
        losses = np.abs(losses)
        
        avg_gain = np.mean(gains[:period])
        avg_loss = np.mean(losses[:period])
        
        if avg_loss == 0:
            return 100
            
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        
        return round(rsi, 2)
    
    def analyze_candle_data(self, candles: List[Dict]) -> Dict:
        """
        Analyze candle data to calculate various metrics
        
        Returns:
            Dictionary with calculated metrics
        """
        if not candles:
            return {}
            
        current_candle = candles[-1]
        current_price = current_candle['close']
        current_volume = current_candle['volume']
        
        # Calculate volume averages
        volumes = [c['volume'] for c in candles]
        avg_volume_5m = float(np.mean(volumes[-5:])) if len(volumes) >= 5 else current_volume
        avg_volume_60m = float(np.mean(volumes)) if len(volumes) > 1 else current_volume
        
        # Volume ratios
        volume_ratio_5m = current_volume / avg_volume_5m if avg_volume_5m > 0 else 1
        volume_ratio_60m = current_volume / avg_volume_60m if avg_volume_60m > 0 else 1
        
        # Price changes
        prices = [c['close'] for c in candles]
        price_change_1m = ((current_price - prices[-2]) / prices[-2] * 100) if len(prices) > 1 else 0
        price_change_5m = ((current_price - prices[-6]) / prices[-6] * 100) if len(prices) > 5 else 0
        price_change_15m = ((current_price - prices[-16]) / prices[-16] * 100) if len(prices) > 15 else 0
        price_change_60m = ((current_price - prices[0]) / prices[0] * 100) if len(prices) > 1 else 0
        
        # High-low range
        high_low_range = ((current_candle['high'] - current_candle['low']) / current_candle['low'] * 100) if current_candle['low'] > 0 else 0
        
        # RSI
        rsi = self.calculate_rsi(prices) if len(prices) >= 15 else None
        
        # Momentum
        momentum_10 = (current_price / prices[-11]) if len(prices) > 10 else 1
        
        # Spike detection
        is_spike = bool(volume_ratio_5m > 3 or volume_ratio_60m > 3)
        spike_magnitude = max(volume_ratio_5m, volume_ratio_60m)
        
        return {
            'symbol': self.symbol,
            'timestamp': current_candle['timestamp'],
            'ohlcv': {
                'open': current_candle['open'],
                'high': current_candle['high'],
                'low': current_candle['low'],
                'close': current_candle['close'],
                'volume': current_candle['volume'],
                'quote_volume': current_candle['quote_volume']
            },
            'volume_analysis': {
                'avg_volume_5m': round(avg_volume_5m, 2),
                'avg_volume_60m': round(avg_volume_60m, 2),
                'volume_ratio_5m': round(volume_ratio_5m, 2),
                'volume_ratio_60m': round(volume_ratio_60m, 2),
                'is_spike': is_spike,
                'spike_magnitude': round(spike_magnitude, 2)
            },
            'price_movement': {
                'change_1m': round(price_change_1m, 2),
                'change_5m': round(price_change_5m, 2),
                'change_15m': round(price_change_15m, 2),
                'change_60m': round(price_change_60m, 2),
                'high_low_range': round(high_low_range, 2)
            },
            'indicators': {
                'rsi_14': rsi,
                'momentum_10': round(momentum_10, 3) if momentum_10 else None
            }
        }
    
    def fetch_funding_rate(self) -> Dict:
        """Fetch current funding rate for the symbol"""
        endpoint = f"/api/v1/contract/funding_rate/{self.symbol}"
        
        try:
            response = self.session.get(f"{self.base_url}{endpoint}")
            response.raise_for_status()
            
            data = response.json()
            if data.get('success'):
                funding_data = data.get('data', {})
                return {
                    'symbol': self.symbol,
                    'timestamp': datetime.now(),
                    'funding_rate': float(funding_data.get('fundingRate', 0)),
                    'max_funding_rate': float(funding_data.get('maxFundingRate', 0)),
                    'settlement_time': funding_data.get('settlementTime', 0)
                }
            else:
                print(f"API error: {data.get('message', 'Unknown error')}")
                return {}
                
        except Exception as e:
            print(f"Error fetching funding rate: {e}")
            return {}
    
    def monitor_realtime(self, duration_minutes: int = 5, callback=None):
        """
        Monitor the trading pair in real-time
        
        Args:
            duration_minutes: How long to monitor
            callback: Function to call with each analysis result
        """
        start_time = datetime.now()
        end_time = start_time + timedelta(minutes=duration_minutes)
        
        print(f"Starting real-time monitoring of {self.symbol} for {duration_minutes} minutes...")
        
        while datetime.now() < end_time:
            # Fetch latest candles
            candles = self.fetch_candles(limit=60)
            
            if candles:
                # Analyze the data
                analysis = self.analyze_candle_data(candles)
                
                # Check for interesting conditions
                if analysis.get('volume_analysis', {}).get('is_spike'):
                    print(f"\n🚨 VOLUME SPIKE DETECTED at {analysis['timestamp']}")
                    print(f"   Volume ratio 5m: {analysis['volume_analysis']['volume_ratio_5m']}x")
                    print(f"   Price change 5m: {analysis['price_movement']['change_5m']}%")
                    
                if analysis.get('indicators', {}).get('rsi_14'):
                    rsi = analysis['indicators']['rsi_14']
                    if rsi > 75:
                        print(f"\n📈 RSI OVERBOUGHT: {rsi}")
                    elif rsi < 25:
                        print(f"\n📉 RSI OVERSOLD: {rsi}")
                
                # Call callback if provided
                if callback:
                    callback(analysis)
                
                # Print summary every minute
                print(f"\r[{datetime.now().strftime('%H:%M:%S')}] "
                      f"Price: ${analysis['ohlcv']['close']:.4f} "
                      f"Vol Ratio: {analysis['volume_analysis']['volume_ratio_5m']:.1f}x "
                      f"5m Change: {analysis['price_movement']['change_5m']:+.2f}%", 
                      end='', flush=True)
            
            # Wait before next fetch (respecting rate limits)
            time.sleep(10)  # Fetch every 10 seconds
        
        print(f"\n\nMonitoring completed for {self.symbol}")


# Example usage
if __name__ == "__main__":
    # Pick a low-volume pair from previous analysis
    symbol = "ORDI_USDT"  # You can change this to any symbol
    
    fetcher = SinglePairDataFetcher(symbol)
    
    # Fetch initial data
    print(f"Fetching data for {symbol}...")
    candles = fetcher.fetch_candles(limit=60)
    
    if candles:
        # Analyze the data
        analysis = fetcher.analyze_candle_data(candles)
        
        # Pretty print the analysis
        print("\n=== Current Analysis ===")
        print(json.dumps(analysis, indent=2, default=str))
        
        # Fetch funding rate
        funding = fetcher.fetch_funding_rate()
        if funding:
            print("\n=== Funding Rate ===")
            print(json.dumps(funding, indent=2, default=str))
        
        # Optional: Start real-time monitoring
        # fetcher.monitor_realtime(duration_minutes=5)
    else:
        print(f"Failed to fetch data for {symbol}")