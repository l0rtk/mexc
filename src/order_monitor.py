import logging
import time
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from datetime import datetime
import statistics

logger = logging.getLogger(__name__)


@dataclass
class LargeOrder:
    symbol: str
    side: str
    price: float
    volume: float
    volume_usdt: float
    timestamp: datetime
    order_type: str
    percentage_of_book: float
    is_whale: bool = False


class OrderBookMonitor:
    def __init__(self, min_order_usdt: float = 50000, whale_threshold_usdt: float = 100000):
        self.min_order_usdt = min_order_usdt
        self.whale_threshold_usdt = whale_threshold_usdt
        self.order_history = {}
        self.volume_thresholds = {}

    def analyze_order_book(self, symbol: str, order_book: Dict) -> List[LargeOrder]:
        large_orders = []

        if not order_book:
            return large_orders

        bids = order_book.get('bids', [])
        asks = order_book.get('asks', [])

        if not bids or not asks:
            return large_orders

        total_bid_volume = sum(float(bid[1]) for bid in bids[:20])
        total_ask_volume = sum(float(ask[1]) for ask in asks[:20])

        for bid in bids[:10]:
            price = float(bid[0])
            volume = float(bid[1])
            volume_usdt = price * volume

            if volume_usdt >= self.min_order_usdt:
                percentage = (volume / total_bid_volume * 100) if total_bid_volume > 0 else 0

                large_orders.append(LargeOrder(
                    symbol=symbol,
                    side='BUY',
                    price=price,
                    volume=volume,
                    volume_usdt=volume_usdt,
                    timestamp=datetime.now(),
                    order_type='LIMIT',
                    percentage_of_book=percentage,
                    is_whale=volume_usdt >= self.whale_threshold_usdt
                ))

        for ask in asks[:10]:
            price = float(ask[0])
            volume = float(ask[1])
            volume_usdt = price * volume

            if volume_usdt >= self.min_order_usdt:
                percentage = (volume / total_ask_volume * 100) if total_ask_volume > 0 else 0

                large_orders.append(LargeOrder(
                    symbol=symbol,
                    side='SELL',
                    price=price,
                    volume=volume,
                    volume_usdt=volume_usdt,
                    timestamp=datetime.now(),
                    order_type='LIMIT',
                    percentage_of_book=percentage,
                    is_whale=volume_usdt >= self.whale_threshold_usdt
                ))

        return large_orders

    def detect_walls(self, symbol: str, order_book: Dict, threshold_multiplier: float = 3.0) -> List[Dict]:
        walls = []

        if not order_book:
            return walls

        bids = order_book.get('bids', [])
        asks = order_book.get('asks', [])

        bid_volumes = [float(bid[1]) for bid in bids[:20]] if bids else []
        ask_volumes = [float(ask[1]) for ask in asks[:20]] if asks else []

        if bid_volumes and len(bid_volumes) > 1:
            avg_bid_volume = statistics.mean(bid_volumes[1:])
            for i, bid in enumerate(bids[:10]):
                price = float(bid[0])
                volume = float(bid[1])

                if volume > avg_bid_volume * threshold_multiplier:
                    walls.append({
                        'symbol': symbol,
                        'type': 'BUY_WALL',
                        'price': price,
                        'volume': volume,
                        'volume_usdt': price * volume,
                        'multiplier': volume / avg_bid_volume if avg_bid_volume > 0 else 0,
                        'position': i + 1
                    })

        if ask_volumes and len(ask_volumes) > 1:
            avg_ask_volume = statistics.mean(ask_volumes[1:])
            for i, ask in enumerate(asks[:10]):
                price = float(ask[0])
                volume = float(ask[1])

                if volume > avg_ask_volume * threshold_multiplier:
                    walls.append({
                        'symbol': symbol,
                        'type': 'SELL_WALL',
                        'price': price,
                        'volume': volume,
                        'volume_usdt': price * volume,
                        'multiplier': volume / avg_ask_volume if avg_ask_volume > 0 else 0,
                        'position': i + 1
                    })

        return walls

    def calculate_order_book_imbalance(self, order_book: Dict, depth: int = 10) -> float:
        if not order_book:
            return 0.0

        bids = order_book.get('bids', [])[:depth]
        asks = order_book.get('asks', [])[:depth]

        total_bid_volume = sum(float(bid[0]) * float(bid[1]) for bid in bids)
        total_ask_volume = sum(float(ask[0]) * float(ask[1]) for ask in asks)

        total_volume = total_bid_volume + total_ask_volume

        if total_volume == 0:
            return 0.0

        imbalance = (total_bid_volume - total_ask_volume) / total_volume * 100
        return imbalance

    def detect_spoofing(self, symbol: str, order_book: Dict, time_window: int = 60) -> List[Dict]:
        if symbol not in self.order_history:
            self.order_history[symbol] = []

        current_large_orders = self.analyze_order_book(symbol, order_book)

        self.order_history[symbol].append({
            'timestamp': time.time(),
            'orders': current_large_orders
        })

        cutoff_time = time.time() - time_window
        self.order_history[symbol] = [
            entry for entry in self.order_history[symbol]
            if entry['timestamp'] > cutoff_time
        ]

        spoofing_patterns = []

        if len(self.order_history[symbol]) >= 3:
            order_counts = {}

            for entry in self.order_history[symbol]:
                for order in entry['orders']:
                    key = (order.side, round(order.price, 2))
                    if key not in order_counts:
                        order_counts[key] = {'count': 0, 'volumes': []}
                    order_counts[key]['count'] += 1
                    order_counts[key]['volumes'].append(order.volume_usdt)

            for key, data in order_counts.items():
                if data['count'] >= 3:
                    avg_volume = statistics.mean(data['volumes'])
                    volume_variation = statistics.stdev(data['volumes']) if len(data['volumes']) > 1 else 0

                    if volume_variation > avg_volume * 0.5:
                        spoofing_patterns.append({
                            'side': key[0],
                            'price': key[1],
                            'appearances': data['count'],
                            'avg_volume_usdt': avg_volume,
                            'volume_variation': volume_variation,
                            'pattern': 'POTENTIAL_SPOOFING'
                        })

        return spoofing_patterns