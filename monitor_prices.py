#!/usr/bin/env python3
import os
import sys
import json
import csv
import logging
import threading
import time
from datetime import datetime
from dotenv import load_dotenv
import websocket

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.telegram_notifier import TelegramNotifier

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

load_dotenv()


# Priority pairs for price monitoring
PRIORITY_TARGETS = [
    'HIFI_USDT',
    'PUMPFUN_USDT',
    'SUI_USDT',
    'WIF_USDT',
    'TRB_USDT'
]


class MEXCPriceMonitor:
    def __init__(self):
        # MEXC Futures WebSocket endpoint
        self.ws_url = "wss://contract.mexc.com/edge"
        self.ws = None

        # Current prices for each symbol
        self.current_prices = {symbol: {'bid': 0, 'ask': 0, 'mid': 0, 'spread': 0}
                               for symbol in PRIORITY_TARGETS}

        # CSV setup - one file per symbol for prices
        os.makedirs("data", exist_ok=True)
        self.csv_files = {}
        self.csv_writers = {}
        self.csv_file_handles = {}
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

        for symbol in PRIORITY_TARGETS:
            # Create subdirectory for each symbol
            symbol_dir = f"data/{symbol}"
            os.makedirs(symbol_dir, exist_ok=True)

            # Create CSV file for prices
            csv_path = f"{symbol_dir}/prices_{timestamp}.csv"
            self.csv_files[symbol] = csv_path

            # Open file handle and create writer
            file_handle = open(csv_path, 'w', newline='')
            self.csv_file_handles[symbol] = file_handle
            writer = csv.writer(file_handle)
            writer.writerow([
                'timestamp', 'bid', 'ask', 'mid', 'spread', 'spread_pct'
            ])
            self.csv_writers[symbol] = writer
            file_handle.flush()

        # Thread control
        self.running = True
        self.price_writer_thread = None
        self.last_update = {symbol: 0 for symbol in PRIORITY_TARGETS}

        # Statistics
        self.stats = {symbol: {'updates': 0, 'snapshots': 0} for symbol in PRIORITY_TARGETS}

    def on_message(self, ws, message):
        """Handle incoming WebSocket messages"""
        try:
            data = json.loads(message)

            # Log first message to see structure
            if not hasattr(self, '_logged_msg'):
                logger.info(f"First message received: {json.dumps(data)[:200]}")
                self._logged_msg = True

            # Process depth updates
            if data.get('channel') == 'push.depth.full':
                symbol = data.get('symbol')
                if symbol in PRIORITY_TARGETS and 'data' in data:
                    self.update_prices(symbol, data['data'])
            elif data.get('channel') == 'rs.sub.depth.full':
                logger.info(f"Subscription confirmed for {data.get('symbol', 'unknown')}")

        except Exception as e:
            logger.debug(f"Message processing error: {e}")

    def update_prices(self, symbol, depth_data):
        """Update current prices from depth data"""
        try:
            bids = depth_data.get('bids', [])
            asks = depth_data.get('asks', [])

            if bids and asks:
                # Get best bid and ask
                best_bid = float(bids[0][0]) if bids[0] else 0
                best_ask = float(asks[0][0]) if asks[0] else 0

                if best_bid > 0 and best_ask > 0:
                    mid = (best_bid + best_ask) / 2
                    spread = best_ask - best_bid

                    self.current_prices[symbol] = {
                        'bid': best_bid,
                        'ask': best_ask,
                        'mid': mid,
                        'spread': spread
                    }

                    self.last_update[symbol] = time.time()
                    self.stats[symbol]['updates'] += 1

                    # Log first update for each symbol
                    if self.stats[symbol]['updates'] == 1:
                        logger.info(f"First price update for {symbol}: Bid=${best_bid:.4f} Ask=${best_ask:.4f}")

        except Exception as e:
            logger.debug(f"Price update error for {symbol}: {e}")

    def price_writer(self):
        """Write prices to CSV every 100ms"""
        while self.running:
            try:
                timestamp = datetime.now()

                for symbol in PRIORITY_TARGETS:
                    prices = self.current_prices[symbol]

                    # Only write if we have valid prices
                    if prices['bid'] > 0 and prices['ask'] > 0:
                        spread_pct = (prices['spread'] / prices['mid'] * 100) if prices['mid'] > 0 else 0

                        # Write to CSV
                        self.csv_writers[symbol].writerow([
                            timestamp.isoformat(),
                            prices['bid'],
                            prices['ask'],
                            prices['mid'],
                            prices['spread'],
                            f"{spread_pct:.4f}"
                        ])

                        # Flush every 10 writes (1 second)
                        self.stats[symbol]['snapshots'] += 1
                        if self.stats[symbol]['snapshots'] % 10 == 0:
                            self.csv_file_handles[symbol].flush()

                # Sleep for 100ms
                time.sleep(0.1)

            except Exception as e:
                logger.error(f"Price writer error: {e}")
                time.sleep(0.1)

    def on_error(self, ws, error):
        """Handle WebSocket errors"""
        logger.error(f"WebSocket error: {error}")

    def on_close(self, ws, close_status_code, close_msg):
        """Handle WebSocket close"""
        logger.info(f"WebSocket closed: {close_status_code} - {close_msg}")

        if self.running:
            logger.info("Reconnecting in 5 seconds...")
            time.sleep(5)
            self.connect()

    def on_open(self, ws):
        """Handle WebSocket open - subscribe to channels"""
        logger.info("WebSocket connected successfully")

        # Subscribe to depth for each symbol
        for symbol in PRIORITY_TARGETS:
            # Subscribe to full depth data
            subscribe_msg = {
                "method": "sub.depth.full",
                "param": {
                    "symbol": symbol,
                    "limit": 5  # Minimum supported limit
                }
            }
            ws.send(json.dumps(subscribe_msg))
            logger.info(f"Subscribed to {symbol} depth")

            # Small delay between subscriptions
            time.sleep(0.05)

        # Start ping thread
        self.start_ping_thread(ws)

        # Start price writer thread
        if not self.price_writer_thread or not self.price_writer_thread.is_alive():
            self.price_writer_thread = threading.Thread(target=self.price_writer)
            self.price_writer_thread.daemon = True
            self.price_writer_thread.start()
            logger.info("Price writer thread started")

    def start_ping_thread(self, ws):
        """Start thread to send periodic pings"""
        def send_ping():
            while self.running:
                time.sleep(15)  # Send ping every 15 seconds
                try:
                    ping_msg = {"method": "ping"}
                    ws.send(json.dumps(ping_msg))
                    logger.debug("Sent ping")
                except:
                    break

        ping_thread = threading.Thread(target=send_ping)
        ping_thread.daemon = True
        ping_thread.start()

    def print_stats(self):
        """Print statistics"""
        print("\n" + "="*60)
        print(f"Price Monitor Stats - {datetime.now().strftime('%H:%M:%S')}")
        print("="*60)

        for symbol, stats in self.stats.items():
            if stats['snapshots'] > 0:
                print(f"{symbol}:")
                print(f"  Updates: {stats['updates']}")
                print(f"  Snapshots: {stats['snapshots']}")
                print(f"  Current: Bid=${self.current_prices[symbol]['bid']:.4f} "
                      f"Ask=${self.current_prices[symbol]['ask']:.4f}")

        print("="*60)

    def connect(self):
        """Connect to WebSocket"""
        websocket.enableTrace(False)

        self.ws = websocket.WebSocketApp(
            self.ws_url,
            on_open=self.on_open,
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close
        )

        # Run in a separate thread
        wst = threading.Thread(target=self.ws.run_forever)
        wst.daemon = True
        wst.start()

    def cleanup(self):
        """Clean up resources"""
        self.running = False

        # Close all CSV files
        for symbol, file_handle in self.csv_file_handles.items():
            try:
                file_handle.close()
            except:
                pass

        if self.ws:
            self.ws.close()

    def run(self):
        """Main run method"""
        print("="*60)
        print("MEXC PRICE SNAPSHOT MONITOR")
        print("="*60)
        print("Recording price snapshots every 100ms for:")

        for symbol in PRIORITY_TARGETS:
            print(f"  - {symbol}")

        print("\nCSV files in: data/{SYMBOL}/prices_*.csv")
        print("="*60)
        print("\nConnecting to WebSocket... (Ctrl+C to stop)\n")

        # Connect to WebSocket
        self.connect()

        # Keep running and print stats periodically
        try:
            while True:
                time.sleep(60)
                self.print_stats()
        except KeyboardInterrupt:
            print("\n\nPrice monitoring stopped")
            self.cleanup()

            print("\nFinal statistics:")
            for symbol, stats in self.stats.items():
                if stats['snapshots'] > 0:
                    print(f"  {symbol}: {stats['snapshots']} snapshots, {stats['updates']} updates")
                    print(f"    CSV: {self.csv_files[symbol]}")


def main():
    monitor = MEXCPriceMonitor()
    monitor.run()


if __name__ == '__main__':
    main()