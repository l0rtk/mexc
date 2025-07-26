"""
Monitor configuration for performance tuning
"""

import os
from typing import Dict, Any

class MonitorConfig:
    """Configuration for monitor optimization"""
    
    def __init__(self, mode: str = "balanced"):
        """
        Initialize config based on mode:
        - fast: Speed optimized, may miss some signals
        - balanced: Good speed with decent signals
        - thorough: All features, slower but comprehensive
        - startup: For first run without historical data
        """
        self.mode = mode
        self.config = self._get_config_for_mode(mode)
    
    def _get_config_for_mode(self, mode: str) -> Dict[str, Any]:
        """Get configuration based on mode"""
        
        configs = {
            "fast": {
                # Feature flags
                "enable_liquidation": False,  # Saves 6s per symbol
                "enable_multi_timeframe": False,  # Saves 2s per symbol
                "enable_statistics": False,  # Saves 0.3s per symbol
                "enable_funding": True,  # Keep - it's fast when cached
                "enable_order_book": True,  # Keep - useful for signals
                
                # Data settings
                "candle_limit": 30,  # Reduced from 60
                "order_book_depth": 5,  # Reduced from 10-20
                "update_interval": 5,  # Faster updates
                
                # Thresholds (more sensitive)
                "volume_spike_threshold": 2.0,  # From 5.0
                "rsi_oversold": 35,  # From 30
                "rsi_overbought": 65,  # From 70
                "price_change_threshold": 1.0,  # From 3.0
                "confidence_threshold": 0.5,  # From 0.7
                
                # Processing
                "max_parallel_requests": 10,
                "request_timeout": 3,  # seconds
                "cache_duration": 60,  # seconds
            },
            
            "balanced": {
                # Feature flags
                "enable_liquidation": False,  # Still skip - too slow
                "enable_multi_timeframe": True,
                "enable_statistics": True,
                "enable_funding": True,
                "enable_order_book": True,
                
                # Data settings
                "candle_limit": 60,
                "order_book_depth": 10,
                "update_interval": 10,
                
                # Thresholds (moderate)
                "volume_spike_threshold": 3.0,
                "rsi_oversold": 30,
                "rsi_overbought": 70,
                "price_change_threshold": 2.0,
                "confidence_threshold": 0.6,
                
                # Processing
                "max_parallel_requests": 5,
                "request_timeout": 5,
                "cache_duration": 300,
            },
            
            "thorough": {
                # Feature flags - all enabled
                "enable_liquidation": True,
                "enable_multi_timeframe": True,
                "enable_statistics": True,
                "enable_funding": True,
                "enable_order_book": True,
                
                # Data settings
                "candle_limit": 100,
                "order_book_depth": 20,
                "update_interval": 15,
                
                # Thresholds (conservative)
                "volume_spike_threshold": 5.0,
                "rsi_oversold": 25,
                "rsi_overbought": 75,
                "price_change_threshold": 3.0,
                "confidence_threshold": 0.7,
                
                # Processing
                "max_parallel_requests": 3,
                "request_timeout": 10,
                "cache_duration": 600,
            },
            
            "startup": {
                # For first run without history
                # Feature flags
                "enable_liquidation": False,
                "enable_multi_timeframe": False,
                "enable_statistics": False,  # No history yet
                "enable_funding": True,
                "enable_order_book": True,
                
                # Data settings
                "candle_limit": 60,
                "order_book_depth": 5,
                "update_interval": 10,
                
                # Thresholds (very sensitive for testing)
                "volume_spike_threshold": 1.5,
                "rsi_oversold": 40,
                "rsi_overbought": 60,
                "price_change_threshold": 0.5,
                "confidence_threshold": 0.4,
                
                # Processing
                "max_parallel_requests": 5,
                "request_timeout": 5,
                "cache_duration": 60,
            }
        }
        
        return configs.get(mode, configs["balanced"])
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get config value"""
        return self.config.get(key, default)
    
    def update(self, updates: Dict[str, Any]):
        """Update config values"""
        self.config.update(updates)
    
    def __str__(self) -> str:
        """String representation"""
        return f"MonitorConfig(mode={self.mode})"
    
    def summary(self) -> str:
        """Get config summary"""
        features = []
        if self.get("enable_liquidation"):
            features.append("Liquidation")
        if self.get("enable_multi_timeframe"):
            features.append("Multi-TF")
        if self.get("enable_statistics"):
            features.append("Statistics")
        if self.get("enable_funding"):
            features.append("Funding")
        if self.get("enable_order_book"):
            features.append("OrderBook")
        
        return (f"Mode: {self.mode}\n"
                f"Features: {', '.join(features)}\n"
                f"Update: {self.get('update_interval')}s\n"
                f"Volume threshold: {self.get('volume_spike_threshold')}x")


# Global config instance
_config = None

def get_config() -> MonitorConfig:
    """Get global config instance"""
    global _config
    if _config is None:
        mode = os.getenv("MONITOR_MODE", "balanced")
        _config = MonitorConfig(mode)
    return _config

def set_config_mode(mode: str):
    """Set config mode"""
    global _config
    _config = MonitorConfig(mode)