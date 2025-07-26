#!/usr/bin/env python3
"""
Fetch and save top 100 MEXC futures pairs by volume
"""

import requests
import os
from datetime import datetime

def get_top_100_pairs():
    """Get top 100 MEXC futures pairs by volume"""
    try:
        print("Fetching MEXC 24h ticker data...")
        url = "https://api.mexc.com/api/v3/ticker/24hr"
        response = requests.get(url, timeout=10)
        data = response.json()
        
        # Filter USDT futures pairs and sort by volume
        usdt_pairs = []
        for item in data:
            if item['symbol'].endswith('USDT') and float(item['quoteVolume']) > 0:
                # MEXC uses format like BTCUSDT, we need BTC_USDT
                symbol = item['symbol']
                if '_' not in symbol:
                    # Insert underscore before USDT
                    symbol = symbol.replace('USDT', '_USDT')
                
                usdt_pairs.append({
                    'symbol': symbol,
                    'volume': float(item['quoteVolume']),
                    'price': float(item['lastPrice']),
                    'change': float(item['priceChangePercent'])
                })
        
        # Sort by volume
        usdt_pairs.sort(key=lambda x: x['volume'], reverse=True)
        
        # Take top 100
        top_100 = usdt_pairs[:100]
        
        # Create watchlists directory if needed
        os.makedirs('watchlists', exist_ok=True)
        
        # Save to file
        with open('watchlists/top_100.txt', 'w') as f:
            f.write("# Top 100 MEXC USDT Futures Pairs by 24h Volume\n")
            f.write(f"# Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} UTC\n")
            f.write("#\n")
            f.write("# Format: SYMBOL (24h Volume in USDT, Price, 24h Change %)\n")
            f.write("#" + "="*70 + "\n\n")
            
            for i, pair in enumerate(top_100, 1):
                f.write(f"{pair['symbol']}  # #{i} Vol: ${pair['volume']:,.0f}, Price: ${pair['price']:.4f}, Change: {pair['change']:+.2f}%\n")
        
        print(f"\n✅ Saved top 100 pairs to watchlists/top_100.txt")
        print(f"\nTop 10 pairs by volume:")
        print("-" * 50)
        for i, pair in enumerate(top_100[:10], 1):
            print(f"{i}. {pair['symbol']:15} Vol: ${pair['volume']:>15,.0f}  Change: {pair['change']:+6.2f}%")
        
        return [p['symbol'] for p in top_100]
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return []

if __name__ == "__main__":
    pairs = get_top_100_pairs()
    if pairs:
        print(f"\nTotal pairs saved: {len(pairs)}")
        print("\nTo monitor these pairs, run:")
        print("  ./monitor_100_pairs.py")
        print("or:")
        print("  cd src && python monitor_optimized.py --mode fast --file ../watchlists/top_100.txt")