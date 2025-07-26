#!/usr/bin/env python3
"""
Simple script to monitor 3 pairs with optimal performance
"""

import subprocess
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'src'))

def main():
    print("MEXC Monitor - 3 Pairs Edition")
    print("=" * 50)
    print()
    
    # Default pairs
    pairs = ["AIXBT_USDT", "USUAL_USDT", "XMR_USDT"]
    
    # Mode selection
    print("Select monitoring mode:")
    print("1. Fast (5s updates, minimal features)")
    print("2. Balanced (10s updates, all key features)")
    print("3. Startup (10s updates, sensitive thresholds)")
    print("4. Use fast_monitor.py (legacy, but proven)")
    
    choice = input("\nEnter choice (1-4) [default: 3]: ").strip() or "3"
    
    # Custom pairs?
    custom = input("\nUse custom pairs? (y/N): ").strip().lower()
    if custom == 'y':
        pairs_input = input("Enter pairs (space-separated): ").strip()
        if pairs_input:
            pairs = pairs_input.split()
    
    print(f"\nMonitoring: {', '.join(pairs)}")
    
    # Run the appropriate monitor
    os.chdir('src')
    
    if choice == "1":
        cmd = ["python", "monitor_optimized.py", "--mode", "fast"] + pairs
    elif choice == "2":
        cmd = ["python", "monitor_optimized.py", "--mode", "balanced"] + pairs
    elif choice == "3":
        cmd = ["python", "monitor_optimized.py", "--mode", "startup"] + pairs
    elif choice == "4":
        cmd = ["python", "fast_monitor.py"] + pairs
    else:
        print("Invalid choice")
        return
    
    print(f"\nRunning: {' '.join(cmd)}")
    print("-" * 50)
    
    try:
        subprocess.run(cmd)
    except KeyboardInterrupt:
        print("\n\nMonitor stopped by user")

if __name__ == "__main__":
    main()