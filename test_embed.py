from embed import build_large_token_embed, build_token_embed


def test_build_token_embed_handles_none_metrics():
    token_data = {
        'name': 'Test Token',
        'symbol': 'TEST',
        'price': None,
        'market_cap': None,
        'liquidity': None,
        'volume_24h': None,
        'price_change_24h': None,
        'address': '1234567890123456789012345678901234567890',
        'dex': 'raydium',
    }

    embed = build_token_embed(token_data, minimal=True)

    assert embed.title == 'Test Token • TEST'


def test_build_token_embed_includes_price_changes_and_volume_breakdown():
    token_data = {
        'name': 'Momentum Token',
        'symbol': 'MOMO',
        'price': 1.23,
        'market_cap': 1200000,
        'liquidity': 800000,
        'volume_24h': 150000,
        'price_change_24h': 8.5,
        'price_change_1m': 1.2,
        'price_change_5m': 3.4,
        'price_change_1h': 6.1,
        'buy_volume_24h': 90000,
        'sell_volume_24h': 60000,
        'address': '1234567890123456789012345678901234567890',
        'dex': 'raydium',
    }

    embed = build_token_embed(token_data, minimal=False)

    field_names = [field.name for field in embed.fields]
    assert '📈 Moves' in field_names
    assert '💸 Volume' in field_names


def test_build_large_token_embed_uses_rich_layout():
    token_data = {
        'name': 'Large Token',
        'symbol': 'LARGE',
        'price': 2.5,
        'market_cap': 2000000,
        'liquidity': 900000,
        'volume_24h': 250000,
        'price_change_24h': 4.2,
        'address': '1234567890123456789012345678901234567890',
        'dex': 'orca',
    }

    embed = build_large_token_embed(token_data)

    assert embed.footer.text == 'MemeCoinScanner'
    assert embed.author.name == 'Solana Scan'
    assert any(field.name == '📊 Stats' for field in embed.fields)
    assert any(field.name == '📈 Moves' for field in embed.fields)
    assert any(field.name == '💸 Volume' for field in embed.fields)
