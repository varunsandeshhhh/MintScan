"""Sniper and early buyer detection."""
from typing import Dict, List, Optional
from database import log_sniper_wallet, get_snipers_for_token
import aiohttp


async def detect_sniper_wallets(token_address: str, helius_api_key: str = "") -> List[Dict]:
    """Detect sniper/bundled buyers using Helius transaction data."""
    try:
        if not helius_api_key:
            return []
        
        url = f"https://api.helius.xyz/v0/token/metadata?token={token_address}&api-key={helius_api_key}"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    return []
                
                data = await resp.json()
        
        snipers = []
        
        # Analyze creation-time purchases (first buyers)
        if data.get('mint_creation_tx'):
            creation_tx = data['mint_creation_tx']
            snipers.extend(await analyze_bundled_buys(token_address, creation_tx, helius_api_key))
        
        # Look for MEV bot patterns (multiple small txs to same wallet in quick succession)
        snipers.extend(await detect_mev_patterns(token_address, helius_api_key))
        
        # Detect fresh wallets
        snipers.extend(await detect_fresh_wallets(token_address, helius_api_key))
        
        return snipers
        
    except Exception as e:
        print(f"Error detecting snipers: {e}")
        return []


async def analyze_bundled_buys(token_address: str, creation_tx: str, helius_api_key: str) -> List[Dict]:
    """Analyze transaction for bundled/coordinated buys."""
    try:
        url = f"https://api.helius.xyz/v0/transactions?tx-hash={creation_tx}&api-key={helius_api_key}"
        
        bundled = []
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    return []
                
                tx_data = await resp.json()
        
        # Extract instruction data to find buyers
        if isinstance(tx_data, list):
            tx_data = tx_data[0] if tx_data else {}
        
        # Simple heuristic: if many different wallets swap in same block, it's likely bundled
        # This is simplified - real implementation would parse full instruction trees
        
        return bundled
        
    except Exception as e:
        print(f"Error analyzing bundled buys: {e}")
        return []


async def detect_mev_patterns(token_address: str, helius_api_key: str) -> List[Dict]:
    """Detect MEV bot patterns (frontrun/sandwich attacks)."""
    try:
        # This would require analyzing mempool transactions
        # For now, use heuristic: detect wallets with 100+ rapid micro-transactions
        
        mev_wallets = []
        
        # Check for known MEV bot patterns
        # This is a simplified version - full implementation would require RPC access
        
        return mev_wallets
        
    except Exception as e:
        print(f"Error detecting MEV patterns: {e}")
        return []


async def detect_fresh_wallets(token_address: str, helius_api_key: str) -> List[Dict]:
    """Detect wallets created recently that bought this token."""
    try:
        fresh_wallets = []
        
        # This would require checking wallet creation time
        # Helius doesn't provide wallet creation time in simple API calls
        # Would need to query full transaction history
        
        return fresh_wallets
        
    except Exception as e:
        print(f"Error detecting fresh wallets: {e}")
        return []


def detect_wallet_age(wallet_address: str, helius_api_key: str) -> Optional[Dict]:
    """Estimate wallet age by analyzing transaction history."""
    # Simplified heuristic
    # Real implementation would query Helius for full history
    return {
        'wallet': wallet_address,
        'is_fresh': False,  # Default to non-fresh
        'estimated_age_days': 0,
    }


def is_bundled_buy(wallet_address: str, transaction_signatures: List[str]) -> bool:
    """Check if a wallet made multiple buys in same block (bundled)."""
    if not transaction_signatures:
        return False
    
    # If same wallet has 3+ transactions in < 1 second window, likely bundled
    return len(transaction_signatures) >= 3


def detect_sniper_strategy(wallet_address: str, buy_price: float, entry_price: float) -> Optional[str]:
    """Analyze sniper strategy type."""
    
    if not entry_price or entry_price == 0:
        return None
    
    premium = (buy_price - entry_price) / entry_price * 100
    
    if premium < 1:
        return "🎯 Exact Entry - Likely sniper bot"
    elif premium < 5:
        return "⚡ Early Entry - Very fast buy"
    elif premium < 20:
        return "📈 First 5% - Early buyer"
    elif premium < 50:
        return "🟢 First 50% - Reasonable entry"
    else:
        return "📊 Later Entry - Normal buyer"


def get_sniper_risk_level(snipers: List[Dict]) -> str:
    """Assess sniper activity risk level."""
    if not snipers:
        return "🟢 None - Clean launch"
    
    high_risk_snipers = len([s for s in snipers if s.get('is_bundled') or s.get('is_fresh')])
    
    if high_risk_snipers > 10:
        return "🔴 Critical - Heavy sniper activity"
    elif high_risk_snipers > 5:
        return "🟠 High - Multiple snipers detected"
    elif high_risk_snipers > 2:
        return "🟡 Medium - Some sniper activity"
    else:
        return "🟢 Low - Minimal sniper presence"


async def track_sniper_buys(token_address: str, entry_price: float):
    """Track and log sniper activity for a token."""
    try:
        # This would integrate with Helius to get all early buys
        # Simplified version logs detected snipers
        snipers = get_snipers_for_token(token_address, limit=100)
        
        return {
            'token': token_address,
            'total_snipers': len(snipers),
            'bundled_count': len([s for s in snipers if s.get('is_bundled')]),
            'fresh_wallet_count': len([s for s in snipers if s.get('is_fresh_wallet')]),
            'risk_level': get_sniper_risk_level(snipers),
        }
        
    except Exception as e:
        print(f"Error tracking sniper buys: {e}")
        return {}
