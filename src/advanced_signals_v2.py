"""
Advanced signal detection V2 with funding, liquidations, and statistical analysis
"""

from typing import Dict, List, Optional, Tuple
from datetime import datetime, timezone
import numpy as np

from advanced_signals import AdvancedSignalDetector


class AdvancedSignalDetectorV2(AdvancedSignalDetector):
    """Enhanced signal detection with new data sources"""
    
    def __init__(self):
        super().__init__()
        
        # Updated weights for more signals
        self.signal_weights = {
            'volume_explosion': 0.2,
            'rsi_divergence': 0.15,
            'momentum_shift': 0.15,
            'liquidity_trap': 0.1,
            'accumulation': 0.1,
            'liquidation_squeeze': 0.15,
            'funding_arbitrage': 0.1,
            'hidden_accumulation': 0.05
        }
    
    def detect_liquidation_squeeze(self, data: Dict, liquidation_data: Dict, 
                                  funding_data: Dict) -> Tuple[bool, float, str]:
        """
        Detect liquidation squeeze patterns
        High funding + heavy long liquidations + overbought = short squeeze ending
        """
        if not liquidation_data or not funding_data:
            return False, 0, ""
        
        funding_rate = funding_data.get('current_rate', 0)
        long_liqs = liquidation_data.get('long_liquidations_1h', 0)
        short_liqs = liquidation_data.get('short_liquidations_1h', 0)
        rsi = data['indicators'].get('rsi_14', 50)
        volume_ratio = data['volume_analysis']['spike_magnitude']
        
        # Pattern 1: Short squeeze ending (time to short)
        if (funding_rate > 0.001 and  # High funding (longs pay shorts)
            long_liqs > short_liqs * 5 and  # Heavy long liquidations
            rsi > 75 and  # Overbought
            volume_ratio > 4):  # High volume
            
            confidence = min(0.9, (funding_rate / 0.002) * (rsi - 70) / 30)
            return True, confidence, f"Short squeeze ending: Funding {funding_rate:.3%}, RSI {rsi}"
        
        # Pattern 2: Long squeeze ending (time to long)
        if (funding_rate < -0.0005 and  # Negative funding (shorts pay longs)
            short_liqs > long_liqs * 3 and  # Heavy short liquidations
            rsi < 25 and  # Oversold
            volume_ratio > 3):
            
            confidence = min(0.85, abs(funding_rate / 0.001) * (30 - rsi) / 30)
            return True, confidence, f"Long squeeze ending: Funding {funding_rate:.3%}, RSI {rsi}"
        
        # Pattern 3: Cascade imminent
        cascade_prob = liquidation_data.get('cascade_probability', 0)
        if cascade_prob > 0.7 and volume_ratio > 2:
            direction = liquidation_data.get('cascade_direction', 'unknown')
            confidence = cascade_prob * 0.8
            return True, confidence, f"Liquidation cascade {cascade_prob:.0%} probability ({direction})"
        
        return False, 0, ""
    
    def detect_funding_arbitrage(self, data: Dict, funding_data: Dict, 
                               order_book: Dict = None) -> Tuple[bool, float, str]:
        """
        Detect funding arbitrage opportunities
        High funding + hours to funding < 1 + favorable technicals
        """
        if not funding_data:
            return False, 0, ""
        
        funding_rate = funding_data.get('current_rate', 0)
        hours_to_funding = funding_data.get('hours_to_funding', 8)
        rsi = data['indicators'].get('rsi_14', 50)
        
        # Need significant funding rate
        if abs(funding_rate) < 0.0015:  # Less than 0.15%
            return False, 0, ""
        
        # Calculate expected return (funding for remaining hours)
        expected_funding = abs(funding_rate) * (hours_to_funding / 8)
        
        # Pattern 1: Short for funding (positive funding)
        if funding_rate > 0.002 and hours_to_funding < 2:
            # Better if also technically overbought
            if rsi > 65:
                confidence = min(0.8, (funding_rate / 0.003) * (rsi - 60) / 40)
                daily_rate = funding_rate * 3  # 3 funding periods per day
                return True, confidence, f"Funding SHORT: {funding_rate:.3%} ({daily_rate:.2%} daily), {hours_to_funding:.1f}h left"
            elif order_book and order_book.get('imbalance_ratio', 1) < 0.7:
                # Or if order book shows selling pressure
                confidence = 0.6
                return True, confidence, f"Funding arbitrage: {funding_rate:.3%} rate, weak bids"
        
        # Pattern 2: Long for funding (negative funding)
        if funding_rate < -0.001 and hours_to_funding < 2:
            if rsi < 40:
                confidence = min(0.8, abs(funding_rate / 0.002) * (40 - rsi) / 40)
                daily_rate = funding_rate * 3
                return True, confidence, f"Funding LONG: {funding_rate:.3%} ({daily_rate:.2%} daily), {hours_to_funding:.1f}h left"
        
        return False, 0, ""
    
    def detect_hidden_accumulation_v2(self, data: Dict, stats_data: Dict,
                                    funding_data: Dict = None) -> Tuple[bool, float, str]:
        """
        Enhanced hidden accumulation detection with statistical significance
        """
        rsi = data['indicators'].get('rsi_14', 50)
        volume_ratio = data['volume_analysis']['volume_ratio_5m']
        price_change = data['price_movement']['change_5m']
        
        # Check statistical significance
        if stats_data:
            volume_zscore = stats_data.get('zscore', {}).get('volume_zscore', 0)
            is_outlier = stats_data.get('zscore', {}).get('is_outlier', False)
        else:
            volume_zscore = 0
            is_outlier = False
        
        # Pattern 1: Statistically significant accumulation
        if (rsi < 35 and 
            volume_ratio > 2 and 
            abs(price_change) < 1 and  # Price stable despite volume
            volume_zscore > 2):  # Statistically significant volume
            
            confidence = min(0.85, (35 - rsi) / 35 * volume_zscore / 3)
            
            # Boost confidence if funding is negative (cheaper to hold longs)
            if funding_data and funding_data.get('current_rate', 0) < -0.0005:
                confidence *= 1.2
            
            return True, confidence, f"Smart accumulation: RSI {rsi}, Volume Z-score {volume_zscore:.1f}"
        
        # Pattern 2: Distribution with statistical significance
        if (rsi > 70 and
            volume_ratio > 2 and
            price_change < 0.5 and  # Price struggling despite buying
            is_outlier):
            
            confidence = min(0.8, (rsi - 70) / 30)
            return True, confidence, f"Hidden distribution: RSI {rsi}, statistical outlier"
        
        return False, 0, ""
    
    def detect_timeframe_divergence_signal(self, tf_divergence: Dict, 
                                         data: Dict) -> Tuple[bool, float, str]:
        """
        Detect signals from timeframe divergences
        """
        if not tf_divergence or not tf_divergence.get('has_divergence'):
            return False, 0, ""
        
        div_type = tf_divergence.get('divergence_type')
        div_strength = tf_divergence.get('divergence_strength', 0)
        volume_ratio = data['volume_analysis']['spike_magnitude']
        
        # Need volume confirmation
        if volume_ratio < 2:
            return False, 0, ""
        
        confidence = min(0.7, div_strength * 0.3)
        
        if div_type == 'bullish':
            return True, confidence, f"Bullish TF divergence: 15m down, 1m up strongly"
        elif div_type == 'bearish':
            return True, confidence, f"Bearish TF divergence: 15m up, 1m down strongly"
        
        return False, 0, ""
    
    def calculate_composite_signal_v2(self, data: Dict, order_book: Dict = None,
                                    funding_data: Dict = None, 
                                    liquidation_data: Dict = None,
                                    stats_data: Dict = None,
                                    tf_divergence: Dict = None) -> Dict:
        """
        Enhanced composite signal calculation with all data sources
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
            ('accumulation', self.detect_accumulation_distribution(data, order_book)),
            ('liquidation_squeeze', self.detect_liquidation_squeeze(data, liquidation_data or {}, funding_data or {})),
            ('funding_arbitrage', self.detect_funding_arbitrage(data, funding_data or {}, order_book)),
            ('hidden_accumulation', self.detect_hidden_accumulation_v2(data, stats_data or {}, funding_data)),
            ('timeframe_divergence', self.detect_timeframe_divergence_signal(tf_divergence or {}, data))
        ]
        
        active_signals = []
        for name, (triggered, confidence, description) in detectors:
            if triggered and confidence > 0:
                weight = self.signal_weights.get(name, 0.1)
                weighted_confidence += confidence * weight
                total_confidence += confidence
                active_signals.append({
                    'type': name,
                    'confidence': confidence,
                    'description': description,
                    'weight': weight
                })
                signals.append(description)
        
        # Apply statistical adjustments
        if stats_data:
            # Boost confidence for statistical outliers
            if stats_data.get('statistical_significance'):
                weighted_confidence *= 1.3
            
            # Apply dynamic threshold adjustment
            if stats_data.get('should_alert') == False and weighted_confidence < 0.8:
                # Statistical analysis says don't alert
                weighted_confidence *= 0.7
        
        # Calculate final metrics
        num_signals = len(active_signals)
        if num_signals > 0:
            avg_confidence = total_confidence / num_signals
            
            # Determine action with more nuanced approach
            price_direction = data['price_movement']['change_5m']
            
            # Check for specific high-confidence patterns
            has_liquidation_signal = any(s['type'] == 'liquidation_squeeze' for s in active_signals)
            has_funding_signal = any(s['type'] == 'funding_arbitrage' for s in active_signals)
            
            if weighted_confidence > 0.7 or (num_signals >= 3 and avg_confidence > 0.6):
                if has_funding_signal:
                    # Funding arbitrage specific actions
                    funding_position = funding_data.get('favorable_position', 'neutral') if funding_data else 'neutral'
                    if funding_position == 'short':
                        action = 'FUNDING_SHORT'
                    elif funding_position == 'long':
                        action = 'FUNDING_LONG'
                    else:
                        action = 'STRONG_BUY' if price_direction >= 0 else 'STRONG_SELL'
                else:
                    action = 'STRONG_BUY' if price_direction >= 0 else 'STRONG_SELL'
                risk_level = 'EXTREME'
            elif weighted_confidence > 0.5 or (num_signals >= 2 and avg_confidence > 0.5):
                action = 'BUY' if price_direction >= 0 else 'SELL'
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
            'description': ' | '.join(signals[:3]) if signals else 'No significant patterns'
        }


# Helper function to use new detector
def enhance_alert_detection_v2(analysis: Dict, order_book: Dict = None,
                             funding_data: Dict = None, liquidation_data: Dict = None,
                             stats_data: Dict = None, tf_divergence: Dict = None) -> Dict:
    """Enhanced alert detection with all data sources"""
    detector = AdvancedSignalDetectorV2()
    return detector.calculate_composite_signal_v2(
        analysis, order_book, funding_data, liquidation_data, stats_data, tf_divergence
    )