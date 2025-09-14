#!/usr/bin/env python3
import csv
import requests
from datetime import datetime

def fetch_futures_data():
    """Fetch all MEXC futures data and save to CSV"""

    print("Fetching MEXC futures data...")

    try:
        # Fetch all tickers
        response = requests.get("https://contract.mexc.com/api/v1/contract/ticker")
        data = response.json()

        if not data.get('success'):
            print("Failed to fetch data")
            return

        tickers = data.get('data', [])

        # Process and prepare data for CSV
        futures_data = []

        for ticker in tickers:
            try:
                symbol = ticker.get('symbol', '')
                last_price = float(ticker.get('lastPrice', 0))
                volume_24h = float(ticker.get('volume24', 0))
                volume_usdt = volume_24h * last_price

                # Skip if no volume
                if volume_usdt == 0:
                    continue

                entry = {
                    'symbol': symbol,
                    'price': last_price,
                    'change_24h_pct': float(ticker.get('riseFallRate', 0)) * 100,
                    'volume_24h': volume_24h,
                    'volume_usdt_24h': volume_usdt,
                    'high_24h': float(ticker.get('high24Price', 0)),
                    'low_24h': float(ticker.get('low24Price', 0)),
                    'open_interest': float(ticker.get('holdVol', 0)),
                    'open_interest_usdt': float(ticker.get('holdVol', 0)) * last_price,
                    'bid': float(ticker.get('bid1', 0)),
                    'ask': float(ticker.get('ask1', 0)),
                    'spread': float(ticker.get('ask1', 0)) - float(ticker.get('bid1', 0)),
                    'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }

                # Calculate additional metrics
                if entry['high_24h'] > 0 and entry['low_24h'] > 0:
                    entry['range_pct'] = ((entry['high_24h'] - entry['low_24h']) / entry['low_24h']) * 100
                else:
                    entry['range_pct'] = 0

                if entry['open_interest_usdt'] > 0:
                    entry['volume_oi_ratio'] = entry['volume_usdt_24h'] / entry['open_interest_usdt']
                else:
                    entry['volume_oi_ratio'] = 0

                futures_data.append(entry)

            except (ValueError, TypeError, KeyError):
                continue

        # Sort by volume
        futures_data.sort(key=lambda x: x['volume_usdt_24h'], reverse=True)

        # Generate filename with timestamp
        filename = f"mexc_futures_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

        # Write to CSV
        if futures_data:
            fieldnames = [
                'symbol', 'price', 'change_24h_pct', 'volume_24h', 'volume_usdt_24h',
                'high_24h', 'low_24h', 'range_pct', 'open_interest', 'open_interest_usdt',
                'volume_oi_ratio', 'bid', 'ask', 'spread', 'timestamp'
            ]

            with open(filename, 'w', newline='') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(futures_data)

            print(f"✅ Data saved to {filename}")
            print(f"   Total contracts: {len(futures_data)}")
            print(f"   Top 5 by volume:")
            for i, d in enumerate(futures_data[:5], 1):
                print(f"   {i}. {d['symbol']}: ${d['volume_usdt_24h']:,.0f}")
        else:
            print("No data to save")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == '__main__':
    fetch_futures_data()