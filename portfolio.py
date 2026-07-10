"""Portfolio tracking and PnL calculation."""
from typing import Dict, List, Optional
from database import add_portfolio_wallet, get_portfolio_wallets, remove_portfolio_wallet
import aiohttp
from birdeye import BirdeyeAPIError, get_wallet_portfolio, get_wallet_tokens


async def link_wallet(user_id: str, wallet_address: str, wallet_label: str = None) -> bool:
    """Link a wallet to user's portfolio."""
    try:
        return add_portfolio_wallet(user_id, wallet_address, wallet_label)
    except Exception as e:
        print(f"Error linking wallet: {e}")
        return False


async def unlink_wallet(user_id: str, wallet_address: str) -> bool:
    """Remove a wallet from user's portfolio."""
    try:
        return remove_portfolio_wallet(user_id, wallet_address)
    except Exception as e:
        print(f"Error unlinking wallet: {e}")
        return False


async def fetch_wallet_portfolio(wallet_address: str, birdeye_api_key: str = None) -> Optional[Dict]:
    """Fetch portfolio data for a wallet."""
    try:
        api_key = birdeye_api_key.strip() if birdeye_api_key else ''
        if not api_key or api_key.startswith('your_'):
            return None

        holdings = await get_wallet_tokens(wallet_address, api_key=api_key)
        if holdings:
            return _parse_holdings(wallet_address, holdings)

        portfolio_data = await get_wallet_portfolio(wallet_address, api_key=api_key)
        if portfolio_data and portfolio_data.get('tokens'):
            return _parse_holdings_from_portfolio(wallet_address, portfolio_data)

        return None
    except BirdeyeAPIError as e:
        print(f"Birdeye API error: {e}")
        return {'error': str(e)}
    except Exception as e:
        print(f"Error fetching portfolio: {e}")
        return {'error': 'Unexpected error fetching portfolio'}


async def calculate_portfolio_pnl(wallet_address: str, holdings: List[Dict]) -> Dict:
    """Calculate PnL for a wallet."""
    try:
        from database import get_call_history
        
        # Get entry prices from call history
        calls = get_call_history(limit=1000)
        call_map = {call['token_address']: call for call in calls}
        
        realized_pnl = 0
        unrealized_pnl = 0
        biggest_winner = None
        biggest_loser = None
        
        for holding in holdings:
            token = holding['token']
            current_value = holding['value']
            
            if token in call_map:
                call = call_map[token]
                entry_price = call.get('entry_price', call.get('initial_price', 0))
                
                if entry_price and entry_price > 0:
                    amount = holding['amount']
                    entry_value = amount * entry_price
                    pnl = current_value - entry_value
                    
                    unrealized_pnl += pnl
                    
                    # Track extremes
                    if biggest_winner is None or pnl > biggest_winner['pnl']:
                        biggest_winner = {
                            'token': holding['symbol'],
                            'address': token,
                            'pnl': pnl,
                            'roi': (pnl / entry_value * 100) if entry_value > 0 else 0,
                        }
                    
                    if biggest_loser is None or pnl < biggest_loser['pnl']:
                        biggest_loser = {
                            'token': holding['symbol'],
                            'address': token,
                            'pnl': pnl,
                            'roi': (pnl / entry_value * 100) if entry_value > 0 else 0,
                        }
        
        return {
            'wallet': wallet_address,
            'total_value': sum(h['value'] for h in holdings),
            'unrealized_pnl': unrealized_pnl,
            'realized_pnl': realized_pnl,
            'total_pnl': unrealized_pnl + realized_pnl,
            'biggest_winner': biggest_winner,
            'biggest_loser': biggest_loser,
            'holdings_count': len(holdings),
        }
    except Exception as e:
        print(f"Error calculating PnL: {e}")
        return {}


def _parse_holdings(wallet_address: str, tokens: List[Dict]) -> Dict:
    total_value = 0
    holdings = []

    for token in tokens:
        value = token.get('valueUsd', token.get('value', 0)) or 0
        total_value += value

        holdings.append({
            'token': token.get('tokenAddress') or token.get('token') or token.get('address'),
            'symbol': token.get('symbol', 'N/A'),
            'value': value,
            'amount': token.get('amount', 0),
        })

    return {
        'wallet': wallet_address,
        'total_value': total_value,
        'holdings_count': len(holdings),
        'holdings': sorted(holdings, key=lambda x: x['value'], reverse=True),
    }


def _parse_holdings_from_portfolio(wallet_address: str, portfolio: Dict) -> Dict:
    tokens = portfolio.get('tokens') or []
    total_value = portfolio.get('totalUsd', 0) or 0
    holdings = []

    for token in tokens:
        value = token.get('valueUsd', token.get('value', 0)) or 0
        holdings.append({
            'token': token.get('tokenAddress') or token.get('token') or token.get('address'),
            'symbol': token.get('symbol', 'N/A'),
            'value': value,
            'amount': token.get('amount', 0),
        })

    return {
        'wallet': wallet_address,
        'total_value': total_value,
        'holdings_count': len(holdings),
        'holdings': sorted(holdings, key=lambda x: x['value'], reverse=True),
    }


def get_user_portfolio_summary(user_id: str) -> Dict:
    """Get summary of all user's linked wallets."""
    try:
        wallets = get_portfolio_wallets(user_id)
        
        total_value = 0
        wallet_list = []
        
        for wallet in wallets:
            wallet_list.append({
                'address': wallet['wallet_address'],
                'label': wallet['wallet_label'] or wallet['wallet_address'][:8],
                'tracked_since': wallet['tracked_since'],
            })
        
        return {
            'user_id': user_id,
            'wallet_count': len(wallet_list),
            'wallets': wallet_list,
            'total_value': total_value,
        }
        
    except Exception as e:
        print(f"Error getting portfolio summary: {e}")
        return {}


async def get_wallet_top_movers(wallet_address: str, holdings: List[Dict], top_n: int = 5) -> Dict:
    """Get top gainers and losers in portfolio."""
    try:
        from database import get_call_history
        
        calls = get_call_history(limit=1000)
        call_map = {call['token_address']: call for call in calls}
        
        movers = []
        
        for holding in holdings:
            token = holding['token']
            
            if token in call_map:
                call = call_map[token]
                entry = call.get('entry_price', call.get('initial_price', 0))
                current = holding['value']
                
                if entry > 0:
                    roi = ((current - entry) / entry * 100)
                    movers.append({
                        'symbol': holding['symbol'],
                        'address': token,
                        'current_value': current,
                        'roi': roi,
                        'amount': holding['amount'],
                    })
        
        movers = sorted(movers, key=lambda x: x['roi'], reverse=True)
        
        return {
            'gainers': movers[:top_n],
            'losers': movers[-top_n:][::-1],
        }
        
    except Exception as e:
        print(f"Error getting top movers: {e}")
        return {'gainers': [], 'losers': []}
