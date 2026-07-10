import aiohttp
from typing import Dict, Optional


async def fetch_token_data(address: str) -> Optional[Dict]:
    """Fetch token data from DexScreener API, tolerating missing or changed payload shapes."""
    urls = [
        f"https://api.dexscreener.com/latest/dex/tokens/{address}",
        f"https://api.dexscreener.com/token-profiles/recent-updates/v1",
    ]

    try:
        async with aiohttp.ClientSession() as session:
            for url in urls:
                try:
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                        if response.status != 200:
                            continue

                        data = await response.json()
                        if not isinstance(data, dict):
                            continue

                        pairs = data.get('pairs') if isinstance(data.get('pairs'), list) else None
                        if pairs and len(pairs) > 0:
                            pair = pairs[0] if isinstance(pairs[0], dict) else {}
                            base = pair.get('baseToken', {}) or {}
                            if not isinstance(base, dict):
                                base = {}

                            liquidity_data = pair.get('liquidity') or {}
                            if not isinstance(liquidity_data, dict):
                                liquidity_data = {}
                            volume_data = pair.get('volume') or {}
                            if not isinstance(volume_data, dict):
                                volume_data = {}
                            price_change_data = pair.get('priceChange') or {}
                            if not isinstance(price_change_data, dict):
                                price_change_data = {}

                            price_change_1m = price_change_data.get('m1')
                            if price_change_1m is None:
                                price_change_1m = price_change_data.get('1m')
                            price_change_5m = price_change_data.get('m5')
                            if price_change_5m is None:
                                price_change_5m = price_change_data.get('5m')
                            price_change_1h = price_change_data.get('h1')
                            if price_change_1h is None:
                                price_change_1h = price_change_data.get('1h')
                            price_change_24h = price_change_data.get('h24')
                            if price_change_24h is None:
                                price_change_24h = price_change_data.get('24h')

                            market_cap = pair.get('marketCap')
                            if market_cap is None:
                                market_cap = pair.get('market_cap')
                            if market_cap is None:
                                market_cap = pair.get('fdv')

                            liquidity = liquidity_data.get('usd')
                            if liquidity is None:
                                liquidity = pair.get('liquidityUsd') or pair.get('liquidity_usd') or pair.get('liquidity')

                            volume_24h = volume_data.get('h24')
                            if volume_24h is None:
                                volume_24h = pair.get('volumeUsd24h') or pair.get('volume_24h')

                            price = pair.get('priceUsd')
                            if price is None:
                                price = pair.get('price')

                            fdv = pair.get('fdv')
                            if fdv is None:
                                fdv = pair.get('fullyDilutedValuation')

                            result = {
                                'address': address,
                                'name': base.get('name', 'Unknown'),
                                'symbol': base.get('symbol', 'N/A'),
                                'price': float(price or 0),
                                'market_cap': float(market_cap or 0),
                                'liquidity': float(liquidity or 0),
                                'volume_24h': float(volume_24h or 0),
                                'fdv': float(fdv or 0),
                                'price_change_1m': float(price_change_1m or 0),
                                'price_change_5m': float(price_change_5m or 0),
                                'price_change_1h': float(price_change_1h or 0),
                                'price_change_24h': float(price_change_24h or 0),
                                'dex': pair.get('dexId', 'Unknown'),
                                'pair_address': pair.get('pairAddress', address),
                            }

                            result['logo'] = base.get('logo') or base.get('logoURI') or None
                            result['website'] = base.get('website') or None
                            result['twitter'] = base.get('twitter') or None
                            result['telegram'] = base.get('telegram') or None
                            result['holder_count'] = base.get('holders') or data.get('holdersCount') or None

                            vol = pair.get('volume', {}) or {}
                            if not isinstance(vol, dict):
                                vol = {}
                            result['buy_volume_24h'] = float(vol.get('h24_buy', 0) or 0)
                            result['sell_volume_24h'] = float(vol.get('h24_sell', 0) or 0)

                            try:
                                from helius import get_token_metadata

                                helius_meta = None
                                try:
                                    helius_meta = await get_token_metadata(address)
                                except Exception:
                                    helius_meta = None

                                if helius_meta:
                                    result['logo'] = result.get('logo') or helius_meta.get('logo') or helius_meta.get('image')
                                    result['website'] = result.get('website') or helius_meta.get('website')
                                    social = helius_meta.get('socials', {}) if isinstance(helius_meta.get('socials', {}), dict) else {}
                                    result['twitter'] = result.get('twitter') or social.get('twitter')
                                    result['telegram'] = result.get('telegram') or social.get('telegram')
                            except Exception:
                                pass

                            return result

                        if isinstance(data.get('tokens'), list) and data['tokens']:
                            token = data['tokens'][0]
                            if isinstance(token, dict):
                                return {
                                    'address': address,
                                    'name': token.get('name', 'Unknown'),
                                    'symbol': token.get('symbol', 'N/A'),
                                    'price': float(token.get('priceUsd') or token.get('price') or 0),
                                    'market_cap': float(token.get('marketCap') or token.get('market_cap') or 0),
                                    'liquidity': float(token.get('liquidityUsd') or token.get('liquidity_usd') or token.get('liquidity') or 0),
                                    'volume_24h': float(token.get('volume24h') or token.get('volume_24h') or 0),
                                    'fdv': float(token.get('fdv') or token.get('fullyDilutedValuation') or 0),
                                    'price_change_1m': float(token.get('priceChange1m') or token.get('price_change_1m') or 0),
                                    'price_change_5m': float(token.get('priceChange5m') or token.get('price_change_5m') or 0),
                                    'price_change_1h': float(token.get('priceChange1h') or token.get('price_change_1h') or 0),
                                    'price_change_24h': float(token.get('priceChange24h') or token.get('price_change_24h') or 0),
                                    'dex': token.get('dexId', 'Unknown'),
                                    'pair_address': token.get('pairAddress', address),
                                }
                except Exception:
                    continue

        return None
    except Exception as e:
        print(f"Error fetching DexScreener data: {e}")
        return None
