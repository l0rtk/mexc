#!/usr/bin/env python3
"""
Run the multi-pair monitor with Telegram alerts

This script starts monitoring multiple low-volume MEXC futures pairs
and sends alerts to a Telegram channel when manipulation is detected.
"""

import os
import sys
import asyncio
import signal
import logging
from datetime import datetime
from dotenv import load_dotenv

# Add src to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from multi_pair_monitor import main


def setup_signal_handlers():
    """Set up graceful shutdown handlers"""
    def signal_handler(signum, frame):
        print(f"\n\n🛑 Received shutdown signal. Cleaning up...")
        # The main loop will handle the actual shutdown
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)


def check_environment():
    """Check and validate environment configuration"""
    issues = []
    
    # Check MongoDB
    mongodb_uri = os.getenv('MONGODB_URI', 'mongodb://localhost:27017/')
    if not mongodb_uri:
        issues.append("MONGODB_URI not set")
    
    # Check Telegram
    bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
    channel_id = os.getenv('TELEGRAM_CHANNEL_ID')
    
    telegram_configured = bool(bot_token and channel_id)
    
    return {
        'telegram_configured': telegram_configured,
        'bot_token': bot_token,
        'channel_id': channel_id,
        'mongodb_uri': mongodb_uri,
        'issues': issues
    }


def print_startup_banner():
    """Print startup banner with configuration info"""
    print("\n" + "="*70)
    print("🚀 MEXC FUTURES MULTI-PAIR MONITOR")
    print("="*70)
    print(f"📅 Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"📁 Working Directory: {os.getcwd()}")
    print(f"🐍 Python Version: {sys.version.split()[0]}")
    

def print_configuration():
    """Print monitor configuration"""
    print("\n📊 Monitor Configuration:")
    print("├─ Pairs: Top 100 futures pairs")
    print("├─ Update Interval: 30 seconds")
    print("├─ Alert System: Advanced multi-signal detection")
    print("├─ Alert Cooldown: 5 minutes per symbol")
    print("├─ Rate Limiting: 0.2s delay between order book requests")
    print("└─ Features: AI pattern detection, manipulation alerts")
    print("\n🎯 Advanced Signal Detection:")
    print("├─ Volume Explosion: >5x with price confirmation")
    print("├─ RSI Divergence: Price/momentum divergence patterns")
    print("├─ Momentum Shifts: Rapid acceleration/reversal detection")
    print("├─ Liquidity Traps: Order book manipulation patterns")
    print("└─ Accumulation/Distribution: Smart money detection")
    

def main_wrapper():
    """Main wrapper with better error handling and startup checks"""
    # Load environment variables
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
    if os.path.exists(env_path):
        load_dotenv(env_path)
        print(f"✅ Loaded environment from: {env_path}")
    else:
        load_dotenv()
        print("⚠️  No .env file found, using system environment variables")
    
    # Print startup banner
    print_startup_banner()
    
    # Check environment
    env_check = check_environment()
    
    # MongoDB check
    print(f"\n🗄️  Database: {env_check['mongodb_uri']}")
    
    # Telegram check
    if not env_check['telegram_configured']:
        print("\n⚠️  WARNING: Telegram not configured!")
        print("\n📱 To enable Telegram alerts:")
        print("1. Create a bot with @BotFather on Telegram")
        print("2. Get your bot token from BotFather")
        print("3. Create a channel/group and add your bot as admin")
        print("4. Get your channel ID (@username or -100xxxxx)")
        print("5. Add to .env file:")
        print("   TELEGRAM_BOT_TOKEN=your_bot_token_here")
        print("   TELEGRAM_CHANNEL_ID=@your_channel_or_chat_id")
        print("\n❓ Continue without Telegram alerts? (y/N): ", end="")
        
        try:
            response = input().strip().lower()
            if response != 'y':
                print("👋 Exiting. Please configure Telegram first.")
                sys.exit(0)
        except KeyboardInterrupt:
            print("\n👋 Exiting...")
            sys.exit(0)
    else:
        print(f"\n✅ Telegram: Configured for {env_check['channel_id']}")
    
    # Print configuration
    print_configuration()
    
    # Check for issues
    if env_check['issues']:
        print("\n⚠️  Configuration Issues:")
        for issue in env_check['issues']:
            print(f"   - {issue}")
    
    print("\n" + "="*70)
    print("🎯 Starting monitor... Press Ctrl+C to stop")
    print("="*70 + "\n")
    
    # Set up signal handlers
    setup_signal_handlers()
    
    # Configure asyncio for better performance
    if sys.platform == 'win32':
        # Windows specific event loop policy
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    
    try:
        # Run the monitor
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n✋ Monitor stopped by user")
        print(f"🕒 Stopped: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    except Exception as e:
        print(f"\n❌ Fatal Error: {e}")
        logging.exception("Fatal error in main loop")
        sys.exit(1)
    finally:
        print("\n👋 Goodbye!")


if __name__ == "__main__":
    main_wrapper()