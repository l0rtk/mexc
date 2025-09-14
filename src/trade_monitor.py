import logging
from typing import Dict, List, Optional
from dataclasses import dataclass
from datetime import datetime, timedelta
import statistics
from collections import deque

logger = logging.getLogger(__name__)


@dataclass
class LargeTrade:
    symbol: str
    side: str
    price: float
    volume: float
    volume_usdt: float
    timestamp: datetime
    trade_id: str
    is_whale: bool
    volume_percentile: float


class TradeMonitor:
    def __init__(self, min_trade_usdt: float = 25000, whale_threshold_usdt: float = 100000):
        self.min_trade_usdt = min_trade_usdt
        self.whale_threshold_usdt = whale_threshold_usdt
        self.trade_history = {}
        self.volume_stats = {}
        self.recent_trades_window = 300

    def analyze_trades(self, symbol: str, trades: List[Dict]) -> List[LargeTrade]:
        large_trades = []

        if not trades:
            return large_trades

        for trade in trades:
            try:
                price = float(trade.get('p', 0))
                volume = float(trade.get('v', 0))
                volume_usdt = price * volume

                if volume_usdt >= self.min_trade_usdt:
                    side = 'BUY' if trade.get('T') == 1 else 'SELL'
                    is_whale = volume_usdt >= self.whale_threshold_usdt

                    percentile = self._calculate_volume_percentile(symbol, volume_usdt)

                    large_trades.append(LargeTrade(
                        symbol=symbol,
                        side=side,
                        price=price,
                        volume=volume,
                        volume_usdt=volume_usdt,
                        timestamp=datetime.fromtimestamp(trade.get('t', 0) / 1000),
                        trade_id=str(trade.get('id', '')),
                        is_whale=is_whale,
                        volume_percentile=percentile
                    ))
            except (KeyError, ValueError, TypeError) as e:
                logger.debug(f"Error parsing trade: {e}")
                continue

        return large_trades

    def _calculate_volume_percentile(self, symbol: str, volume_usdt: float) -> float:
        if symbol not in self.volume_stats:
            return 50.0

        volumes = self.volume_stats[symbol].get('volumes', [])
        if not volumes:
            return 50.0

        below_count = sum(1 for v in volumes if v < volume_usdt)
        percentile = (below_count / len(volumes)) * 100
        return percentile

    def update_volume_statistics(self, symbol: str, trades: List[Dict]):
        if symbol not in self.volume_stats:
            self.volume_stats[symbol] = {
                'volumes': deque(maxlen=1000),
                'last_update': datetime.now()
            }

        for trade in trades:
            try:
                price = float(trade.get('p', 0))
                volume = float(trade.get('v', 0))
                volume_usdt = price * volume
                self.volume_stats[symbol]['volumes'].append(volume_usdt)
            except (KeyError, ValueError, TypeError):
                continue

        self.volume_stats[symbol]['last_update'] = datetime.now()

    def detect_aggressive_trading(self, symbol: str, trades: List[Dict], time_window: int = 60) -> Dict:
        if not trades:
            return {}

        current_time = datetime.now()
        cutoff_time = current_time - timedelta(seconds=time_window)

        buy_volume = 0
        sell_volume = 0
        buy_count = 0
        sell_count = 0
        total_volume = 0

        for trade in trades:
            try:
                trade_time = datetime.fromtimestamp(trade.get('t', 0) / 1000)
                if trade_time < cutoff_time:
                    continue

                price = float(trade.get('p', 0))
                volume = float(trade.get('v', 0))
                volume_usdt = price * volume
                side = 'BUY' if trade.get('T') == 1 else 'SELL'

                total_volume += volume_usdt

                if side == 'BUY':
                    buy_volume += volume_usdt
                    buy_count += 1
                else:
                    sell_volume += volume_usdt
                    sell_count += 1
            except (KeyError, ValueError, TypeError):
                continue

        if total_volume == 0:
            return {}

        buy_percentage = (buy_volume / total_volume) * 100
        sell_percentage = (sell_volume / total_volume) * 100

        aggression_score = abs(buy_percentage - 50)

        return {
            'symbol': symbol,
            'buy_volume_usdt': buy_volume,
            'sell_volume_usdt': sell_volume,
            'buy_count': buy_count,
            'sell_count': sell_count,
            'buy_percentage': buy_percentage,
            'sell_percentage': sell_percentage,
            'aggression_score': aggression_score,
            'dominant_side': 'BUY' if buy_volume > sell_volume else 'SELL',
            'time_window': time_window
        }

    def detect_volume_surge(self, symbol: str, trades: List[Dict], baseline_minutes: int = 5) -> Optional[Dict]:
        if symbol not in self.trade_history:
            self.trade_history[symbol] = deque(maxlen=baseline_minutes * 60)

        current_minute_volume = 0
        current_time = datetime.now()
        one_minute_ago = current_time - timedelta(minutes=1)

        for trade in trades:
            try:
                trade_time = datetime.fromtimestamp(trade.get('t', 0) / 1000)
                if trade_time >= one_minute_ago:
                    price = float(trade.get('p', 0))
                    volume = float(trade.get('v', 0))
                    current_minute_volume += price * volume
            except (KeyError, ValueError, TypeError):
                continue

        self.trade_history[symbol].append(current_minute_volume)

        if len(self.trade_history[symbol]) < baseline_minutes:
            return None

        recent_volumes = list(self.trade_history[symbol])[-baseline_minutes:]
        avg_volume = statistics.mean(recent_volumes[:-1]) if len(recent_volumes) > 1 else 0

        if avg_volume == 0:
            return None

        surge_multiplier = current_minute_volume / avg_volume if avg_volume > 0 else 0

        if surge_multiplier >= 2.0:
            return {
                'symbol': symbol,
                'current_volume': current_minute_volume,
                'average_volume': avg_volume,
                'surge_multiplier': surge_multiplier,
                'baseline_minutes': baseline_minutes,
                'timestamp': current_time
            }

        return None

    def identify_coordinated_trades(self, symbol: str, trades: List[Dict],
                                   time_threshold: int = 5, volume_threshold: float = 0.9) -> List[Dict]:
        if not trades or len(trades) < 2:
            return []

        coordinated_groups = []
        processed_indices = set()

        for i in range(len(trades)):
            if i in processed_indices:
                continue

            try:
                base_trade = trades[i]
                base_time = base_trade.get('t', 0)
                base_price = float(base_trade.get('p', 0))
                base_volume = float(base_trade.get('v', 0))
                base_side = 'BUY' if base_trade.get('T') == 1 else 'SELL'

                group = [base_trade]
                group_volume = base_price * base_volume

                for j in range(i + 1, len(trades)):
                    if j in processed_indices:
                        continue

                    compare_trade = trades[j]
                    compare_time = compare_trade.get('t', 0)
                    compare_price = float(compare_trade.get('p', 0))
                    compare_volume = float(compare_trade.get('v', 0))
                    compare_side = 'BUY' if compare_trade.get('T') == 1 else 'SELL'

                    time_diff = abs(compare_time - base_time) / 1000

                    if (time_diff <= time_threshold and
                        compare_side == base_side and
                        abs(compare_price - base_price) / base_price <= 0.001):

                        group.append(compare_trade)
                        group_volume += compare_price * compare_volume
                        processed_indices.add(j)

                if len(group) >= 3 and group_volume >= self.min_trade_usdt:
                    processed_indices.add(i)
                    coordinated_groups.append({
                        'symbol': symbol,
                        'side': base_side,
                        'trade_count': len(group),
                        'total_volume_usdt': group_volume,
                        'avg_price': base_price,
                        'time_span': time_threshold,
                        'timestamp': datetime.fromtimestamp(base_time / 1000)
                    })

            except (KeyError, ValueError, TypeError) as e:
                logger.debug(f"Error processing trade group: {e}")
                continue

        return coordinated_groups