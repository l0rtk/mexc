#!/usr/bin/env python3
import os
import sys
import time
import logging
import argparse
from datetime import datetime
from typing import List, Dict
from dotenv import load_dotenv

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.mexc_client import MEXCFuturesClient
from src.order_monitor import OrderBookMonitor
from src.trade_monitor import TradeMonitor
from src.alert_system import AlertSystem

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

load_dotenv()


class MEXCFuturesMonitor:
    def __init__(self, symbols: List[str], config: Dict = None):
        self.symbols = symbols
        self.config = config or {}

        access_key = os.getenv('MEXC_ACCESS_KEY')
        secret_key = os.getenv('MEXC_SECRET_KEY')
        self.client = MEXCFuturesClient(access_key, secret_key)

        self.order_monitor = OrderBookMonitor(
            min_order_usdt=self.config.get('min_order_usdt', 50000),
            whale_threshold_usdt=self.config.get('whale_threshold_usdt', 100000)
        )

        self.trade_monitor = TradeMonitor(
            min_trade_usdt=self.config.get('min_trade_usdt', 25000),
            whale_threshold_usdt=self.config.get('whale_threshold_usdt', 100000)
        )

        self.alert_system = AlertSystem(
            enable_console=True,
            enable_file=self.config.get('log_alerts', False),
            enable_telegram=self.config.get('telegram', True)
        )

        self.update_interval = self.config.get('update_interval', 5)

    def monitor_symbol(self, symbol: str):
        try:
            order_book = self.client.get_order_book(symbol, limit=20)
            if order_book:
                large_orders = self.order_monitor.analyze_order_book(symbol, order_book)
                for order in large_orders:
                    if order.is_whale:
                        self.alert_system.send_alert('large_order', order, priority='HIGH')
                    else:
                        self.alert_system.send_alert('large_order', order, priority='MEDIUM')

                walls = self.order_monitor.detect_walls(symbol, order_book)
                for wall in walls:
                    self.alert_system.send_alert('wall', wall, priority='MEDIUM')

                imbalance = self.order_monitor.calculate_order_book_imbalance(order_book)
                if abs(imbalance) > 30:
                    logger.info(f"{symbol} Order Book Imbalance: {imbalance:.1f}%")

                spoofing = self.order_monitor.detect_spoofing(symbol, order_book)
                for spoof in spoofing:
                    self.alert_system.send_alert('spoofing', spoof, priority='HIGH')

            trades = self.client.get_recent_trades(symbol, limit=100)
            if trades:
                self.trade_monitor.update_volume_statistics(symbol, trades)

                large_trades = self.trade_monitor.analyze_trades(symbol, trades)
                for trade in large_trades:
                    if trade.is_whale:
                        self.alert_system.send_alert('large_order', trade, priority='HIGH')

                aggressive = self.trade_monitor.detect_aggressive_trading(symbol, trades)
                if aggressive and aggressive.get('aggression_score', 0) > 30:
                    self.alert_system.send_alert('aggressive_trading', aggressive, priority='MEDIUM')

                surge = self.trade_monitor.detect_volume_surge(symbol, trades)
                if surge:
                    self.alert_system.send_alert('volume_surge', surge, priority='HIGH')

                coordinated = self.trade_monitor.identify_coordinated_trades(symbol, trades)
                for coord in coordinated:
                    self.alert_system.send_alert('coordinated_trades', coord, priority='HIGH')

        except Exception as e:
            logger.error(f"Error monitoring {symbol}: {e}")

    def run(self):
        logger.info(f"Starting MEXC Futures Monitor for {len(self.symbols)} symbols")
        logger.info(f"Symbols: {', '.join(self.symbols)}")
        logger.info(f"Update interval: {self.update_interval} seconds")
        logger.info("-" * 50)

        iteration = 0
        while True:
            try:
                iteration += 1
                start_time = time.time()

                for symbol in self.symbols:
                    self.monitor_symbol(symbol)

                elapsed = time.time() - start_time
                logger.info(f"Iteration {iteration} completed in {elapsed:.2f}s")

                if iteration % 12 == 0:
                    summary = self.alert_system.get_alert_summary()
                    logger.info(f"Alert Summary: {summary}")

                time.sleep(max(0, self.update_interval - elapsed))

            except KeyboardInterrupt:
                logger.info("Monitoring stopped by user")
                break
            except Exception as e:
                logger.error(f"Error in main loop: {e}")
                time.sleep(5)


def validate_symbol(symbol: str) -> str:
    if not symbol.endswith('_USDT'):
        symbol = f"{symbol}_USDT"
    return symbol.upper()


def main():
    parser = argparse.ArgumentParser(description='MEXC Futures Order Monitor')
    parser.add_argument('symbols', nargs='*', help='Symbols to monitor (e.g., BTC_USDT ETH_USDT)')
    parser.add_argument('--min-order', type=float, default=50000,
                       help='Minimum order size in USDT (default: 50000)')
    parser.add_argument('--min-trade', type=float, default=25000,
                       help='Minimum trade size in USDT (default: 25000)')
    parser.add_argument('--whale-threshold', type=float, default=100000,
                       help='Whale threshold in USDT (default: 100000)')
    parser.add_argument('--interval', type=int, default=5,
                       help='Update interval in seconds (default: 5)')
    parser.add_argument('--log-alerts', action='store_true',
                       help='Log alerts to file')
    parser.add_argument('--no-telegram', action='store_true',
                       help='Disable Telegram notifications')
    parser.add_argument('--test-telegram', action='store_true',
                       help='Test Telegram connection and exit')

    args = parser.parse_args()

    # Test Telegram connection if requested
    if args.test_telegram:
        from src.telegram_notifier import TelegramNotifier
        notifier = TelegramNotifier()
        notifier.test_connection()
        return

    # Check if symbols provided when not testing
    if not args.symbols:
        parser.error("symbols are required unless using --test-telegram")

    symbols = [validate_symbol(s) for s in args.symbols]

    config = {
        'min_order_usdt': args.min_order,
        'min_trade_usdt': args.min_trade,
        'whale_threshold_usdt': args.whale_threshold,
        'update_interval': args.interval,
        'log_alerts': args.log_alerts,
        'telegram': not args.no_telegram
    }

    monitor = MEXCFuturesMonitor(symbols, config)
    monitor.run()


if __name__ == '__main__':
    main()