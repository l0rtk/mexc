"""
Advanced signal detection based on pattern analysis
"""

from typing import Dict, List, Optional, Tuple
from datetime import datetime, timezone
import numpy as np


class AdvancedSignalDetector:
    """Enhanced signal detection with multiple strategies"""
    
    def __init__(self):
        # Signal weights based on backtesting
        self.signal_weights = {
            'volume_explosion': 0.3,
            'rsi_divergence': 0.2,
            'momentum_shift': 0.2,
            'liquidity_trap': 0.15,
            'accumulation': 0.15
        }
        
    def detect_volume_explosion(self, data: Dict) -> Tuple[bool, float, str]:
        """
        Detect explosive volume with price confirmation
        Returns: (signal_triggered, confidence, description)
        """
        volume_ratio = data['volume_analysis']['spike_magnitude']
        price_change = data['price_movement']['change_5m']
        
        # Pattern 1: Massive volume with price movement
        if volume_ratio > 5 and abs(price_change) > 3:
            confidence = min(0.9, volume_ratio / 10)
            return True, confidence, f"Volume explosion {volume_ratio:.1f}x with {price_change:+.1f}% price move"
        
        # Pattern 2: Steady volume increase
        if volume_ratio > 3 and data['volume_analysis'].get('volume_trend', 0) > 1.5:
            confidence = 0.7
            return True, confidence, f"Sustained volume increase {volume_ratio:.1f}x"
        
        return False, 0, ""
    
    def detect_rsi_divergence(self, data: Dict, price_history: List[float] = None) -> Tuple[bool, float, str]:
        """
        Detect RSI divergence patterns
        """
        rsi = data['indicators'].get('rsi_14')
        if not rsi:
            return False, 0, ""
        
        price_change = data['price_movement']['change_5m']
        
        # Bullish divergence: Price down, RSI up (oversold bounce)
        if rsi < 30 and price_change < -1:
            confidence = (30 - rsi) / 30  # More oversold = higher confidence
            return True, confidence, f"Bullish divergence: RSI {rsi:.0f} with price down {price_change:.1f}%"
        
        # Bearish divergence: Price up, RSI down (overbought reversal)
        if rsi > 70 and price_change > 1:
            confidence = (rsi - 70) / 30
            return True, confidence, f"Bearish divergence: RSI {rsi:.0f} with price up {price_change:.1f}%"
        
        # Hidden bullish divergence
        if 30 < rsi < 50 and price_change > 2:
            confidence = 0.6
            return True, confidence, f"Hidden bullish divergence: RSI {rsi:.0f}"
        
        return False, 0, ""
    
    def detect_momentum_shift(self, data: Dict) -> Tuple[bool, float, str]:
        """
        Detect sudden momentum shifts that indicate manipulation
        """
        price_change_1m = data['price_movement'].get('change_1m', 0)
        price_change_5m = data['price_movement']['change_5m']
        volume_ratio = data['volume_analysis']['spike_magnitude']
        
        # Rapid acceleration
        if abs(price_change_1m) > 1 and abs(price_change_5m) > 2:
            if price_change_1m * price_change_5m > 0:  # Same direction
                momentum = abs(price_change_1m) / max(0.1, abs(price_change_5m - price_change_1m))
                if momentum > 2 and volume_ratio > 2:
                    confidence = min(0.85, momentum / 5)
                    direction = "up" if price_change_1m > 0 else "down"
                    return True, confidence, f"Momentum surge {direction}: {price_change_1m:+.1f}% in 1m"
        
        # V-shaped reversal
        if price_change_1m * price_change_5m < 0 and abs(price_change_1m) > 1:
            confidence = 0.7
            return True, confidence, f"V-reversal detected: {price_change_5m:+.1f}% to {price_change_1m:+.1f}%"
        
        return False, 0, ""
    
    def detect_liquidity_trap(self, data: Dict, order_book: Dict) -> Tuple[bool, float, str]:
        """
        Detect liquidity trap patterns using order book data
        """
        if not order_book:
            return False, 0, ""
        
        spread = order_book.get('spread_bps', 0)
        liquidity = order_book.get('liquidity_score', 1)
        spoofing = order_book.get('spoofing_score', 0)
        
        # Wide spread with low liquidity = trap
        if spread > 50 and liquidity < 0.3:
            confidence = 0.8
            return True, confidence, f"Liquidity trap: {spread:.0f}bps spread, {liquidity:.2f} liquidity"
        
        # Spoofing with price movement
        if spoofing > 0.6 and abs(data['price_movement']['change_5m']) > 1:
            confidence = spoofing
            return True, confidence, f"Spoofing detected: {spoofing:.2f} score"
        
        return False, 0, ""
    
    def detect_accumulation_distribution(self, data: Dict, order_book: Dict = None) -> Tuple[bool, float, str]:
        """
        Detect accumulation/distribution phases
        """
        rsi = data['indicators'].get('rsi_14', 50)
        volume_ratio = data['volume_analysis']['spike_magnitude']
        price_change = data['price_movement']['change_5m']
        
        # Accumulation: Low RSI, increasing volume, stable price
        if rsi < 40 and volume_ratio > 2 and abs(price_change) < 1:
            confidence = 0.7
            return True, confidence, f"Accumulation phase: RSI {rsi:.0f}, volume {volume_ratio:.1f}x"
        
        # Distribution: High RSI, high volume, topping price
        if rsi > 70 and volume_ratio > 2 and price_change < 0:
            confidence = 0.75
            return True, confidence, f"Distribution phase: RSI {rsi:.0f}, volume {volume_ratio:.1f}x"
        
        # Smart money accumulation (order book)
        if order_book and order_book.get('imbalance_ratio', 1) > 1.5 and rsi < 45:
            confidence = 0.65
            return True, confidence, f"Smart accumulation: {order_book['imbalance_ratio']:.1f} bid/ask ratio"
        
        return False, 0, ""
    
    def calculate_composite_signal(self, data: Dict, order_book: Dict = None) -> Dict:
        """
        Calculate composite signal from all detectors
        """
        signals = []
        total_confidence = 0
        weighted_confidence = 0
        
        # Run all detectors
        detectors = [
            ('volume_explosion', self.detect_volume_explosion(data)),
            ('rsi_divergence', self.detect_rsi_divergence(data)),
            ('momentum_shift', self.detect_momentum_shift(data)),
            ('liquidity_trap', self.detect_liquidity_trap(data, order_book)),
            ('accumulation', self.detect_accumulation_distribution(data, order_book))
        ]
        
        active_signals = []
        for name, (triggered, confidence, description) in detectors:
            if triggered:
                weight = self.signal_weights.get(name, 0.2)
                weighted_confidence += confidence * weight
                total_confidence += confidence
                active_signals.append({
                    'type': name,
                    'confidence': confidence,
                    'description': description,
                    'weight': weight
                })
                signals.append(description)
        
        # Calculate final metrics
        num_signals = len(active_signals)
        if num_signals > 0:
            avg_confidence = total_confidence / num_signals
            
            # Determine action
            if weighted_confidence > 0.7 or (num_signals >= 3 and avg_confidence > 0.6):
                action = 'STRONG_BUY' if data['price_movement']['change_5m'] >= 0 else 'STRONG_SELL'
                risk_level = 'EXTREME'
            elif weighted_confidence > 0.5 or (num_signals >= 2 and avg_confidence > 0.5):
                action = 'BUY' if data['price_movement']['change_5m'] >= 0 else 'SELL'
                risk_level = 'HIGH'
            else:
                action = 'WATCH'
                risk_level = 'MEDIUM'
        else:
            avg_confidence = 0
            weighted_confidence = 0
            action = 'NEUTRAL'
            risk_level = 'LOW'
        
        return {
            'timestamp': datetime.now(timezone.utc),
            'action': action,
            'risk_level': risk_level,
            'confidence': weighted_confidence,
            'num_signals': num_signals,
            'signals': active_signals,
            'description': ' | '.join(signals) if signals else 'No significant signals'
        }


def enhance_alert_detection(data: Dict, order_book: Dict = None) -> Dict:
    """
    Enhanced alert detection using advanced signals
    """
    detector = AdvancedSignalDetector()
    
    # Get composite signal
    signal = detector.calculate_composite_signal(data, order_book)
    
    # Add market context
    signal['market_context'] = {
        'symbol': data.get('symbol', 'UNKNOWN'),
        'price': data['ohlcv']['close'],
        'volume': data['ohlcv']['volume'],
        'rsi': data['indicators'].get('rsi_14'),
        'volume_ratio': data['volume_analysis']['spike_magnitude'],
        'price_change_5m': data['price_movement']['change_5m']
    }
    
    return signal