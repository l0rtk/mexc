import requests
import time
import hashlib
import hmac
from typing import Dict, List, Optional, Any
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class MEXCFuturesClient:
    BASE_URL = "https://contract.mexc.com"

    def __init__(self, access_key: str = None, secret_key: str = None):
        self.access_key = access_key
        self.secret_key = secret_key
        self.session = requests.Session()
        self.session.headers.update({
            'Content-Type': 'application/json',
            'User-Agent': 'MEXC-Futures-Monitor/1.0'
        })

    def _sign_request(self, params: Dict[str, Any]) -> Dict[str, Any]:
        if not self.access_key or not self.secret_key:
            return params

        params['api_key'] = self.access_key
        params['req_time'] = str(int(time.time() * 1000))

        query_string = '&'.join([f"{k}={v}" for k, v in sorted(params.items())])
        signature = hmac.new(
            self.secret_key.encode('utf-8'),
            query_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

        params['sign'] = signature
        return params

    def get_active_contracts(self) -> List[Dict]:
        try:
            response = self.session.get(f"{self.BASE_URL}/api/v1/contract/detail")
            response.raise_for_status()
            data = response.json()

            if data.get('success'):
                contracts = data.get('data', [])
                return [c for c in contracts if c.get('state') == 1]
            return []
        except Exception as e:
            logger.error(f"Error fetching contracts: {e}")
            return []

    def get_order_book(self, symbol: str, limit: int = 20) -> Dict:
        try:
            params = {'symbol': symbol, 'limit': limit}
            response = self.session.get(
                f"{self.BASE_URL}/api/v1/contract/depth/{symbol}",
                params=params
            )
            response.raise_for_status()
            data = response.json()

            if data.get('success'):
                return data.get('data', {})
            return {}
        except Exception as e:
            logger.error(f"Error fetching order book for {symbol}: {e}")
            return {}

    def get_recent_trades(self, symbol: str, limit: int = 100) -> List[Dict]:
        try:
            response = self.session.get(
                f"{self.BASE_URL}/api/v1/contract/deals/{symbol}",
                params={'limit': limit}
            )
            response.raise_for_status()
            data = response.json()

            if data.get('success'):
                return data.get('data', [])
            return []
        except Exception as e:
            logger.error(f"Error fetching trades for {symbol}: {e}")
            return []

    def get_ticker(self, symbol: str) -> Dict:
        try:
            response = self.session.get(
                f"{self.BASE_URL}/api/v1/contract/ticker",
                params={'symbol': symbol}
            )
            response.raise_for_status()
            data = response.json()

            if data.get('success'):
                return data.get('data', {})
            return {}
        except Exception as e:
            logger.error(f"Error fetching ticker for {symbol}: {e}")
            return {}

    def get_klines(self, symbol: str, interval: str = '1m', limit: int = 100) -> List[List]:
        try:
            interval_map = {
                '1m': 'Min1',
                '5m': 'Min5',
                '15m': 'Min15',
                '30m': 'Min30',
                '1h': 'Min60',
                '4h': 'Hour4',
                '1d': 'Day1'
            }

            params = {
                'symbol': symbol,
                'interval': interval_map.get(interval, 'Min1'),
                'limit': limit
            }

            response = self.session.get(
                f"{self.BASE_URL}/api/v1/contract/kline/{symbol}",
                params=params
            )
            response.raise_for_status()
            data = response.json()

            if data.get('success'):
                return data.get('data', {}).get('time', [])
            return []
        except Exception as e:
            logger.error(f"Error fetching klines for {symbol}: {e}")
            return []

    def get_funding_rate(self, symbol: str) -> Dict:
        try:
            response = self.session.get(
                f"{self.BASE_URL}/api/v1/contract/funding_rate/{symbol}"
            )
            response.raise_for_status()
            data = response.json()

            if data.get('success'):
                return data.get('data', {})
            return {}
        except Exception as e:
            logger.error(f"Error fetching funding rate for {symbol}: {e}")
            return {}