import asyncio
from typing import Dict, List, Callable, Optional
from datetime import datetime
from database import get_active_alerts, create_alert


class AlertManager:
    """Manage and trigger alerts for token movements."""
    
    def __init__(self):
        self.alerts = []
        self.subscribers: Dict[str, List[Callable]] = {}
        self.alert_history = []
    
    def subscribe(self, alert_type: str, callback: Callable):
        """Subscribe to alert types."""
        if alert_type not in self.subscribers:
            self.subscribers[alert_type] = []
        self.subscribers[alert_type].append(callback)
    
    async def trigger_alert(self, alert_type: str, data: Dict):
        """Trigger an alert and notify all subscribers."""
        alert_event = {
            'type': alert_type,
            'data': data,
            'timestamp': datetime.now().isoformat(),
        }
        
        self.alert_history.append(alert_event)
        
        if alert_type in self.subscribers:
            for callback in self.subscribers[alert_type]:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback(alert_event)
                    else:
                        callback(alert_event)
                except Exception as e:
                    print(f"Error in alert callback: {e}")
    
    async def check_price_alert(self, token_address: str, current_price: float, threshold: float, alert_type: str = 'price_spike'):
        """Check if price crosses threshold."""
        if alert_type == 'price_spike' and current_price > threshold:
            await self.trigger_alert('price_spike', {
                'token_address': token_address,
                'current_price': current_price,
                'threshold': threshold,
                'spike_percentage': ((current_price - threshold) / threshold) * 100,
            })
        elif alert_type == 'price_drop' and current_price < threshold:
            await self.trigger_alert('price_drop', {
                'token_address': token_address,
                'current_price': current_price,
                'threshold': threshold,
                'drop_percentage': ((threshold - current_price) / threshold) * 100,
            })
    
    async def check_holder_concentration_alert(self, token_address: str, top_10_percentage: float):
        """Alert when holder concentration is high."""
        if top_10_percentage > 70:
            await self.trigger_alert('high_concentration', {
                'token_address': token_address,
                'top_10_percentage': top_10_percentage,
                'risk_level': 'CRITICAL',
            })
    
    async def check_smart_money_alert(self, token_address: str, smart_buys: List[Dict]):
        """Alert when smart money buys a token."""
        if smart_buys:
            await self.trigger_alert('smart_money_buy', {
                'token_address': token_address,
                'smart_money_count': len(smart_buys),
                'buys': smart_buys,
            })
    
    async def check_dev_wallet_alert(self, token_address: str, dev_holding_percentage: float):
        """Alert when dev holdings are detected."""
        if dev_holding_percentage > 30:
            await self.trigger_alert('high_dev_holdings', {
                'token_address': token_address,
                'dev_percentage': dev_holding_percentage,
                'risk_level': 'HIGH' if dev_holding_percentage > 50 else 'MEDIUM',
            })
    
    async def check_volume_alert(self, token_address: str, volume_24h: float, threshold: float = 100_000):
        """Alert when volume spikes."""
        if volume_24h > threshold:
            await self.trigger_alert('volume_spike', {
                'token_address': token_address,
                'volume_24h': volume_24h,
                'threshold': threshold,
            })
    
    async def check_risk_score_alert(self, token_address: str, risk_score: float):
        """Alert when risk score is too high."""
        if risk_score > 75:
            await self.trigger_alert('high_risk', {
                'token_address': token_address,
                'risk_score': risk_score,
                'recommendation': 'AVOID',
            })
    
    async def check_whale_deposit_alert(self, token_address: str, whale_buys: List[Dict]):
        """Alert when whales buy a token."""
        if whale_buys:
            total_whale_percentage = sum(w.get('percentage', 0) for w in whale_buys)
            if total_whale_percentage > 5:
                await self.trigger_alert('whale_activity', {
                    'token_address': token_address,
                    'whale_count': len(whale_buys),
                    'total_percentage': total_whale_percentage,
                    'whales': whale_buys,
                })
    
    def get_alert_history(self, limit: int = 50) -> List[Dict]:
        """Get recent alert history."""
        return self.alert_history[-limit:]


# Global alert manager instance
alert_manager = AlertManager()


def create_user_alert(user_id: str, token_address: str, alert_type: str, threshold: float):
    """Create a custom user alert."""
    create_alert(user_id, token_address, alert_type, threshold)


async def run_continuous_monitoring(token_analysis_func: Callable, interval: int = 60):
    """Run continuous monitoring loop."""
    while True:
        try:
            await token_analysis_func()
            await asyncio.sleep(interval)
        except Exception as e:
            print(f"Error in monitoring loop: {e}")
            await asyncio.sleep(interval)
