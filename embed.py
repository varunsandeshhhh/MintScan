import discord
from typing import Dict, Optional

DEFAULT_SOLANA_LOGO_URL = "https://cryptologos.cc/logos/solana-sol-logo.png"


def _to_number(value, default: float = 0.0) -> float:
    """Safely coerce values to numbers, treating None and invalid data as zero."""
    if value is None:
        return float(default)
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def format_number(num: float) -> str:
    """Format large numbers with K, M, B suffixes."""
    num = _to_number(num, 0.0)
    if num >= 1_000_000_000:
        return f"${num / 1_000_000_000:.2f}B"
    elif num >= 1_000_000:
        return f"${num / 1_000_000:.2f}M"
    elif num >= 1_000:
        return f"${num / 1_000:.2f}K"
    else:
        return f"${num:.2f}"


def _format_change(value) -> str:
    value = _to_number(value, 0)
    prefix = "+" if value >= 0 else ""
    return f"{prefix}{value:.2f}%"


def build_large_token_embed(token_data: Dict, risk_data: Optional[Dict] = None, security_data: Optional[Dict] = None) -> discord.Embed:
    """Build a larger, richer token embed for Discord visibility."""
    embed = build_token_embed(token_data, risk_data, security_data, minimal=False)
    embed.description = (
        f"{embed.description or ''}\n\n"
        "🔎 Bigger scan card with stronger signal breakdown and more context."
    )
    embed.set_author(name="MemeCoinScanner", icon_url="https://cdn.discordapp.com/embed/avatars/0.png")
    embed.timestamp = discord.utils.utcnow()
    embed.colour = embed.colour or 0x5865F2
    return embed


def build_token_embed(token_data: Dict, risk_data: Optional[Dict] = None, security_data: Optional[Dict] = None, minimal: bool = False) -> discord.Embed:
    """Build a professional token information embed similar to Qutex style."""
    
    # Main embed with token info
    name = token_data.get('name', 'Unknown')
    symbol = token_data.get('symbol', 'N/A')
    price = _to_number(token_data.get('price', 0), 0)
    market_cap = _to_number(token_data.get('market_cap', 0), 0)
    liquidity = _to_number(token_data.get('liquidity', 0), 0)
    volume_24h = _to_number(token_data.get('volume_24h', 0), 0)
    price_change = _to_number(token_data.get('price_change_24h', 0), 0)
    price_change_1m = _to_number(token_data.get('price_change_1m', 0), 0)
    price_change_5m = _to_number(token_data.get('price_change_5m', 0), 0)
    price_change_1h = _to_number(token_data.get('price_change_1h', 0), 0)
    price_change_24h = _to_number(token_data.get('price_change_24h', 0), 0)
    dex = token_data.get('dex', 'Unknown').upper()
    ath = _to_number(token_data.get('ath', 0), 0)
    ath_change = _to_number(token_data.get('ath_change', 0), 0)
    
    # Color based on price change
    color = 0x00FF00 if price_change >= 0 else 0xFF0000
    if risk_data:
        risk_score = _to_number(risk_data.get('risk_score', 50), 50)
        if risk_score > 70:
            color = 0xFF0000
        elif risk_score > 40:
            color = 0xFFA500
        else:
            color = 0x00FF00
    
    # Minimal mode reduces description, hides links/footer and shortens fields
    desc = f"[{dex}]" if minimal else f"[{dex}] • Solana"
    embed = discord.Embed(
        title=f"{name} • {symbol}",
        description=desc,
        color=color,
    )

    embed.set_author(name="Solana Scan", icon_url=DEFAULT_SOLANA_LOGO_URL)
    logo = token_data.get('logo')
    embed.set_thumbnail(url=logo or DEFAULT_SOLANA_LOGO_URL)
    
    # Price section
    price_str = f"${price:.6f}" if price < 0.01 else f"${price:.2f}"
    change_emoji = "📈" if price_change >= 0 else "📉"
    # Compact single-line stats field to keep embed small
    stats_value = (
        f"{price_str} {change_emoji} {price_change:+.2f}%"
        f" • MC {format_number(market_cap)}"
        f" • LP {format_number(liquidity)}"
        f" • Vol {format_number(volume_24h)}"
    )

    embed.add_field(name="📊 Stats", value=stats_value, inline=False)

    # If minimal mode requested, keep a single-line concise description
    if minimal:
        # Short security indicator: combine key flags into very short tokens
        sec_parts = []
        if security_data:
            lp = security_data.get('lp_locked')
            if lp is True:
                sec_parts.append('LP🔒')
            elif lp is False:
                sec_parts.append('LP⚠️')
            if security_data.get('honeypot') is True:
                sec_parts.append('HNP🔴')
        sec_summary = ' '.join(sec_parts) if sec_parts else ''

        # Build concise one-line description
        desc_parts = [f"[{dex}]", f"{price_str}", f"{change_emoji}{price_change:+.0f}%"]
        if market_cap:
            desc_parts.append(f"MC{format_number(market_cap)}")
        if liquidity:
            desc_parts.append(f"LQ{format_number(liquidity)}")
        if sec_summary:
            desc_parts.append(sec_summary)

        embed.description = ' • '.join(desc_parts)
        return embed
    
    # Risk section
    if risk_data:
        risk_level = risk_data.get('risk_level', 'Unknown')
        risk_score = _to_number(risk_data.get('risk_score', 0), 0)
        embed.add_field(
            name="⚠️ Risk Level",
            value=f"{risk_level} ({risk_score}/100)",
            inline=True,
        )
        
        # Owner info
        owner_renounced = "✅ Yes" if risk_data.get('owner_is_renounced') else "❌ No"
        embed.add_field(
            name="Owner Renounced",
            value=owner_renounced,
            inline=True,
        )

    # Security summary
    if security_data:
        sec_lines = []
        lp = security_data.get('lp_locked')
        if lp is True:
            sec_lines.append('LP🔒')
        elif lp is False:
            sec_lines.append('LP⚠️')

        mint_disabled = security_data.get('mint_authority_disabled')
        if mint_disabled is True:
            sec_lines.append('Mint✅')
        elif mint_disabled is False:
            sec_lines.append('Mint❌')

        freeze_disabled = security_data.get('freeze_authority_disabled')
        if freeze_disabled is True:
            sec_lines.append('Frz✅')
        elif freeze_disabled is False:
            sec_lines.append('Frz❌')

        honeypot = security_data.get('honeypot')
        if honeypot is True:
            sec_lines.append('Hnp🔴')
        elif honeypot is False:
            sec_lines.append('Hnp🟢')

        tax = security_data.get('tax_percent')
        if tax is not None:
            try:
                sec_lines.append(f'Tax:{int(round(tax))}%')
            except Exception:
                sec_lines.append(f'Tax:{tax}%')

        if sec_lines:
            # Abbreviated security summary; in minimal mode keep inline
            embed.add_field(name='🔐 Sec', value=' • '.join(sec_lines), inline=True)

    # If we have suspicious wallets, add a short summary
    if security_data and security_data.get('suspicious_wallets'):
        sw = security_data.get('suspicious_wallets')[:5]
        lines = [f"{s.get('address')[:8]}...: {s.get('percentage'):.1f}%" for s in sw]
        embed.add_field(name='🚩 Suspicious Wallets', value='\n'.join(lines), inline=False)
    
    # Token address
    address = token_data.get('address', 'Unknown')
    short_address = f"{address[:6]}...{address[-6:]}"
    embed.add_field(
        name="📋 Contract",
        value=f"`{short_address}`",
        inline=True,
    )

    # Price-change breakdown and volume snapshot
    embed.add_field(
        name="📈 Moves",
        value=(
            f"1m {_format_change(price_change_1m)} • 5m {_format_change(price_change_5m)}\n"
            f"1h {_format_change(price_change_1h)} • 24h {_format_change(price_change_24h)}"
        ),
        inline=False,
    )

    buy_volume = _to_number(token_data.get('buy_volume_24h', 0), 0)
    sell_volume = _to_number(token_data.get('sell_volume_24h', 0), 0)
    embed.add_field(
        name="💸 Volume",
        value=f"Buy {format_number(buy_volume)} • Sell {format_number(sell_volume)}",
        inline=True,
    )

    holder_count = token_data.get('holder_count')
    if holder_count is not None:
        embed.add_field(name="👥 Holders", value=f"{holder_count}", inline=True)

    if ath and ath > 0:
        ath_label = "ATH"
        if ath_change != 0:
            ath_label = f"ATH ({ath_change:+.2f}%)"
        embed.add_field(name="🏆 All-time high", value=f"${ath:.2f} {ath_label}", inline=True)

    links = []
    address = token_data.get('address', '')
    bubble_url = f"https://v2.bubblemaps.io/map?address={address}&chain=solana"
    links.append(f"[Bubblemap 🫧]({bubble_url})")

    logo_url = token_data.get('logo') or token_data.get('image')
    if logo_url:
        lens_url = f"https://lens.google.com/uploadbyurl?url={logo_url}"
        links.append(f"[Google lens 🎨]({lens_url})")

    if token_data.get('website'):
        links.append(f"[Website 🌍]({token_data.get('website')})")

    if not minimal:
        embed.add_field(name="🛠 Utility", value="\n".join(links), inline=False)

    # Minimal mode uses a shorter footer or hides it
    if not minimal:
        embed.set_footer(text="MemeCoinScanner")
    
    return embed


def create_button_view(token_data: Dict) -> discord.ui.View:
    """Create a view with buttons for external links."""
    
    view = discord.ui.View()
    address = token_data.get('address', '')
    pair_address = token_data.get('pair_address', '')
    dex = token_data.get('dex', 'raydium').lower()
    
    # DexScreener button
    dexscreener_url = f"https://dexscreener.com/solana/{pair_address}"
    view.add_item(
        discord.ui.Button(
            label="📊 DexScreener",
            url=dexscreener_url,
            style=discord.ButtonStyle.link,
        )
    )
    
    # BubbleMaps button
    bubblemaps_url = f"https://bubbleMaps.io/token/solana/{address}"
    view.add_item(
        discord.ui.Button(
            label="🗺️ BubbleMaps",
            url=bubblemaps_url,
            style=discord.ButtonStyle.link,
        )
    )
    
    # RugCheck button
    rugcheck_url = f"https://rugcheck.xyz/tokens/solana/{address}"
    view.add_item(
        discord.ui.Button(
            label="🔍 RugCheck",
            url=rugcheck_url,
            style=discord.ButtonStyle.link,
        )
    )
    
    # Solscan button
    solscan_url = f"https://solscan.io/token/{address}"
    view.add_item(
        discord.ui.Button(
            label="🔗 Solscan",
            url=solscan_url,
            style=discord.ButtonStyle.link,
        )
    )

    logo_url = token_data.get('logo') or token_data.get('image')
    if logo_url:
        lens_url = f"https://lens.google.com/uploadbyurl?url={logo_url}"
        view.add_item(
            discord.ui.Button(
                label="🎨 Google Lens",
                url=lens_url,
                style=discord.ButtonStyle.link,
            )
        )

    website = token_data.get('website')
    if website:
        view.add_item(
            discord.ui.Button(
                label="🌐 Website",
                url=website,
                style=discord.ButtonStyle.link,
            )
        )

    twitter = token_data.get('twitter')
    if twitter:
        view.add_item(
            discord.ui.Button(
                label="𝕏 X",
                url=f"https://twitter.com/{twitter.lstrip('@')}",
                style=discord.ButtonStyle.link,
            )
        )

    telegram = token_data.get('telegram')
    if telegram:
        view.add_item(
            discord.ui.Button(
                label="📣 Telegram",
                url=telegram,
                style=discord.ButtonStyle.link,
            )
        )
    
    return view

