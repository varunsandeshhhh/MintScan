from typing import Dict, List, Optional
from birdeye import get_wallet_portfolio, get_wallet_tokens
from database import track_developer_wallet
import asyncio


KNOWN_SMART_MONEY_WALLETS = {
    "9B5X6wrjCiVM8j1waxL8YLsuEZthMxFjNQqEjXjxDqM": "Raydium Insider",
    "5Q544fRrGkZAEoXT33zqwU6G1yLqKCVoRg6STiGsc7w": "Pump Fun Creator",
}


async def analyze_smart_wallet(wallet_address: str) -> Optional[Dict]:
    """Analyze a wallet for smart money characteristics."""
    try:
        portfolio = await get_wallet_portfolio(wallet_address)
        tokens = await get_wallet_tokens(wallet_address)
        
        if not portfolio or not tokens:
            return None
        
        total_value = portfolio.get('totalUsd', 0)
        
        # Calculate profit statistics
        profitable_tokens = [t for t in tokens if t.get('valueUsd', 0) > 0]
        loss_tokens = [t for t in tokens if t.get('valueUsd', 0) < 0]
        
        profit_count = len(profitable_tokens)
        loss_count = len(loss_tokens)
        total_trades = profit_count + loss_count
        
        win_rate = (profit_count / total_trades * 100) if total_trades > 0 else 0
        
        # Calculate average ROI
        roi_values = []
        for token in tokens:
            cost_basis = token.get('cost_basis', 0)
            current_value = token.get('valueUsd', 0)
            if cost_basis > 0:
                roi = ((current_value - cost_basis) / cost_basis) * 100
                roi_values.append(roi)
        
        avg_roi = sum(roi_values) / len(roi_values) if roi_values else 0
        
        smart_wallet_data = {
            'wallet_address': wallet_address,
            'total_value': total_value,
            'profit_count': profit_count,
            'loss_count': loss_count,
            'win_rate': win_rate,
            'avg_roi': avg_roi,
            'total_trades': total_trades,
            'score': calculate_smart_money_score(win_rate, avg_roi, total_value),
        }
        
        return smart_wallet_data
        
    except Exception as e:
        print(f"Error analyzing smart wallet: {e}")
        return None


def calculate_smart_money_score(win_rate: float, avg_roi: float, total_value: float) -> float:
    """Calculate a smart money score (0-100)."""
    score = 0
    
    # Win rate component (0-50)
    if win_rate >= 80:
        score += 50
    elif win_rate >= 60:
        score += 40
    elif win_rate >= 40:
        score += 25
    
    # ROI component (0-30)
    if avg_roi > 100:
        score += 30
    elif avg_roi > 50:
        score += 20
    elif avg_roi > 0:
        score += 10
    
    # Portfolio size component (0-20)
    if total_value > 1_000_000:
        score += 20
    elif total_value > 100_000:
        score += 15
    elif total_value > 10_000:
        score += 10
    
    return min(score, 100)


async def detect_smart_money_buys(token_address: str, smart_wallets: List[str]) -> List[Dict]:
    """Detect if smart money wallets are buying a token."""
    smart_buys = []
    
    for wallet in smart_wallets:
        try:
            portfolio_data = await get_wallet_portfolio(wallet)
            tokens = await get_wallet_tokens(wallet)
            
            if not tokens:
                continue
            
            # Check if wallet holds this token
            matching_tokens = [t for t in tokens if t.get('address', '') == token_address]
            
            if matching_tokens:
                token_data = matching_tokens[0]
                smart_buys.append({
                    'wallet': wallet,
                    'amount': token_data.get('amount', 0),
                    'value': token_data.get('valueUsd', 0),
                    'cost_basis': token_data.get('cost_basis', 0),
                    'roi': ((token_data.get('valueUsd', 0) - token_data.get('cost_basis', 0)) / token_data.get('cost_basis', 1)) * 100 if token_data.get('cost_basis', 0) > 0 else 0,
                })
        except Exception as e:
            print(f"Error checking wallet {wallet}: {e}")
            continue
    
    return smart_buys


async def track_top_wallets(token_address: str, holders: List[Dict], top_n: int = 20) -> List[Dict]:
    """Track top holders and their wallet scores."""
    top_wallets_analysis = []
    
    top_holders = sorted(holders, key=lambda x: x.get('percentage', 0), reverse=True)[:top_n]
    
    for holder in top_holders:
        try:
            wallet_address = holder.get('address', '')
            wallet_analysis = await analyze_smart_wallet(wallet_address)
            
            if wallet_analysis:
                top_wallets_analysis.append({
                    'wallet': wallet_address,
                    'percentage_of_token': holder.get('percentage', 0),
                    'smart_money_score': wallet_analysis.get('score', 0),
                    'win_rate': wallet_analysis.get('win_rate', 0),
                    'avg_roi': wallet_analysis.get('avg_roi', 0),
                })
        except Exception as e:
            print(f"Error analyzing holder {holder.get('address')}: {e}")
            continue
    
    return top_wallets_analysis
