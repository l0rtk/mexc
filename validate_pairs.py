#!/usr/bin/env python3
"""
Validate which pairs have active futures contracts on MEXC
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'src'))

from data_fetcher import SinglePairDataFetcher
import time

def validate_pairs(pairs_file):
    """Check which pairs have valid futures contracts"""
    
    # Read pairs from file
    pairs = []
    with open(pairs_file, 'r') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#'):
                symbol = line.split('#')[0].strip()
                if symbol:
                    pairs.append(symbol)
    
    print(f"Checking {len(pairs)} pairs...")
    print("-" * 50)
    
    valid_pairs = []
    invalid_pairs = []
    
    for i, symbol in enumerate(pairs):
        try:
            fetcher = SinglePairDataFetcher(symbol)
            candles = fetcher.fetch_candles(limit=5)
            
            if candles and len(candles) > 0:
                valid_pairs.append(symbol)
                print(f"✅ {symbol:15} - Valid futures contract")
            else:
                invalid_pairs.append(symbol)
                print(f"❌ {symbol:15} - No data returned")
                
        except Exception as e:
            invalid_pairs.append(symbol)
            error_msg = str(e)
            if "合约不存在" in error_msg or "contract" in error_msg.lower():
                print(f"❌ {symbol:15} - No futures contract")
            else:
                print(f"❌ {symbol:15} - Error: {error_msg[:50]}")
        
        # Small delay to avoid rate limiting
        if i % 10 == 9:
            time.sleep(1)
    
    # Save valid pairs
    output_file = pairs_file.replace('.txt', '_valid.txt')
    with open(output_file, 'w') as f:
        f.write("# Validated MEXC Futures Pairs\n")
        f.write(f"# {len(valid_pairs)} valid pairs out of {len(pairs)} checked\n\n")
        for pair in valid_pairs:
            f.write(f"{pair}\n")
    
    print("\n" + "=" * 50)
    print(f"Results:")
    print(f"✅ Valid pairs: {len(valid_pairs)}")
    print(f"❌ Invalid pairs: {len(invalid_pairs)}")
    print(f"\nValid pairs saved to: {output_file}")
    
    if invalid_pairs:
        print(f"\nInvalid pairs: {', '.join(invalid_pairs[:10])}" + 
              (f" and {len(invalid_pairs)-10} more" if len(invalid_pairs) > 10 else ""))
    
    return valid_pairs

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description='Validate MEXC futures pairs')
    parser.add_argument('file', help='Input file with pairs to validate')
    args = parser.parse_args()
    
    if os.path.exists(args.file):
        validate_pairs(args.file)
    else:
        print(f"File not found: {args.file}")