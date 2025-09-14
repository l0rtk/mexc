import logging
from typing import Dict, List, Optional
from datetime import datetime
from colorama import init, Fore, Style
import json

init(autoreset=True)
logger = logging.getLogger(__name__)


class AlertSystem:
    def __init__(self, enable_console: bool = True, enable_file: bool = False,
                 alert_file: str = "alerts.log"):
        self.enable_console = enable_console
        self.enable_file = enable_file
        self.alert_file = alert_file
        self.alert_counts = {}
        self.last_alerts = {}

    def format_large_order_alert(self, order) -> str:
        emoji = "🐋" if order.is_whale else "📊"
        side_color = Fore.GREEN if order.side == "BUY" else Fore.RED

        message = f"{emoji} {side_color}LARGE {order.side} ORDER{Style.RESET_ALL}\n"
        message += f"Symbol: {Fore.YELLOW}{order.symbol}{Style.RESET_ALL}\n"
        message += f"Price: ${order.price:,.2f}\n"
        message += f"Volume: {order.volume:,.2f}\n"
        message += f"Value: ${order.volume_usdt:,.2f}\n"
        message += f"Book %: {order.percentage_of_book:.1f}%\n"
        message += f"Time: {order.timestamp.strftime('%H:%M:%S')}"

        return message

    def format_wall_alert(self, wall: Dict) -> str:
        emoji = "🚧"
        wall_type = wall['type']
        color = Fore.GREEN if 'BUY' in wall_type else Fore.RED

        message = f"{emoji} {color}{wall_type} DETECTED{Style.RESET_ALL}\n"
        message += f"Symbol: {Fore.YELLOW}{wall['symbol']}{Style.RESET_ALL}\n"
        message += f"Price: ${wall['price']:,.2f}\n"
        message += f"Volume: {wall['volume']:,.2f}\n"
        message += f"Value: ${wall['volume_usdt']:,.2f}\n"
        message += f"Size vs Avg: {wall['multiplier']:.1f}x\n"
        message += f"Position: #{wall['position']}"

        return message

    def format_aggressive_trading_alert(self, data: Dict) -> str:
        emoji = "⚡"
        dominant_color = Fore.GREEN if data['dominant_side'] == 'BUY' else Fore.RED

        message = f"{emoji} {dominant_color}AGGRESSIVE {data['dominant_side']} DETECTED{Style.RESET_ALL}\n"
        message += f"Symbol: {Fore.YELLOW}{data['symbol']}{Style.RESET_ALL}\n"
        message += f"Buy Volume: ${data['buy_volume_usdt']:,.2f} ({data['buy_percentage']:.1f}%)\n"
        message += f"Sell Volume: ${data['sell_volume_usdt']:,.2f} ({data['sell_percentage']:.1f}%)\n"
        message += f"Aggression Score: {data['aggression_score']:.1f}/50\n"
        message += f"Time Window: {data['time_window']}s"

        return message

    def format_volume_surge_alert(self, surge: Dict) -> str:
        emoji = "🚀"

        message = f"{emoji} {Fore.MAGENTA}VOLUME SURGE DETECTED{Style.RESET_ALL}\n"
        message += f"Symbol: {Fore.YELLOW}{surge['symbol']}{Style.RESET_ALL}\n"
        message += f"Current Volume: ${surge['current_volume']:,.2f}\n"
        message += f"Average Volume: ${surge['average_volume']:,.2f}\n"
        message += f"Surge: {surge['surge_multiplier']:.1f}x normal\n"
        message += f"Baseline: {surge['baseline_minutes']} minutes"

        return message

    def format_coordinated_trades_alert(self, coordinated: Dict) -> str:
        emoji = "🎯"
        side_color = Fore.GREEN if coordinated['side'] == 'BUY' else Fore.RED

        message = f"{emoji} {side_color}COORDINATED {coordinated['side']} DETECTED{Style.RESET_ALL}\n"
        message += f"Symbol: {Fore.YELLOW}{coordinated['symbol']}{Style.RESET_ALL}\n"
        message += f"Trade Count: {coordinated['trade_count']}\n"
        message += f"Total Volume: ${coordinated['total_volume_usdt']:,.2f}\n"
        message += f"Avg Price: ${coordinated['avg_price']:,.2f}\n"
        message += f"Time Span: {coordinated['time_span']}s"

        return message

    def format_spoofing_alert(self, spoof: Dict) -> str:
        emoji = "⚠️"
        side_color = Fore.GREEN if spoof['side'] == 'BUY' else Fore.RED

        message = f"{emoji} {Fore.YELLOW}POTENTIAL SPOOFING{Style.RESET_ALL}\n"
        message += f"{side_color}{spoof['side']} orders at ${spoof['price']:,.2f}{Style.RESET_ALL}\n"
        message += f"Appearances: {spoof['appearances']} times\n"
        message += f"Avg Volume: ${spoof['avg_volume_usdt']:,.2f}\n"
        message += f"Variation: ${spoof['volume_variation']:,.2f}"

        return message

    def send_alert(self, alert_type: str, data: any, priority: str = "MEDIUM"):
        try:
            if alert_type == "large_order":
                message = self.format_large_order_alert(data)
            elif alert_type == "wall":
                message = self.format_wall_alert(data)
            elif alert_type == "aggressive_trading":
                message = self.format_aggressive_trading_alert(data)
            elif alert_type == "volume_surge":
                message = self.format_volume_surge_alert(data)
            elif alert_type == "coordinated_trades":
                message = self.format_coordinated_trades_alert(data)
            elif alert_type == "spoofing":
                message = self.format_spoofing_alert(data)
            else:
                message = f"Unknown alert type: {alert_type}"

            if self.enable_console:
                self._print_to_console(message, priority)

            if self.enable_file:
                self._write_to_file(alert_type, data, priority)

            self._update_alert_stats(alert_type)

        except Exception as e:
            logger.error(f"Error sending alert: {e}")

    def _print_to_console(self, message: str, priority: str):
        separator = "=" * 50

        if priority == "HIGH":
            print(f"\n{Fore.RED}{separator}{Style.RESET_ALL}")
            print(message)
            print(f"{Fore.RED}{separator}{Style.RESET_ALL}\n")
        elif priority == "MEDIUM":
            print(f"\n{Fore.YELLOW}{separator}{Style.RESET_ALL}")
            print(message)
            print(f"{Fore.YELLOW}{separator}{Style.RESET_ALL}\n")
        else:
            print(f"\n{separator}")
            print(message)
            print(f"{separator}\n")

    def _write_to_file(self, alert_type: str, data: any, priority: str):
        try:
            alert_entry = {
                'timestamp': datetime.now().isoformat(),
                'type': alert_type,
                'priority': priority,
                'data': self._serialize_data(data)
            }

            with open(self.alert_file, 'a') as f:
                f.write(json.dumps(alert_entry) + '\n')
        except Exception as e:
            logger.error(f"Error writing to alert file: {e}")

    def _serialize_data(self, data: any) -> Dict:
        if hasattr(data, '__dict__'):
            result = {}
            for key, value in data.__dict__.items():
                if isinstance(value, datetime):
                    result[key] = value.isoformat()
                else:
                    result[key] = value
            return result
        elif isinstance(data, dict):
            return data
        else:
            return {'data': str(data)}

    def _update_alert_stats(self, alert_type: str):
        if alert_type not in self.alert_counts:
            self.alert_counts[alert_type] = 0
        self.alert_counts[alert_type] += 1
        self.last_alerts[alert_type] = datetime.now()

    def get_alert_summary(self) -> Dict:
        return {
            'total_alerts': sum(self.alert_counts.values()),
            'by_type': self.alert_counts,
            'last_alerts': {k: v.isoformat() for k, v in self.last_alerts.items()}
        }