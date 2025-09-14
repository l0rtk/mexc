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


# Priority pairs for WebSocket monitoring
# huge: threshold for CSV logging (moderate size orders)
# mega: threshold for Telegram alerts (EXTREMELY LARGE orders only)
PRIORITY_TARGETS = {
    'HIFI_USDT': {'huge': 15000, 'mega': 150000},      # 10x increase
    'PUMPFUN_USDT': {'huge': 8000, 'mega': 100000},    # 12.5x increase
    'SUI_USDT': {'huge': 150000, 'mega': 2000000},     # 5x increase (already liquid)
    'WIF_USDT': {'huge': 25000, 'mega': 300000},       # 5x increase
    'TRB_USDT': {'huge': 40000, 'mega': 500000},       # 5x increase
}


class MEXCWebSocketMonitor:
    def __init__(self):
        # MEXC Futures WebSocket endpoint
        # Using the contract WebSocket endpoint for futures
        self.ws_url = "wss://contract.mexc.com/edge"
        self.telegram = TelegramNotifier()
        self.ws = None

        # Track orders to avoid duplicates
        self.last_orders = {symbol: set() for symbol in PRIORITY_TARGETS}

        # Statistics
        self.stats = {symbol: {'huge': 0, 'mega': 0, 'updates': 0}
                     for symbol in PRIORITY_TARGETS}

        # CSV setup - one file per symbol
        os.makedirs("data", exist_ok=True)
        self.csv_files = {}
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

        for symbol in PRIORITY_TARGETS:
            # Create subdirectory for each symbol
            symbol_dir = f"data/{symbol}"
            os.makedirs(symbol_dir, exist_ok=True)

            # Create CSV file for this symbol
            self.csv_files[symbol] = f"{symbol_dir}/websocket_{timestamp}.csv"
            self._init_csv(self.csv_files[symbol])

        # Ping thread
        self.ping_thread = None
        self.running = True

    def _init_csv(self, csv_file):
        """Initialize CSV file"""
        with open(csv_file, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                'timestamp', 'side', 'price',
                'volume', 'volume_usdt', 'alert_type'
            ])

    def on_message(self, ws, message):
        """Handle incoming WebSocket messages"""
        try:
            data = json.loads(message)

            # Log all messages for debugging (except push.depth.full which are frequent)
            if data.get('channel') != 'push.depth.full':
                logger.debug(f"Received message type: {data.get('channel', 'unknown')}")

            # Check for different message types
            if data.get('channel') == 'pong':
                logger.debug("Received pong")
            elif data.get('channel') == 'rs.error':
                logger.error(f"Subscription error: {data}")
            elif data.get('channel') == 'rs.sub.depth.full':
                logger.debug(f"Subscription confirmed for depth.full")
            elif data.get('channel') == 'push.depth.full':
                # Full depth push from futures WebSocket
                # Log first message to understand structure
                if not hasattr(self, '_logged_sample'):
                    logger.info(f"Sample depth message: {json.dumps(data)[:500]}")
                    self._logged_sample = True

                logger.debug(f"Processing depth push for symbol: {data.get('symbol', 'unknown')}")
                if 'data' in data and data.get('symbol'):
                    self.check_order_book(data['symbol'], data['data'])
            elif 'channel' in data and 'depth.full' in data['channel']:
                # Full depth update from futures WebSocket
                logger.info(f"Processing depth data for channel: {data['channel']}")
                self.process_depth_data(data)
            elif 'data' in data:
                # Direct depth data
                if 'bids' in data['data'] or 'asks' in data['data']:
                    symbol = data.get('symbol') or self.extract_symbol_from_data(data)
                    if symbol:
                        logger.info(f"Processing order book for {symbol}")
                        self.check_order_book(symbol, data['data'])
            else:
                # Log any unhandled message type
                logger.info(f"Unhandled message: {json.dumps(data)[:200]}")

        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error: {e}")
        except Exception as e:
            logger.error(f"Message processing error: {e}")

    def extract_symbol_from_data(self, data):
        """Extract symbol from various message formats"""
        # Try different ways to get symbol
        if 'symbol' in data:
            return data['symbol']
        if 'data' in data and 'symbol' in data['data']:
            return data['data']['symbol']
        if 'channel' in data:
            # Parse from channel name like "depth.update.HIFI_USDT"
            parts = data['channel'].split('.')
            for part in parts:
                if part in PRIORITY_TARGETS:
                    return part
        return None

    def process_depth_data(self, data):
        """Process depth channel data"""
        channel = data.get('channel', '')

        # Extract symbol from channel
        symbol = None
        for target_symbol in PRIORITY_TARGETS:
            if target_symbol in channel:
                symbol = target_symbol
                break

        if symbol and 'data' in data:
            self.check_order_book(symbol, data['data'])

    def check_order_book(self, symbol, depth_data):
        """Check order book for huge orders"""
        if symbol not in PRIORITY_TARGETS:
            return

        thresholds = PRIORITY_TARGETS[symbol]
        huge_threshold = thresholds['huge']
        mega_threshold = thresholds['mega']

        self.stats[symbol]['updates'] += 1

        # Get bids and asks
        bids = depth_data.get('bids', [])
        asks = depth_data.get('asks', [])

        current_orders = set()

        # Check bids (buy orders)
        for bid in bids[:5]:
            if isinstance(bid, list) and len(bid) >= 2:
                try:
                    # Futures format: [price, order_size_contracts, order_count]
                    # order_size_contracts is the total size in contracts at this level
                    price = float(bid[0])
                    # Volume is at index 1 (total contracts at this price level)
                    volume = float(bid[1])

                    volume_usdt = price * volume

                    if volume_usdt >= huge_threshold:
                        order_key = f"BUY_{price}_{volume}"
                        current_orders.add(order_key)

                        # New order detected
                        if order_key not in self.last_orders[symbol]:
                            self.handle_huge_order(
                                symbol, 'BUY', price, volume,
                                volume_usdt, huge_threshold, mega_threshold
                            )
                except (ValueError, TypeError, IndexError):
                    continue

        # Check asks (sell orders)
        for ask in asks[:5]:
            if isinstance(ask, list) and len(ask) >= 2:
                try:
                    # Futures format: [price, order_size_contracts, order_count]
                    # order_size_contracts is the total size in contracts at this level
                    price = float(ask[0])
                    # Volume is at index 1 (total contracts at this price level)
                    volume = float(ask[1])

                    volume_usdt = price * volume

                    if volume_usdt >= huge_threshold:
                        order_key = f"SELL_{price}_{volume}"
                        current_orders.add(order_key)

                        # New order detected
                        if order_key not in self.last_orders[symbol]:
                            self.handle_huge_order(
                                symbol, 'SELL', price, volume,
                                volume_usdt, huge_threshold, mega_threshold
                            )
                except (ValueError, TypeError, IndexError):
                    continue

        # Update last seen orders
        self.last_orders[symbol] = current_orders

    def handle_huge_order(self, symbol, side, price, volume, volume_usdt, huge_threshold, mega_threshold):
        """Handle huge order detection"""
        emoji = "🔴" if side == "SELL" else "🟢"
        timestamp = datetime.now()

        if volume_usdt >= mega_threshold:
            # MEGA order - send Telegram
            logger.info(f"💥 MEGA {emoji} {symbol}: ${volume_usdt:,.0f} @ ${price:.4f}")

            # Calculate how many times larger than the mega threshold
            multiplier = volume_usdt / mega_threshold

            message = f"🚨🚨🚨 <b>MASSIVE ORDER DETECTED</b> 🚨🚨🚨\n\n"
            message += f"💥💥💥 <b>EXTREMELY LARGE</b> 💥💥💥\n\n"
            message += f"{emoji} <b>{symbol}</b>\n"
            message += f"Side: <b>{side}</b>\n"
            message += f"Size: <b>${volume_usdt:,.0f}</b>\n"
            message += f"Price: ${price:.4f}\n"
            message += f"Volume: {volume:,.2f}\n"
            message += f"Magnitude: {multiplier:.1f}x mega threshold\n"
            message += f"Time: {timestamp.strftime('%H:%M:%S.%f')[:-3]}"

            self.telegram.send_message(message)
            self.save_to_csv(timestamp, symbol, side, price, volume, volume_usdt, 'MEGA')
            self.stats[symbol]['mega'] += 1

        else:
            # Regular huge order
            logger.info(f"🐋 HUGE {emoji} {symbol}: ${volume_usdt:,.0f} @ ${price:.4f}")
            self.save_to_csv(timestamp, symbol, side, price, volume, volume_usdt, 'HUGE')
            self.stats[symbol]['huge'] += 1

    def save_to_csv(self, timestamp, symbol, side, price, volume, volume_usdt, alert_type):
        """Save order to CSV"""
        csv_file = self.csv_files[symbol]
        with open(csv_file, 'a', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                timestamp.isoformat(),
                side, price, volume,
                volume_usdt, alert_type
            ])

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
            # Subscribe to full depth data (futures/contract format)
            subscribe_msg = {
                "method": "sub.depth.full",
                "param": {
                    "symbol": symbol,
                    "limit": 5  # Get top 5 levels for efficiency
                }
            }
            ws.send(json.dumps(subscribe_msg))
            logger.info(f"Subscribed to {symbol} full depth")

            # Small delay between subscriptions
            time.sleep(0.1)

        # Start ping thread
        self.start_ping_thread(ws)

    def start_ping_thread(self, ws):
        """Start thread to send periodic pings"""
        def send_ping():
            while self.running:
                time.sleep(15)  # Send ping every 15 seconds (recommended 10-20s)
                try:
                    ping_msg = {"method": "ping"}
                    ws.send(json.dumps(ping_msg))
                    logger.debug("Sent ping")
                except:
                    break

        self.ping_thread = threading.Thread(target=send_ping)
        self.ping_thread.daemon = True
        self.ping_thread.start()

    def print_stats(self):
        """Print statistics"""
        print("\n" + "="*60)
        print(f"WebSocket Stats - {datetime.now().strftime('%H:%M:%S')}")
        print("="*60)

        for symbol, stats in self.stats.items():
            if stats['updates'] > 0:
                print(f"{symbol}:")
                print(f"  Updates: {stats['updates']}")
                print(f"  Huge Orders: {stats['huge']}")
                print(f"  Mega Orders: {stats['mega']}")

        print("="*60)

    def connect(self):
        """Connect to WebSocket"""
        websocket.enableTrace(False)  # Set to True for debugging

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

    def run(self):
        """Main run method"""
        print("="*60)
        print("MEXC WEBSOCKET MONITOR - Real-time Order Book")
        print("="*60)
        print("Monitoring 5 priority pairs via WebSocket:")

        for symbol, thresholds in PRIORITY_TARGETS.items():
            print(f"  {symbol:<15} Huge: ${thresholds['huge']:,} | Mega: ${thresholds['mega']:,}")

        print("="*60)
        print("⚡ REAL-TIME MODE - Zero latency WebSocket streaming")
        print("CSV files in: data/{SYMBOL}/websocket_*.csv")
        print("\nConnecting to WebSocket... (Ctrl+C to stop)\n")

        # Connect to WebSocket
        self.connect()

        # Keep running and print stats periodically
        try:
            while True:
                time.sleep(60)
                self.print_stats()
        except KeyboardInterrupt:
            print("\n\nWebSocket monitoring stopped")
            self.running = False
            if self.ws:
                self.ws.close()

            print("Final statistics:")
            for symbol, stats in self.stats.items():
                print(f"  {symbol}: {stats['huge']} huge, {stats['mega']} mega, {stats['updates']} updates")


def main():
    monitor = MEXCWebSocketMonitor()
    monitor.run()


if __name__ == '__main__':
    main()