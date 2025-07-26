#!/usr/bin/env python3
"""
Select optimal pairs for manipulation monitoring based on volume and volatility
Focus on medium-liquidity pairs that can be manipulated
"""

import requests
import os
from datetime import datetime

def get_manipulation_targets():
    """Get pairs suitable for manipulation monitoring"""
    try:
        print("Fetching MEXC market data...")
        # Use futures ticker endpoint instead
        url = "https://contract.mexc.com/api/v1/contract/ticker"
        response = requests.get(url, timeout=10)
        data = response.json()
        
        if 'data' in data:
            data = data['data']  # Extract data array
        
        # Analyze all USDT pairs
        all_pairs = []
        for item in data:
            try:
                symbol = item.get('symbol', '')
                if not symbol.endswith('_USDT'):
                    continue
                
                # Already in correct format for futures
                volume24 = float(item.get('volume24', 0))
                price_change = float(item.get('riseFallRate', 0)) * 100  # Convert to percentage
                
                # Skip stablecoins
                if any(stable in symbol for stable in ['USDC_', 'USDT_', 'BUSD_', 'DAI_', 'TUSD_', 'FDUSD_']):
                    continue
                
                # Only include if has decent volume (futures volume in contracts)
                if volume24 > 100000:  # Min 100k contracts volume
                    all_pairs.append({
                        'symbol': symbol,
                        'volume': volume24,
                        'change': price_change,
                        'volatility': abs(price_change)
                    })
            except Exception as e:
                continue
        
        # Sort by volume to find the sweet spot
        all_pairs.sort(key=lambda x: x['volume'], reverse=True)
        
        # Find manipulation sweet spot (rank 50-200 by volume)
        # These have enough liquidity but can still be moved
        sweet_spot = all_pairs[50:200] if len(all_pairs) > 200 else all_pairs[50:]
        
        # Also get volatile mid-caps (high % moves)
        volatile_pairs = [p for p in all_pairs[20:300] if p['volatility'] > 3]
        volatile_pairs.sort(key=lambda x: x['volatility'], reverse=True)
        
        # Combine and deduplicate
        targets = {p['symbol']: p for p in sweet_spot}
        for p in volatile_pairs[:50]:
            targets[p['symbol']] = p
        
        # Convert back to list and sort by volatility
        final_targets = list(targets.values())
        final_targets.sort(key=lambda x: x['volatility'], reverse=True)
        
        # Save results
        os.makedirs('watchlists', exist_ok=True)
        
        # Save top 50 manipulation targets
        with open('watchlists/manipulation_targets_auto.txt', 'w') as f:
            f.write("# Auto-Selected Manipulation Targets\n")
            f.write(f"# Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} UTC\n")
            f.write("# Selection: Medium liquidity + High volatility\n")
            f.write("#" + "="*70 + "\n\n")
            
            selected = final_targets[:50]
            for pair in selected:
                f.write(f"{pair['symbol']:15} # Vol: ${pair['volume']:>12,.0f}, 24h: {pair['change']:+6.2f}%\n")
        
        print(f"✅ Saved {len(selected)} targets to watchlists/manipulation_targets_auto.txt")
        
        # Create focused list (top 20 most volatile)
        with open('watchlists/high_volatility_targets.txt', 'w') as f:
            f.write("# High Volatility Manipulation Targets\n")
            f.write("# Top 20 most volatile in medium liquidity range\n\n")
            
            for pair in selected[:20]:
                f.write(f"{pair['symbol']}\n")
        
        print(f"✅ Saved top 20 to watchlists/high_volatility_targets.txt")
        
        # Analysis
        print("\n📊 Market Analysis:")
        print(f"Total USDT pairs: {len(all_pairs)}")
        print(f"Pairs in sweet spot (rank 50-200): {len(sweet_spot)}")
        print(f"High volatility pairs (>3%): {len(volatile_pairs)}")
        print(f"Selected targets: {len(selected)}")
        
        # Show volume distribution
        vol_ranges = {
            '<$1M': len([p for p in all_pairs if p['volume'] < 1_000_000]),
            '$1M-$10M': len([p for p in all_pairs if 1_000_000 <= p['volume'] < 10_000_000]),
            '$10M-$50M': len([p for p in all_pairs if 10_000_000 <= p['volume'] < 50_000_000]),
            '>$50M': len([p for p in all_pairs if p['volume'] >= 50_000_000])
        }
        
        print("\n📈 Volume Distribution:")
        for range_name, count in vol_ranges.items():
            print(f"  {range_name}: {count} pairs")
        
        print("\n🎯 Top 15 Manipulation Targets:")
        print("-" * 70)
        print(f"{'Symbol':<15} {'Volume':>15} {'24h Change':>10} {'Volatility':>10}")
        print("-" * 70)
        
        for pair in selected[:15]:
            print(f"{pair['symbol']:<15} ${pair['volume']:>14,.0f} {pair['change']:>9.2f}% {pair['volatility']:>9.2f}%")
        
        return [p['symbol'] for p in selected]
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return []

if __name__ == "__main__":
    print("🎯 MEXC Manipulation Target Selector")
    print("=" * 70)
    
    targets = get_manipulation_targets()
    
    if targets:
        print("\n✅ Ready to monitor!")
        print("\nTo monitor all targets (50 pairs):")
        print("  cd src")
        print("  python monitor_optimized.py --mode fast --file ../watchlists/manipulation_targets_auto.txt")
        print("\nFor high volatility only (20 pairs):")
        print("  python monitor_optimized.py --mode balanced --file ../watchlists/high_volatility_targets.txt")
        print("\n💡 Tip: Use 'balanced' mode for 20 pairs, 'fast' mode for 50 pairs")