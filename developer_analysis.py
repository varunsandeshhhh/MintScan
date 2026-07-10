from typing import Dict, Optional, List
from birdeye import get_wallet_tokens, get_wallet_portfolio
from database import track_developer_wallet
import asyncio


async def analyze_developer_wallet(wallet_address: str) -> Optional[Dict]:
    """Analyze a developer/creator wallet for their token portfolio and history."""
    try:
        # Get wallet portfolio
        portfolio = await get_wallet_portfolio(wallet_address)
        if not portfolio:
            return None
        
        # Get tokens held
        tokens = await get_wallet_tokens(wallet_address)
        if not tokens:
            return None
        
        total_value = portfolio.get('totalUsd', 0)
        token_count = len(tokens)
        
        # Calculate win rate (tokens that gained value)
        winners = sum(1 for t in tokens if t.get('valueUsd', 0) > 0)
        win_rate = (winners / token_count * 100) if token_count > 0 else 0
        
        # Calculate average ROI
        roi_values = []
        for token in tokens:
            if token.get('cost_basis', 0) > 0:
                roi = ((token.get('valueUsd', 0) - token.get('cost_basis', 0)) / token.get('cost_basis', 0)) * 100
                roi_values.append(roi)
        
        avg_roi = sum(roi_values) / len(roi_values) if roi_values else 0
        
        dev_wallet_data = {
            'wallet_address': wallet_address,
            'token_count': token_count,
            'total_value': total_value,
            'win_rate': win_rate,
            'avg_roi': avg_roi,
            'portfolio': portfolio,
            'tokens': tokens[:10],  # Top 10 tokens
        }
        
        # Store in database
        track_developer_wallet(
            wallet_address=wallet_address,
            wallet_name=f"Dev Wallet",
            token_count=token_count,
            total_value=total_value
        )
        
        return dev_wallet_data
        
    except Exception as e:
        print(f"Error analyzing developer wallet: {e}")
        return None


async def detect_dev_movements(wallet_address: str, token_address: str) -> Dict:
    """Detect if a developer wallet is buying/selling a token."""
    try:
        tokens = await get_wallet_tokens(wallet_address)
        if not tokens:
            return {'detected': False}
        
        # Check if dev holds this token
        dev_holds = any(t['address'] == token_address for t in tokens)
        
        if dev_holds:
            token_data = next(t for t in tokens if t['address'] == token_address)
            return {
                'detected': True,
                'holds_token': True,
                'holdings': token_data.get('amount', 0),
                'value': token_data.get('valueUsd', 0),
                'percentage_of_portfolio': (token_data.get('valueUsd', 0) / sum(t.get('valueUsd', 0) for t in tokens)) * 100 if tokens else 0
            }
        
        return {'detected': False, 'holds_token': False}
        
    except Exception as e:
        print(f"Error detecting dev movements: {e}")
        return {'detected': False, 'error': str(e)}


async def get_dev_wallet_history(wallet_address: str) -> Optional[List[Dict]]:
    """Get trading history of a developer wallet."""
    try:
        tokens = await get_wallet_tokens(wallet_address)
        if not tokens:
            return None
        
        # Sort by recent activity
        history = sorted(
            tokens,
            key=lambda x: x.get('lastTradeTime', 0),
            reverse=True
        )[:20]
        
        return history
        
    except Exception as e:
        print(f"Error fetching dev wallet history: {e}")
        return None
