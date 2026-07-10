"""Fallback holder analysis when Birdeye is unavailable."""
from typing import Dict, Optional, List
from rugcheck import fetch_risk_data


async def analyze_holders_from_rugcheck(token_address: str) -> Optional[Dict]:
    """Analyze holders using RugCheck data (fallback without Birdeye)."""
    try:
        risk_data = await fetch_risk_data(token_address)
        if not risk_data:
            return None
        
        # Extract holder-related risks from RugCheck
        risks = risk_data.get('risks', [])
        
        # Look for holder concentration risks in the risks array
        holder_concentration_risk = False
        for risk in risks:
            description = (risk.get('description') or '').lower()
            if any(keyword in description for keyword in ['holder', 'concentration', 'distribution', 'supply']):
                holder_concentration_risk = True
                break
        
        # Estimate concentration based on risk level
        concentration_risk = 'HIGH' if risk_data.get('risk_score', 50) > 70 else \
                           'MEDIUM' if risk_data.get('risk_score', 50) > 40 else 'LOW'
        
        analysis = {
            'total_holders_tracked': 0,  # RugCheck doesn't provide exact count
            'top_10_percentage': 0,
            'top_5_percentage': 0,
            'top_1_percentage': 0,
            'concentration_risk': concentration_risk,
            'is_concentrated': concentration_risk in ('HIGH', 'MEDIUM'),
            'is_very_concentrated': concentration_risk == 'HIGH',
            'holders': [],
            'source': 'rugcheck_heuristic',
        }
        
        # Try to infer concentration from risks
        if holder_concentration_risk or concentration_risk != 'LOW':
            # If risks indicate concentration issues
            analysis['top_10_percentage'] = 65 if concentration_risk == 'HIGH' else 45
            analysis['top_5_percentage'] = 50 if concentration_risk == 'HIGH' else 30
            analysis['top_1_percentage'] = 35 if concentration_risk == 'HIGH' else 15
        else:
            # Assume better distribution if no concentration risks
            analysis['top_10_percentage'] = 25
            analysis['top_5_percentage'] = 15
            analysis['top_1_percentage'] = 5
        
        return analysis
        
    except Exception as e:
        print(f"Error analyzing holders from RugCheck: {e}")
        return None


async def estimate_holder_distribution(token_data: Dict) -> Optional[Dict]:
    """Estimate holder distribution using market data heuristics."""
    try:
        market_cap = token_data.get('market_cap', 0)
        liquidity = token_data.get('liquidity', 0)
        volume_24h = token_data.get('volume_24h', 0)
        holder_count = token_data.get('holder_count') or 1
        
        # Heuristic-based estimation
        analysis = {
            'total_holders_tracked': holder_count or 100,  # Best guess
            'top_10_percentage': 0,
            'top_5_percentage': 0,
            'top_1_percentage': 0,
            'concentration_risk': 'MEDIUM',
            'is_concentrated': True,
            'is_very_concentrated': False,
            'holders': [],
            'source': 'market_heuristic',
        }
        
        # If liquidity is high relative to market cap, distribution is likely better
        if market_cap and liquidity:
            liq_ratio = liquidity / market_cap
            if liq_ratio > 0.2:
                # Good liquidity suggests broad distribution
                analysis['top_10_percentage'] = 30
                analysis['top_5_percentage'] = 18
                analysis['top_1_percentage'] = 8
                analysis['concentration_risk'] = 'LOW'
                analysis['is_concentrated'] = False
            elif liq_ratio > 0.05:
                # Moderate liquidity
                analysis['top_10_percentage'] = 45
                analysis['top_5_percentage'] = 28
                analysis['top_1_percentage'] = 15
                analysis['concentration_risk'] = 'MEDIUM'
            else:
                # Low liquidity suggests concentrated ownership
                analysis['top_10_percentage'] = 65
                analysis['top_5_percentage'] = 45
                analysis['top_1_percentage'] = 30
                analysis['concentration_risk'] = 'HIGH'
                analysis['is_very_concentrated'] = True
        
        # If volume is high, suggests active trading and broader distribution
        if volume_24h and market_cap:
            vol_ratio = volume_24h / market_cap
            if vol_ratio > 0.5:
                # High volume suggests activity and distribution
                analysis['concentration_risk'] = max('LOW', analysis['concentration_risk']) if analysis['concentration_risk'] != 'HIGH' else analysis['concentration_risk']
        
        return analysis
        
    except Exception as e:
        print(f"Error estimating holder distribution: {e}")
        return None


async def get_fallback_holder_analysis(token_address: str, token_data: Dict) -> Optional[Dict]:
    """Get holder analysis using fallback methods when Birdeye is unavailable."""
    # Try RugCheck first
    rugcheck_analysis = await analyze_holders_from_rugcheck(token_address)
    if rugcheck_analysis:
        return rugcheck_analysis
    
    # Fall back to market heuristics
    heuristic_analysis = await estimate_holder_distribution(token_data)
    if heuristic_analysis:
        return heuristic_analysis
    
    # Last resort: very conservative estimate
    return {
        'total_holders_tracked': 100,
        'top_10_percentage': 50,
        'top_5_percentage': 35,
        'top_1_percentage': 20,
        'concentration_risk': 'MEDIUM',
        'is_concentrated': True,
        'is_very_concentrated': False,
        'holders': [],
        'source': 'fallback_conservative',
    }


def estimate_insider_supply(security_data: Optional[Dict], holder_risk: Optional[Dict]) -> Dict:
    """Estimate insider/bundled supply based on security flags."""
    if not security_data:
        return {'insider_percentage': 0, 'bundled_percentage': 0, 'risk_level': 'Unknown'}
    
    insider_pct = 0
    bundled_pct = 0
    
    # Check for dev/insider holdings
    top_holders = security_data.get('suspicious_wallets', [])
    if top_holders:
        for holder in top_holders[:3]:
            insider_pct += holder.get('percentage', 0) * 0.5  # Estimate half could be insider
    
    # Check for locked supply indicators
    if security_data.get('lp_locked'):
        bundled_pct += 10
    
    if not security_data.get('mint_authority_disabled'):
        bundled_pct += 15  # Minting risk adds to bundled supply estimate
    
    if insider_pct > 40:
        risk_level = 'HIGH'
    elif insider_pct > 20:
        risk_level = 'MEDIUM'
    else:
        risk_level = 'LOW'
    
    return {
        'insider_percentage': min(insider_pct, 100),
        'bundled_percentage': min(bundled_pct, 100),
        'risk_level': risk_level,
    }


def estimate_burn_and_locked(security_data: Optional[Dict]) -> Dict:
    """Estimate burn percentage and locked supply."""
    burn_pct = 0
    locked_pct = 0
    
    if security_data:
        if security_data.get('lp_locked'):
            locked_pct = 15  # Conservative estimate
        
        if security_data.get('owner_renounced'):
            burn_pct = 5  # Proxy for security
    
    return {
        'burn_percentage': burn_pct,
        'locked_percentage': locked_pct,
        'total_unavailable': burn_pct + locked_pct,
    }
