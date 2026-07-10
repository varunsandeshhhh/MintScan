import aiohttp
from typing import Dict, Optional, List
from config import settings


def get_helius_api_key() -> str:
    """Return the configured Helius API key from the current settings."""
    return str(settings.get('HELIUS_API_KEY', '') or '').strip()


def get_helius_rpc_url() -> str:
    """Build the Helius RPC URL for the current API key."""
    api_key = get_helius_api_key()
    return f"https://mainnet.helius-rpc.com/?api-key={api_key}" if api_key else ""


async def get_token_metadata(address: str) -> Optional[Dict]:
    """Fetch token metadata from Helius."""
    api_key = get_helius_api_key()
    if not api_key:
        return None
    
    try:
        async with aiohttp.ClientSession() as session:
            payload = {
                "jsonrpc": "2.0",
                "id": "text",
                "method": "getAsset",
                "params": {"id": address}
            }
            
            async with session.post(get_helius_rpc_url(), json=payload, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status == 200:
                    data = await response.json()
                    if 'result' in data:
                        return data['result']
        return None
    except Exception as e:
        print(f"Error fetching metadata from Helius: {e}")
        return None


async def get_token_transactions(address: str, limit: int = 10) -> Optional[List[Dict]]:
    """Fetch recent transactions for a token."""
    api_key = get_helius_api_key()
    if not api_key:
        return None
    
    try:
        async with aiohttp.ClientSession() as session:
            payload = {
                "jsonrpc": "2.0",
                "id": "text",
                "method": "getSignaturesForAddress",
                "params": {
                    "address": address,
                    "limit": limit
                }
            }
            
            async with session.post(get_helius_rpc_url(), json=payload, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status == 200:
                    data = await response.json()
                    if 'result' in data:
                        return data['result']
        return None
    except Exception as e:
        print(f"Error fetching transactions from Helius: {e}")
        return None


async def get_parsed_transactions(signatures: List[str]) -> Optional[List[Dict]]:
    """Get parsed transaction details."""
    api_key = get_helius_api_key()
    if not api_key or not signatures:
        return None
    
    try:
        url = f"https://api.helius.xyz/v0/parsed-transactions?api-key={api_key}"
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                json=signatures,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                if response.status == 200:
                    return await response.json()
        return None
    except Exception as e:
        print(f"Error fetching parsed transactions: {e}")
        return None
