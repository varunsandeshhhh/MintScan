from typing import Dict, List, Optional
from birdeye import get_token_holders
from database import add_holder, get_top_holders


async def analyze_token_holders(token_address: str, limit: int = 50) -> Optional[Dict]:
    """Analyze token holder distribution and detect risks."""
    try:
        holders = await get_token_holders(token_address, limit)
        if not holders:
            return None
        
        # Store in database
        for holder in holders:
            add_holder(
                token_address=token_address,
                holder_address=holder.get('address', ''),
                percentage=holder.get('percentage', 0),
                count=holder.get('amount', 0)
            )
        
        # Calculate concentration metrics
        top_10_percentage = sum(h.get('percentage', 0) for h in holders[:10])
        top_5_percentage = sum(h.get('percentage', 0) for h in holders[:5])
        top_1_percentage = holders[0].get('percentage', 0) if holders else 0
        
        # Detect distribution type
        is_concentrated = top_10_percentage > 50
        is_very_concentrated = top_5_percentage > 40
        
        # Risk levels
        concentration_risk = 'HIGH' if top_10_percentage > 60 else 'MEDIUM' if top_10_percentage > 40 else 'LOW'
        
        analysis = {
            'total_holders_tracked': len(holders),
            'top_10_percentage': top_10_percentage,
            'top_5_percentage': top_5_percentage,
            'top_1_percentage': top_1_percentage,
            'concentration_risk': concentration_risk,
            'is_concentrated': is_concentrated,
            'is_very_concentrated': is_very_concentrated,
            'holders': holders,
        }
        
        return analysis
        
    except Exception as e:
        print(f"Error analyzing token holders: {e}")
        return None


def calculate_holder_risk_score(holder_analysis: Dict) -> int:
    """Calculate holder concentration risk score (0-100)."""
    if not holder_analysis:
        return 50
    
    top_10 = holder_analysis.get('top_10_percentage', 0)
    risk_score = 0
    
    if top_10 > 70:
        risk_score = 90
    elif top_10 > 60:
        risk_score = 75
    elif top_10 > 50:
        risk_score = 60
    elif top_10 > 40:
        risk_score = 45
    elif top_10 > 30:
        risk_score = 30
    else:
        risk_score = 10
    
    return risk_score


async def detect_whale_activity(token_address: str, threshold_percentage: float = 5.0) -> Optional[List[Dict]]:
    """Detect large whale holders that pose dump risk."""
    try:
        holders = await get_token_holders(token_address, limit=100)
        if not holders:
            return None
        
        whales = [h for h in holders if h.get('percentage', 0) >= threshold_percentage]
        
        return whales
        
    except Exception as e:
        print(f"Error detecting whale activity: {e}")
        return None


async def check_dev_holding_percentage(token_address: str, dev_wallets: List[str]) -> Dict:
    """Check how much developers hold of the token."""
    try:
        holders = await get_token_holders(token_address, limit=100)
        if not holders:
            return {}
        
        dev_holdings = {}
        for dev_wallet in dev_wallets:
            matching_holders = [h for h in holders if h.get('address', '').lower() == dev_wallet.lower()]
            if matching_holders:
                dev_holdings[dev_wallet] = {
                    'percentage': matching_holders[0].get('percentage', 0),
                    'amount': matching_holders[0].get('amount', 0),
                }
        
        total_dev_percentage = sum(h['percentage'] for h in dev_holdings.values())
        
        return {
            'dev_holdings': dev_holdings,
            'total_dev_percentage': total_dev_percentage,
            'risk_level': 'HIGH' if total_dev_percentage > 50 else 'MEDIUM' if total_dev_percentage > 25 else 'LOW'
        }
        
    except Exception as e:
        print(f"Error checking dev holdings: {e}")
        return {}
