import aiohttp
from typing import Dict, Optional


async def fetch_risk_data(address: str) -> Optional[Dict]:
    """Fetch risk data from RugCheck API."""
    url = f"https://api.rugcheck.xyz/v1/tokens/{address}/report"
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    # Calculate overall risk score (0-100)
                    risks = data.get('risks', [])
                    risk_level = 'SAFE'
                    risk_score = 0
                    
                    if risks:
                        high_risk_count = sum(1 for r in risks if r.get('level') == 3)
                        medium_risk_count = sum(1 for r in risks if r.get('level') == 2)
                        low_risk_count = sum(1 for r in risks if r.get('level') == 1)
                        
                        risk_score = (high_risk_count * 30) + (medium_risk_count * 15) + (low_risk_count * 5)
                        risk_score = min(risk_score, 100)
                        
                        if high_risk_count > 0:
                            risk_level = '🔴 HIGH RISK'
                        elif medium_risk_count > 0:
                            risk_level = '🟠 MEDIUM RISK'
                        elif low_risk_count > 0:
                            risk_level = '🟡 LOW RISK'
                        else:
                            risk_level = '🟢 SAFE'
                    
                    return {
                        'risk_score': risk_score,
                        'risk_level': risk_level,
                        'risks': risks,
                        'is_open_source': data.get('isOpenSource', False),
                        'owner_is_renounced': data.get('ownerIsRenounced', False),
                    }
        return None
    except Exception as e:
        print(f"Error fetching RugCheck data: {e}")
        return None
