"""Watchlist management and custom alerts."""
from typing import Dict, List, Optional
from database import add_watchlist, get_watchlist, remove_watchlist
import json


async def add_token_to_watchlist(user_id: str, token_address: str, alert_conditions: Dict = None) -> bool:
    """Add token to user's watchlist with optional alert conditions."""
    try:
        conditions_str = json.dumps(alert_conditions) if alert_conditions else ''
        return add_watchlist(user_id, token_address, conditions_str)
    except Exception as e:
        print(f"Error adding to watchlist: {e}")
        return False


async def remove_token_from_watchlist(user_id: str, token_address: str) -> bool:
    """Remove token from user's watchlist."""
    try:
        return remove_watchlist(user_id, token_address)
    except Exception as e:
        print(f"Error removing from watchlist: {e}")
        return False


def get_user_watchlist(user_id: str) -> List[Dict]:
    """Get all tokens in user's watchlist."""
    try:
        watches = get_watchlist(user_id)
        
        formatted = []
        for watch in watches:
            conditions = {}
            if watch.get('alert_conditions'):
                try:
                    conditions = json.loads(watch['alert_conditions'])
                except:
                    conditions = {}
            
            formatted.append({
                'address': watch['token_address'],
                'conditions': conditions,
                'added': watch['created_at'],
            })
        
        return formatted
        
    except Exception as e:
        print(f"Error getting watchlist: {e}")
        return []


def parse_alert_conditions(condition_string: str) -> Dict:
    """Parse alert condition from user input.
    
    Examples:
    - 'mc > 500k' -> {'metric': 'mc', 'operator': '>', 'value': 500000}
    - 'volume > 1m' -> {'metric': 'volume', 'operator': '>', 'value': 1000000}
    - 'holder_concentration > 70' -> {'metric': 'top_10', 'operator': '>', 'value': 70}
    """
    try:
        condition_string = condition_string.lower().strip()
        
        # Define known metrics
        metric_aliases = {
            'mc': 'market_cap',
            'market_cap': 'market_cap',
            'vol': 'volume_24h',
            'volume': 'volume_24h',
            'liq': 'liquidity',
            'liquidity': 'liquidity',
            'holders': 'holder_count',
            'concentration': 'top_10',
            'top_10': 'top_10',
            'whale': 'top_1',
            'top_1': 'top_1',
        }
        
        # Parse: \"metric operator value\"
        parts = condition_string.split()
        
        if len(parts) < 3:
            return None
        
        metric = metric_aliases.get(parts[0])
        operator = parts[1]
        value_str = parts[2]
        
        if not metric or operator not in ['>', '<', '==', '>=', '<=', '!=']:
            return None
        
        # Parse value with unit suffixes
        value = parse_value_with_unit(value_str)
        
        if value is None:
            return None
        
        return {
            'metric': metric,
            'operator': operator,
            'value': value,
        }
        
    except Exception as e:
        print(f"Error parsing alert condition: {e}")
        return None


def parse_value_with_unit(value_str: str) -> Optional[float]:
    """Parse value strings like '500k', '1.5m', '100' to numbers."""
    try:
        value_str = value_str.lower().strip()
        
        multipliers = {
            'k': 1_000,
            'm': 1_000_000,
            'b': 1_000_000_000,
            't': 1_000_000_000_000,
        }
        
        # Check for unit suffix
        if value_str[-1] in multipliers:
            unit = value_str[-1]
            number = float(value_str[:-1])
            return number * multipliers[unit]
        else:
            return float(value_str)
        
    except Exception as e:
        print(f"Error parsing value: {e}")
        return None


async def check_watchlist_alerts(token_address: str, token_data: Dict) -> List[Dict]:
    """Check if token triggers any user watchlist alerts."""
    try:
        from database import DB_PATH
        import sqlite3
        
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Get all watchers for this token
        cursor.execute('''
            SELECT user_id, alert_conditions FROM watchlists 
            WHERE token_address = ? AND is_active = 1
        ''', (token_address,))
        
        triggered_alerts = []
        
        for row in cursor.fetchall():
            user_id = row['user_id']
            conditions_str = row['alert_conditions']
            
            if not conditions_str:
                continue
            
            try:
                conditions = json.loads(conditions_str)
            except:
                continue
            
            # Check each condition
            if check_condition(conditions, token_data):
                triggered_alerts.append({
                    'user_id': user_id,
                    'token': token_address,
                    'condition': conditions,
                    'trigger_data': token_data,
                })
        
        conn.close()
        return triggered_alerts
        
    except Exception as e:
        print(f"Error checking watchlist alerts: {e}")
        return []


def check_condition(condition: Dict, token_data: Dict) -> bool:
    """Check if token data satisfies a condition."""
    try:
        metric = condition.get('metric')
        operator = condition.get('operator')
        threshold = condition.get('value')
        
        # Get metric value from token data
        metric_value = None
        
        if metric == 'market_cap':
            metric_value = token_data.get('market_cap', 0)
        elif metric == 'volume_24h':
            metric_value = token_data.get('volume_24h', 0)
        elif metric == 'liquidity':
            metric_value = token_data.get('liquidity', 0)
        elif metric == 'holder_count':
            metric_value = token_data.get('holder_count', 0)
        elif metric in ('top_1', 'top_10'):
            # These require holder data, not in token_data
            return False
        
        if metric_value is None:
            return False
        
        # Compare using operator
        if operator == '>':
            return metric_value > threshold
        elif operator == '<':
            return metric_value < threshold
        elif operator == '==':
            return metric_value == threshold
        elif operator == '>=':
            return metric_value >= threshold
        elif operator == '<=':
            return metric_value <= threshold
        elif operator == '!=':
            return metric_value != threshold
        
        return False
        
    except Exception as e:
        print(f"Error checking condition: {e}")
        return False


def format_condition_readable(condition: Dict) -> str:
    """Format condition dict back to readable string."""
    try:
        metric = condition.get('metric', 'unknown')
        operator = condition.get('operator', '?')
        value = condition.get('value', 0)
        
        # Format value
        if value >= 1_000_000:
            value_str = f"{value / 1_000_000:.1f}M"
        elif value >= 1_000:
            value_str = f"{value / 1_000:.1f}K"
        else:
            value_str = str(value)
        
        return f"{metric} {operator} {value_str}"
        
    except Exception as e:
        print(f"Error formatting condition: {e}")
        return "Invalid condition"
