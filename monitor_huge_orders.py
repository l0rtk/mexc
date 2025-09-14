#!/usr/bin/env python3
import os
import sys
import time
import csv
import logging
from datetime import datetime
from dotenv import load_dotenv

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.mexc_client import MEXCFuturesClient
from src.order_monitor import OrderBookMonitor
from src.telegram_notifier import TelegramNotifier

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

load_dotenv()


# Hardcoded manipulation targets with thresholds
# huge_order: threshold for CSV logging
# mega_order: threshold for Telegram alerts (VERY huge orders)
MANIPULATION_TARGETS = [
    # Extreme manipulation - very low thresholds
    {'symbol': 'HIFI_USDT', 'huge_order': 20000, 'mega_order': 50000},
    {'symbol': 'EXO_USDT', 'huge_order': 25000, 'mega_order': 60000},
    {'symbol': 'PUMPFUN_USDT', 'huge_order': 10000, 'mega_order': 25000},
    {'symbol': 'H_USDT', 'huge_order': 10000, 'mega_order': 25000},

    # High manipulation - low thresholds
    {'symbol': 'AVNT_USDT', 'huge_order': 50000, 'mega_order': 150000},
    {'symbol': 'SOMI_USDT', 'huge_order': 25000, 'mega_order': 60000},
    {'symbol': 'AI16Z_USDT', 'huge_order': 20000, 'mega_order': 50000},
    {'symbol': 'WIF_USDT', 'huge_order': 30000, 'mega_order': 75000},

    # Medium manipulation - medium thresholds
    {'symbol': 'SUI_USDT', 'huge_order': 200000, 'mega_order': 500000},
    {'symbol': 'TRB_USDT', 'huge_order': 50000, 'mega_order': 150000},
    {'symbol': 'SPX_USDT', 'huge_order': 25000, 'mega_order': 60000},
    {'symbol': 'HNT_USDT', 'huge_order': 30000, 'mega_order': 75000},
    {'symbol': 'ETHFI_USDT', 'huge_order': 40000, 'mega_order': 100000},
    {'symbol': 'ENA_USDT', 'huge_order': 50000, 'mega_order': 125000},
    {'symbol': 'OMNI_USDT', 'huge_order': 40000, 'mega_order': 100000},
]


class HugeOrderMonitor:
    def __init__(self):
        self.client = MEXCFuturesClient(
            os.getenv('MEXC_ACCESS_KEY'),
            os.getenv('MEXC_SECRET_KEY')
        )

        self.telegram = TelegramNotifier()

        # Create monitors for each symbol
        self.monitors = {}
        for target in MANIPULATION_TARGETS:
            symbol = target['symbol']
            self.monitors[symbol] = {
                'order_monitor': OrderBookMonitor(
                    min_order_usdt=target['huge_order'],
                    whale_threshold_usdt=target['huge_order']
                ),
                'huge_threshold': target['huge_order'],
                'mega_threshold': target['mega_order']
            }

        # Create data directory and CSV file
        os.makedirs("data", exist_ok=True)
        self.csv_file = f"data/huge_orders_{datetime.now().strftime('%Y%m%d')}.csv"

        # Initialize CSV file with headers if it doesn't exist
        if not os.path.exists(self.csv_file):
            with open(self.csv_file, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([
                    'timestamp', 'symbol', 'side', 'price',
                    'volume', 'volume_usdt', 'percentage_of_book',
                    'alert_type', 'threshold'
                ])

        self.stats = {
            t['symbol']: {
                'huge_count': 0,
                'mega_count': 0,
                'max_size': 0
            } for t in MANIPULATION_TARGETS
        }

    def check_symbol(self, symbol: str):
        """Check for huge orders in a symbol"""
        try:
            monitor = self.monitors[symbol]['order_monitor']
            huge_threshold = self.monitors[symbol]['huge_threshold']
            mega_threshold = self.monitors[symbol]['mega_threshold']

            # Get order book
            order_book = self.client.get_order_book(symbol, limit=10)
            if not order_book:
                return

            # Check for huge orders
            large_orders = monitor.analyze_order_book(symbol, order_book)

            for order in large_orders:
                # Check if it's at least a huge order
                if order.volume_usdt >= huge_threshold:
                    emoji = "🔴" if order.side == "SELL" else "🟢"

                    # Check if it's a MEGA order (very very huge)
                    if order.volume_usdt >= mega_threshold:
                        # MEGA ORDER - Send Telegram alert
                        logger.info(f"💥 MEGA ORDER {emoji} {symbol}: "
                                   f"${order.volume_usdt:,.0f} at ${order.price:.4f}")

                        # Telegram alert for MEGA orders only
                        message = f"💥💥💥 <b>MEGA ORDER ALERT</b> 💥💥💥\n\n"
                        message += f"{'🔴' if order.side == 'SELL' else '🟢'} <b>{symbol}</b>\n"
                        message += f"Side: <b>{order.side}</b>\n"
                        message += f"Size: <b>${order.volume_usdt:,.0f}</b>\n"
                        message += f"Price: ${order.price:.4f}\n"
                        message += f"Volume: {order.volume:,.2f}\n"
                        message += f"Book %: {order.percentage_of_book:.1f}%\n"
                        message += f"Size vs Threshold: {order.volume_usdt/mega_threshold:.1f}x"

                        self.telegram.send_message(message)

                        # Save to CSV with MEGA flag
                        self.save_to_csv(symbol, order, 'MEGA', mega_threshold)

                        self.stats[symbol]['mega_count'] += 1

                    else:
                        # Regular HUGE order - only log to console and CSV
                        logger.info(f"🐋 HUGE ORDER {emoji} {symbol}: "
                                   f"${order.volume_usdt:,.0f} at ${order.price:.4f}")

                        # Save to CSV with HUGE flag
                        self.save_to_csv(symbol, order, 'HUGE', huge_threshold)

                        self.stats[symbol]['huge_count'] += 1

                    # Update max size
                    if order.volume_usdt > self.stats[symbol]['max_size']:
                        self.stats[symbol]['max_size'] = order.volume_usdt

        except Exception as e:
            logger.error(f"Error checking {symbol}: {e}")

    def save_to_csv(self, symbol: str, order, alert_type: str, threshold: float):
        """Append order to CSV file"""
        with open(self.csv_file, 'a', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                datetime.now().isoformat(),
                symbol,
                order.side,
                order.price,
                order.volume,
                order.volume_usdt,
                order.percentage_of_book,
                alert_type,
                threshold
            ])

    def print_summary(self):
        """Print summary of orders detected"""
        total_huge = sum(s['huge_count'] for s in self.stats.values())
        total_mega = sum(s['mega_count'] for s in self.stats.values())

        if total_huge > 0 or total_mega > 0:
            print("\n" + "="*60)
            print(f"ORDER SUMMARY - {datetime.now().strftime('%H:%M:%S')}")
            print("="*60)

            for symbol, stats in self.stats.items():
                if stats['huge_count'] > 0 or stats['mega_count'] > 0:
                    print(f"{symbol}:")
                    print(f"  Huge Orders: {stats['huge_count']}")
                    print(f"  💥 MEGA Orders: {stats['mega_count']}")
                    if stats['max_size'] > 0:
                        print(f"  Max Size: ${stats['max_size']:,.0f}")

            print(f"\nTotals: {total_huge} huge, {total_mega} MEGA")
            print(f"CSV file: {self.csv_file}")
            print("="*60)

    def run(self):
        """Main monitoring loop"""
        print("="*60)
        print("MEXC HUGE ORDER MONITOR")
        print("="*60)
        print(f"Monitoring {len(MANIPULATION_TARGETS)} pairs")
        print(f"Saving to: {self.csv_file}\n")

        print("Thresholds:")
        for target in MANIPULATION_TARGETS:
            print(f"  {target['symbol']:<15} "
                  f"Huge: ${target['huge_order']:,} | "
                  f"💥 MEGA: ${target['mega_order']:,}")

        print("\n🐋 = Logged to CSV only")
        print("💥 = Telegram alert + CSV")
        print("="*60)
        print("\nMonitoring started... (Ctrl+C to stop)\n")

        iteration = 0
        while True:
            try:
                iteration += 1

                # Check all symbols
                for target in MANIPULATION_TARGETS:
                    self.check_symbol(target['symbol'])

                # Print summary every 60 iterations (5 minutes)
                if iteration % 60 == 0:
                    self.print_summary()
                    # Reset stats
                    self.stats = {
                        t['symbol']: {
                            'huge_count': 0,
                            'mega_count': 0,
                            'max_size': 0
                        } for t in MANIPULATION_TARGETS
                    }

                # Wait 5 seconds
                time.sleep(5)

            except KeyboardInterrupt:
                print("\nMonitoring stopped")
                self.print_summary()
                break
            except Exception as e:
                logger.error(f"Error: {e}")
                time.sleep(5)


def main():
    monitor = HugeOrderMonitor()
    monitor.run()


if __name__ == '__main__':
    main()