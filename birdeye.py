import aiohttp
import json
from typing import Dict, Optional, List
from config import settings


BIRDEYE_API_KEY = settings.get('BIRDEYE_API_KEY', '')
BIRDEYE_API = "https://public-api.birdeye.so/v1"


class BirdeyeAPIError(Exception):
    """Raised when Birdeye returns an error response or message."""
    pass


def _normalize_api_key(api_key: str = None) -> Optional[str]:
    api_key = api_key or BIRDEYE_API_KEY
    if not api_key:
        return None
    api_key = api_key.strip()
    if api_key.startswith('your_'):
        return None
    return api_key


async def _birdeye_get(url: str, api_key: str) -> Dict:
    api_key = _normalize_api_key(api_key)
    if not api_key:
        raise BirdeyeAPIError('Missing or invalid Birdeye API key')

    headers = {"X-API-KEY": api_key}

    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as response:
            text = await response.text()
            if response.status != 200:
                try:
                    data = json.loads(text)
                    message = data.get('message') or text
                except Exception:
                    message = text
                raise BirdeyeAPIError(f"{response.status} {message}")

            data = await response.json()
            if not data.get('success'):
                raise BirdeyeAPIError(data.get('message') or 'Birdeye request failed')

            return data.get('data', {})


async def get_token_overview(address: str, api_key: str = None) -> Optional[Dict]:
    """Get token overview from Birdeye."""
    try:
        url = f"{BIRDEYE_API}/defi/token_overview?address={address}"
        return await _birdeye_get(url, api_key)
    except BirdeyeAPIError as e:
        print(f"Error fetching token overview from Birdeye: {e}")
        return None



async def get_token_holders(address: str, limit: int = 50, api_key: str = None) -> Optional[List[Dict]]:
    """Get token holder distribution."""
    try:
        url = f"{BIRDEYE_API}/defi/token_holders?address={address}&limit={limit}"
        data = await _birdeye_get(url, api_key)
        return data.get('holders', []) if isinstance(data, dict) else []
    except BirdeyeAPIError as e:
        print(f"Error fetching token holders from Birdeye: {e}")
        return None



async def get_token_trades(address: str, limit: int = 100, sort_type: str = "raydium", api_key: str = None) -> Optional[List[Dict]]:
    """Get recent trades for a token."""
    try:
        url = f"{BIRDEYE_API}/defi/txs/token?address={address}&limit={limit}&sort_type={sort_type}"
        data = await _birdeye_get(url, api_key)
        return data.get('items', []) if isinstance(data, dict) else []
    except BirdeyeAPIError as e:
        print(f"Error fetching token trades from Birdeye: {e}")
        return None



async def get_wallet_portfolio(address: str, api_key: str = None) -> Optional[Dict]:
    """Get wallet portfolio data."""
    url = f"{BIRDEYE_API}/wallet/portfolio?wallet={address}"
    return await _birdeye_get(url, api_key)



async def get_wallet_tokens(address: str, api_key: str = None) -> Optional[List[Dict]]:
    """Get tokens held by a wallet."""
    data = await _birdeye_get(f"{BIRDEYE_API}/wallet/token_list?wallet={address}", api_key)
    return data.get('items', []) if isinstance(data, dict) else []
