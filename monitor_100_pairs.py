#!/usr/bin/env python3
"""
Monitor 100 MEXC futures pairs with optimized performance
"""

import subprocess
import sys
import os
import json
import requests

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'src'))

def get_top_100_pairs():
    """Get top 100 MEXC futures pairs by volume"""
    try:
        # Get 24h ticker data
        url = "https://api.mexc.com/api/v3/ticker/24hr"
        response = requests.get(url, timeout=10)
        data = response.json()
        
        # Filter USDT futures pairs and sort by volume
        usdt_pairs = [
            (item['symbol'], float(item['quoteVolume']))
            for item in data 
            if item['symbol'].endswith('_USDT') and float(item['quoteVolume']) > 0
        ]
        
        # Sort by volume and take top 100
        usdt_pairs.sort(key=lambda x: x[1], reverse=True)
        top_100 = [pair[0] for pair in usdt_pairs[:100]]
        
        print(f"Found {len(top_100)} top volume pairs")
        return top_100
        
    except Exception as e:
        print(f"Error fetching pairs: {e}")
        print("Using default list...")
        # Fallback to common pairs
        return [
            "BTC_USDT", "ETH_USDT", "XRP_USDT", "SOL_USDT", "BNB_USDT",
            "DOGE_USDT", "ADA_USDT", "AVAX_USDT", "SHIB_USDT", "DOT_USDT",
            "MATIC_USDT", "UNI_USDT", "LTC_USDT", "TRX_USDT", "LINK_USDT",
            "ATOM_USDT", "XLM_USDT", "BCH_USDT", "APT_USDT", "HBAR_USDT",
            "FIL_USDT", "ARB_USDT", "VET_USDT", "ICP_USDT", "NEAR_USDT",
            "OP_USDT", "INJ_USDT", "SUI_USDT", "SEI_USDT", "TIA_USDT"
        ]

def main():
    print("MEXC Monitor - 100 Pairs Edition")
    print("=" * 50)
    print()
    
    # Mode selection
    print("Select monitoring mode:")
    print("1. Fast (5s updates, minimal features) - RECOMMENDED for 100 pairs")
    print("2. Balanced (10s updates, more features)")
    print("3. Thorough (15s updates, all features) - May be slow")
    print("4. Custom pairs from file")
    
    choice = input("\nEnter choice (1-4) [default: 1]: ").strip() or "1"
    
    # Get pairs
    if choice == "4":
        file_path = input("Enter watchlist file path: ").strip()
        if os.path.exists(file_path):
            with open(file_path, 'r') as f:
                pairs = [line.strip() for line in f if line.strip() and not line.startswith('#')]
        else:
            print("File not found, using top 100 by volume")
            pairs = get_top_100_pairs()
    else:
        print("\nFetching top 100 MEXC pairs by volume...")
        pairs = get_top_100_pairs()
    
    print(f"\nMonitoring {len(pairs)} pairs")
    print("First 10:", ', '.join(pairs[:10]), "...")
    
    # Save pairs to file for reference
    with open('watchlists/top_100.txt', 'w') as f:
        f.write("# Top 100 MEXC pairs by volume\n")
        f.write(f"# Generated at {os.popen('date').read().strip()}\n\n")
        for pair in pairs:
            f.write(f"{pair}\n")
    
    # Run the appropriate monitor
    os.chdir('src')
    
    if choice == "1":
        # Fast mode - recommended for 100 pairs
        cmd = ["python", "monitor_optimized.py", "--mode", "fast", "--file", "../watchlists/top_100.txt"]
    elif choice == "2":
        # Balanced mode
        cmd = ["python", "monitor_optimized.py", "--mode", "balanced", "--file", "../watchlists/top_100.txt"]
    elif choice == "3":
        # Thorough mode - warning: may be slow
        cmd = ["python", "monitor_optimized.py", "--mode", "thorough", "--file", "../watchlists/top_100.txt"]
    else:
        # Custom file
        cmd = ["python", "monitor_optimized.py", "--mode", "fast", "--file", f"../{file_path}"]
    
    print(f"\nRunning: {' '.join(cmd)}")
    print("-" * 50)
    print("\nNOTE: With 100 pairs, expect:")
    print("- Fast mode: 20-30s per cycle")
    print("- Balanced mode: 40-60s per cycle")
    print("- Focus on the most active pairs shown in updates")
    print("-" * 50)
    
    try:
        subprocess.run(cmd)
    except KeyboardInterrupt:
        print("\n\nMonitor stopped by user")

if __name__ == "__main__":
    main()