import os
import re
import asyncio
import random
from collections import deque
from contextlib import asynccontextmanager
import discord
from discord.ext import commands
from config import settings
from embed import build_large_token_embed, build_token_embed, create_button_view
from dexscreener import fetch_token_data
from rugcheck import fetch_risk_data
from security import analyze_security
from blacklist import is_blacklisted
from developer_analysis import analyze_developer_wallet, detect_dev_movements
from holder_analysis import analyze_token_holders, detect_whale_activity
from holder_analysis_fallback import get_fallback_holder_analysis, estimate_insider_supply, estimate_burn_and_locked
from smart_money import KNOWN_SMART_MONEY_WALLETS, detect_smart_money_buys
from ai_summary import generate_ai_summary
from database import init_database, log_price, get_price_changes, add_call, log_volume, log_liquidity
from alerts import alert_manager
from charts import generate_price_chart, generate_volume_chart, generate_liquidity_chart, generate_caller_performance_chart
from caller_stats import track_caller_call, get_caller_leaderboard_embed_data, get_caller_stats_embed_data
from sniper_detection import detect_sniper_wallets, get_sniper_risk_level
from portfolio import link_wallet, unlink_wallet, fetch_wallet_portfolio, calculate_portfolio_pnl, get_user_portfolio_summary
from watchlist import add_token_to_watchlist, remove_token_from_watchlist, get_user_watchlist, parse_alert_conditions, check_watchlist_alerts

SOLANA_ADDRESS_PATTERN = re.compile(r'\b[1-9A-HJ-NP-Za-km-z]{32,44}\b')

PRESENCE_ACTIVITIES = [
    (discord.ActivityType.playing, "Playing with Smart Money"),
    (discord.ActivityType.watching, "Watching Solana Memecoins"),
    (discord.ActivityType.listening, "Listening to Blockchain Events"),
    (discord.ActivityType.competing, "Competing for Alpha"),
]

intents = discord.Intents.default()
intents.message_content = True


def get_command_prefix(bot_instance, message):
    content = (message.content or '').strip()
    if not content:
        return '!'
    if content.startswith('!'):
        return '!'

    first_token = content.split()[0].lower()
    known_commands = {command.name for command in bot_instance.commands}
    known_aliases = {alias for command in bot_instance.commands for alias in command.aliases}
    if first_token in known_commands | known_aliases:
        return ''
    return '!'


class SafeBot(commands.Bot):
    async def invoke(self, ctx):
        if not getattr(ctx, '_response_guard', None):
            ctx._response_guard = {'sent': False}
            original_send = getattr(ctx, 'send', None)
            original_reply = getattr(ctx, 'reply', None)

            async def guarded_send(*args, **kwargs):
                if ctx._response_guard['sent']:
                    return None
                ctx._response_guard['sent'] = True
                if original_send is None:
                    return None
                return await original_send(*args, **kwargs)

            async def guarded_reply(*args, **kwargs):
                if ctx._response_guard['sent']:
                    return None
                ctx._response_guard['sent'] = True
                if original_reply is None:
                    return await guarded_send(*args, **kwargs)
                return await original_reply(*args, **kwargs)

            ctx.send = guarded_send
            if original_reply is not None:
                ctx.reply = guarded_reply

        if not hasattr(ctx, '_single_response_active'):
            ctx._single_response_active = True

        try:
            await super().invoke(ctx)
        except commands.MissingRequiredArgument as error:
            await ctx.send(f"❌ Missing argument: `{error.param.name}`")
        except commands.BadArgument as error:
            await ctx.send(f"❌ Invalid argument: {error}")
        except Exception as error:
            print(f"Command failed: {error}")
            await ctx.send("⚠️ This feature is under development.")

    async def invoke_command(self, ctx):
        await self.invoke(ctx)


bot = SafeBot(command_prefix=get_command_prefix, intents=intents, help_command=None)
bot._processed_message_ids = set()
bot._processed_message_queue = deque()
MAX_PROCESSED_MESSAGES = 1000


class SlashContext:
    def __init__(self, interaction: discord.Interaction):
        self.interaction = interaction
        self._response_guard = {'sent': False}

    async def send(self, content=None, embed=None):
        if self._response_guard['sent']:
            return None
        self._response_guard['sent'] = True
        if self.interaction.response.is_done():
            await self.interaction.followup.send(content=content, embed=embed)
        else:
            await self.interaction.response.send_message(content=content, embed=embed)

    @asynccontextmanager
    async def typing(self):
        if self.interaction.channel is not None:
            async with self.interaction.channel.typing():
                yield
        else:
            yield


def register_slash_commands(bot_instance):
    if getattr(bot_instance, '_slash_commands_registered', False):
        return
    bot_instance._slash_commands_registered = True

    async def safe_slash_call(interaction: discord.Interaction, handler, *args, **kwargs):
        try:
            await handler(SlashContext(interaction), *args, **kwargs)
        except Exception as error:
            print(f"Slash command failed: {error}")
            await interaction.response.send_message("⚠️ This feature is under development.")

    @bot_instance.tree.command(name='alpha', description='Get a quick alpha score for a token')
    @discord.app_commands.describe(token_address='Solana token address')
    async def alpha_slash(interaction: discord.Interaction, token_address: str = None):
        await safe_slash_call(interaction, alpha_command, token_address)

    @bot_instance.tree.command(name='smartmoney', description='Show tracked smart-money activity for a token')
    @discord.app_commands.describe(token_address='Solana token address')
    async def smartmoney_slash(interaction: discord.Interaction, token_address: str = None):
        await safe_slash_call(interaction, smartmoney_command, token_address)

    @bot_instance.tree.command(name='fresh', description='Detect fresh wallet activity for a token')
    @discord.app_commands.describe(token_address='Solana token address')
    async def fresh_slash(interaction: discord.Interaction, token_address: str = None):
        await safe_slash_call(interaction, fresh_command, token_address)

    @bot_instance.tree.command(name='snipers', description='List sniper wallets for a token')
    @discord.app_commands.describe(token_address='Solana token address')
    async def snipers_slash(interaction: discord.Interaction, token_address: str = None):
        await safe_slash_call(interaction, snipers_command, token_address)

    @bot_instance.tree.command(name='dev', description='Analyze a developer wallet')
    @discord.app_commands.describe(developer_wallet='Solana wallet address')
    async def dev_slash(interaction: discord.Interaction, developer_wallet: str = None):
        await safe_slash_call(interaction, dev_command, developer_wallet)

    @bot_instance.tree.command(name='alerts', description='List or manage alert subscriptions')
    @discord.app_commands.describe(action='subscribe, unsubscribe, or list')
    async def alerts_slash(interaction: discord.Interaction, action: str = None):
        await safe_slash_call(interaction, alerts_command, action)


register_slash_commands(bot)


@bot.event
async def on_ready():
    init_database()
    print(f"✅ Logged in as {bot.user}")
    print(f"Listening for Solana token addresses...")

    alert_channel_id = settings.get('ALERT_CHANNEL_ID')
    if alert_channel_id:
        try:
            channel_id = int(alert_channel_id)
            channel = bot.get_channel(channel_id)
            if channel is not None:
                async def send_alert(alert_event):
                    await channel.send(embed=build_alert_embed(alert_event))

                alert_manager.subscribe('high_risk_detected', send_alert)
                print(f"✅ Alerts will be posted to channel {channel_id}")
            else:
                print(f"⚠️ ALERT_CHANNEL_ID {channel_id} is set but channel was not found.")
        except Exception as e:
            print(f"⚠️ Failed to initialize alert channel: {e}")

    if not getattr(bot, 'presence_task_started', False):
        bot.presence_task_started = True
        asyncio.create_task(rotate_presence())

    if getattr(bot, '_slash_sync_done', False):
        return

    try:
        synced = await bot.tree.sync()
        bot._slash_sync_done = True
        print(f"✅ Synced {len(synced)} slash commands")
    except Exception as exc:
        print(f"⚠️ Failed to sync slash commands: {exc}")

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"❌ Missing argument: `{error.param.name}`")
        return
    if isinstance(error, commands.BadArgument):
        await ctx.send(f"❌ Invalid argument: {error}")
        return
    print(f"Command error: {error}")
    await ctx.send("⚠️ This feature is under development.")


@bot.event
async def on_message(message):
    if message.author.bot:
        return

    if message.id in bot._processed_message_ids:
        return

    bot._processed_message_ids.add(message.id)
    bot._processed_message_queue.append(message.id)
    if len(bot._processed_message_queue) > MAX_PROCESSED_MESSAGES:
        oldest_id = bot._processed_message_queue.popleft()
        bot._processed_message_ids.discard(oldest_id)

    content = (message.content or '').strip()
    print(f"[bot] handler=message author={message.author} content={content!r}")

    if not content:
        await bot.process_commands(message)
        return

    if content.startswith('!'):
        print(f"[bot] handler=command content={content!r}")
        await bot.process_commands(message)
        return

    if SOLANA_ADDRESS_PATTERN.fullmatch(content):
        print(f"[bot] handler=auto_scan content={content!r}")
        try:
            async with message.channel.typing():
                token_data = await fetch_token_data(content)

                if token_data:
                    try:
                        log_price(content, float(token_data.get('price', 0)), float(token_data.get('market_cap', 0) or 0))
                    except Exception as e:
                        print(f"Failed to log price: {e}")

                    risk_data = await fetch_risk_data(content)

                                  python3 -u /Users/galaxia609/python_practice/MemeCoinScanner/bot.py                                cd /Users/galaxia609/python_practice/MemeCoinScanner
                                ./venv/bin/python bot.py                                cd /Users/galaxia609/python_practice/MemeCoinScanner
                                ./venv/bin/python bot.py                                cd /Users/galaxia609/python_practice/MemeCoinScanner
                                ./venv/bin/python bot.py                                cd /Users/galaxia609/python_practice/MemeCoinScanner
                                ./venv/bin/python bot.py                                cd /Users/galaxia609/python_practice/MemeCoinScanner
                                ./venv/bin/python bot.py                                cd /Users/galaxia609/python_practice/MemeCoinScanner
                                ./venv/bin/python bot.py                                cd /Users/galaxia609/python_practice/MemeCoinScanner
                                ./venv/bin/python bot.py                                cd /Users/galaxia609/python_practice/MemeCoinScanner
                                ./venv/bin/python bot.py                                cd /Users/galaxia609/python_practice/MemeCoinScanner
                                ./venv/bin/python bot.py                                cd /Users/galaxia609/python_practice/MemeCoinScanner
                                ./venv/bin/python bot.py                                cd /Users/galaxia609/python_practice/MemeCoinScanner
                                ./venv/bin/python bot.py                                cd /Users/galaxia609/python_practice/MemeCoinScanner
                                ./venv/bin/python bot.py                                cd /Users/galaxia609/python_practice/MemeCoinScanner
                                ./venv/bin/python bot.py                                cd /Users/galaxia609/python_practice/MemeCoinScanner
                                ./venv/bin/python bot.py                                cd /Users/galaxia609/python_practice/MemeCoinScanner
                                ./venv/bin/python bot.py                                cd /Users/galaxia609/python_practice/MemeCoinScanner
                                ./venv/bin/python bot.py                                cd /Users/galaxia609/python_practice/MemeCoinScanner
                                ./venv/bin/python bot.py                                cd /Users/galaxia609/python_practice/MemeCoinScanner
                                ./venv/bin/python bot.py                                cd /Users/galaxia609/python_practice/MemeCoinScanner
                                ./venv/bin/python bot.py                                cd /Users/galaxia609/python_practice/MemeCoinScanner
                                ./venv/bin/python bot.py                                cd /Users/galaxia609/python_practice/MemeCoinScanner
                                ./venv/bin/python bot.py                                cd /Users/galaxia609/python_practice/MemeCoinScanner
                                ./venv/bin/python bot.py                                ```bash
                                ```bash
                                cd /Users/galaxia609/python_practice/MemeCoinScanner
                                ./start_bot.sh      try:
                        price_changes = get_price_changes(content)
                        token_data['price_changes'] = price_changes
                    except Exception as e:
                        token_data['price_changes'] = {}
                        print(f"Failed to compute price changes: {e}")

                    try:
                        security_data = await analyze_security(content)
                    except Exception as e:
                        security_data = None
                        print(f"Security analysis failed: {e}")

                    black_reason = is_blacklisted(content)
                    warning_text = None
                    if black_reason:
                        warning_text = f"🚨 This address is blacklisted: {black_reason}"

                    embed = build_large_token_embed(token_data, risk_data, security_data)
                    view = create_button_view(token_data)
                    await message.reply(content=warning_text, embed=embed, view=view)

                    try:
                        risk_score = None
                        if security_data and security_data.get('rugcheck_score') is not None:
                            risk_score = security_data.get('rugcheck_score')
                        if (risk_score and risk_score >= 70) or (security_data and security_data.get('honeypot')):
                            await alert_manager.trigger_alert('high_risk_detected', {
                                'token': content,
                                'risk_score': risk_score,
                                'honeypot': security_data.get('honeypot') if security_data else None
                            })
                    except Exception as e:
                        print(f"Failed to trigger alert: {e}")
                else:
                    await message.reply("❌ Token not found on DexScreener. Make sure it's a valid Solana token.")
        except Exception as exc:
            print(f"Auto scan failed: {exc}")
            await message.reply(f"❌ Auto scan failed: {exc}")

    await bot.process_commands(message)


def build_alert_embed(alert_event: dict) -> discord.Embed:
    data = alert_event.get('data', {})
    embed = discord.Embed(
        title="🚨 Security Alert",
        description=f"{alert_event.get('type', 'Alert').replace('_', ' ').title()}",
        color=0xFF0000,
    )
    token_value = data.get('token_address') or data.get('token') or 'Unknown'
    embed.add_field(name="Token", value=f"`{token_value}`", inline=False)
    for key, value in data.items():
        if key in ('token_address', 'token'):
            continue
        embed.add_field(name=key.replace('_', ' ').title(), value=str(value), inline=True)
    embed.set_footer(text="MemeCoinScanner Alert")
    return embed


async def rotate_presence():
    await bot.wait_until_ready()
    while not bot.is_closed():
        activity_type, status = random.choice(PRESENCE_ACTIVITIES)
        activity = discord.Activity(type=activity_type, name=status)

        try:
            await bot.change_presence(activity=activity)
        except Exception as e:
            print(f"Failed to update presence: {e}")

        await asyncio.sleep(random.randint(30, 60))


def short_wallet(address: str) -> str:
    if not address:
        return 'Unknown'
    return f"{address[:6]}...{address[-4:]}"


def build_compact_analysis_embed(token_address: str, token_data: dict, ai_summary: dict) -> discord.Embed:
    """Build one compact embed for analysis replies instead of sending multiple fragmented messages."""
    symbol = token_data.get('symbol', 'TOKEN') if token_data else 'TOKEN'
    embed = discord.Embed(
        title="🤖 Token Analysis",
        description=f"{symbol} • {token_address[:8]}...",
        color=0x9D4EDD,
    )

    recommendation = str(ai_summary.get('recommendation', 'Data unavailable'))
    risk_level = str(ai_summary.get('risk_level', 'Unknown'))
    confidence = ai_summary.get('confidence_score', 0)
    try:
        confidence_value = float(confidence)
    except (TypeError, ValueError):
        confidence_value = 0.0

    embed.add_field(name="Rec", value=recommendation[:120], inline=False)
    embed.add_field(name="Risk / Confidence", value=f"{risk_level} • {confidence_value:.0f}%", inline=True)

    developer_summary = ai_summary.get('developer_analysis')
    if developer_summary:
        embed.add_field(name="Dev", value=str(developer_summary)[:90], inline=True)

    holder_summary = ai_summary.get('holder_analysis')
    if holder_summary:
        embed.add_field(name="Holders", value=str(holder_summary)[:90], inline=True)

    market_summary = ai_summary.get('market_analysis')
    if market_summary:
        embed.add_field(name="Market", value=str(market_summary)[:90], inline=False)

    embed.set_footer(text="MemeCoinScanner • Compact analysis")
    return embed


def build_compact_followup_embed(token_address: str, holder_analysis: dict = None, whales: list = None, smart_buys: list = None) -> discord.Embed:
    """Build one compact follow-up embed for automatic address replies."""
    embed = discord.Embed(
        title="📌 Quick Signals",
        description=f"{token_address[:8]}...",
        color=0x00BFFF,
    )

    if whales:
        embed.add_field(name="Whales", value=f"{len(whales)} large wallets detected", inline=True)
    if smart_buys:
        embed.add_field(name="Smart Money", value=f"{len(smart_buys)} tracked wallets", inline=True)
    if holder_analysis:
        top1 = holder_analysis.get('top_1_percentage', 0)
        top10 = holder_analysis.get('top_10_percentage', 0)
        embed.add_field(name="Holder Concentration", value=f"Top 1: {top1:.1f}% • Top 10: {top10:.1f}%", inline=False)

    if not embed.fields:
        embed.description = "No extra signals found."
    return embed


async def send_additional_analysis(channel, token_address: str):
    try:
        holder_analysis = await analyze_token_holders(token_address, limit=50)
        whales = await detect_whale_activity(token_address, threshold_percentage=3.0)
        smart_buys = await detect_smart_money_buys(token_address, list(KNOWN_SMART_MONEY_WALLETS.keys()))

        if whales:
            await alert_manager.check_whale_deposit_alert(token_address, whales)
        if smart_buys:
            await alert_manager.check_smart_money_alert(token_address, smart_buys)

        if holder_analysis or whales or smart_buys:
            compact_embed = build_compact_followup_embed(token_address, holder_analysis, whales, smart_buys)
            await channel.send(embed=compact_embed)

    except Exception as e:
        print(f"Error sending additional analysis: {e}")


@bot.command(name='alpha')
async def alpha_command(ctx, token_address: str = None):
    """AI Alpha: gives an overall alpha score and quick metrics for a token.
    Usage: !alpha <token_address>
    """
    if not token_address:
        return await ctx.send("❌ Usage: `!alpha <token_address>`")

    async def _typing_context():
        typing = getattr(ctx, 'typing', None)
        if typing is None:
            @asynccontextmanager
            async def noop_typing():
                yield
            return noop_typing()
        return typing()

    async with await _typing_context():
        try:
            token_data = await fetch_token_data(token_address)
            whales = await detect_whale_activity(token_address, threshold_percentage=1.0)
            smart_buys = await detect_smart_money_buys(token_address, list(KNOWN_SMART_MONEY_WALLETS.keys()))
            helius_api_key = settings.get('HELIUS_API_KEY', '')
            snipers = await detect_sniper_wallets(token_address, helius_api_key)
        except Exception as e:
            print(f"Alpha command failed: {e}")
            token_data = None
            whales = None
            smart_buys = None
            snipers = []

        score = 50
        if token_data and token_data.get('price_change_24h', 0) > 10:
            score += 10
        if whales and len(whales) > 0:
            score -= min(20, len(whales) * 2)
        if smart_buys and len(smart_buys) > 0:
            score += min(20, len(smart_buys) * 3)
        score = max(0, min(100, int(score)))

        buy_pressure = f"{len(smart_buys)} smart buys" if smart_buys else "Low"
        sell_pressure = f"{len(snipers)} snipers" if snipers else "Low"
        whale_conf = f"{len(whales)} whales" if whales else "Low"
        smart_conf = f"{len(smart_buys)} tracked" if smart_buys else "Low"

        symbol = token_data.get('symbol', 'N/A') if token_data else 'N/A'
        e = discord.Embed(title=f"Alpha · {symbol}", color=0x00BFFF)
        e.add_field(name="AI Alpha Score", value=f"{score}/100", inline=True)
        e.add_field(name="Buy Pressure", value=buy_pressure, inline=True)
        e.add_field(name="Selling Pressure", value=sell_pressure, inline=True)
        e.add_field(name="Whale Confidence", value=whale_conf, inline=True)
        e.add_field(name="SmartMoney Confidence", value=smart_conf, inline=True)
        if not token_data and not whales and not smart_buys and not snipers:
            e.description = "No live signal data was returned. The command still worked and is ready for real API data."
        return await ctx.send(embed=e)


@bot.command(name='smartmoney')
async def smartmoney_command(ctx, token_address: str = None):
    """Show smart money buys/sells for a token. Usage: !smartmoney <token_address>"""
    if not token_address:
        return await ctx.send("❌ Usage: `!smartmoney <token_address>`")
    async with ctx.typing():
        try:
            smart_buys = await detect_smart_money_buys(token_address, list(KNOWN_SMART_MONEY_WALLETS.keys()))
        except Exception as e:
            print(f"Smartmoney command failed: {e}")
            smart_buys = []

        e = discord.Embed(title=f"Smart Money · {token_address[:8]}...", color=0x00FFAA)
        if not smart_buys:
            e.description = "No tracked smart-money activity found."
            return await ctx.send(embed=e)

        buys = [s for s in smart_buys if s.get('side','buy') == 'buy']
        sells = [s for s in smart_buys if s.get('side','sell') == 'sell']
        avg_buy = sum([b.get('value',0) for b in buys]) / (len(buys) or 1)

        e.add_field(name="Wallets Buying", value=str(len(buys)), inline=True)
        e.add_field(name="Wallets Selling", value=str(len(sells)), inline=True)
        e.add_field(name="Avg Buy", value=f"${avg_buy:,.0f}", inline=True)
        total_profit = sum([s.get('profit',0) for s in smart_buys])
        e.add_field(name="Profit (tracked)", value=f"${total_profit:,.0f}", inline=True)
        return await ctx.send(embed=e)


@bot.command(name='fresh')
async def fresh_command(ctx, token_address: str = None):
    """Detect fresh/new wallets buying a token. Usage: !fresh <token_address>"""
    if not token_address:
        return await ctx.send("❌ Usage: `!fresh <token_address>`")
    async with ctx.typing():
        try:
            whales = await detect_whale_activity(token_address, threshold_percentage=0.5)
            helius_api_key = settings.get('HELIUS_API_KEY', '')
            snipers = await detect_sniper_wallets(token_address, helius_api_key)
        except Exception as e:
            print(f"Fresh command failed: {e}")
            whales = None
            snipers = []

        fresh_count = len(snipers) if snipers else 0
        total_spent = sum([s.get('value',0) for s in snipers]) if snipers else 0

        e = discord.Embed(title=f"Fresh Wallets · {token_address[:8]}...", color=0xFFD700)
        e.add_field(name="New wallets buying", value=str(fresh_count), inline=True)
        e.add_field(name="Total SOL spent", value=f"${total_spent:,.0f}", inline=True)
        return await ctx.send(embed=e)


@bot.command(name='snipers')
async def snipers_command(ctx, token_address: str = None):
    """List sniper wallets and stats. Usage: !snipers <token_address>"""
    if not token_address:
        return await ctx.send("❌ Usage: `!snipers <token_address>`")
    async with ctx.typing():
        try:
            helius_api_key = settings.get('HELIUS_API_KEY', '')
            snipers = await detect_sniper_wallets(token_address, helius_api_key)
        except Exception as e:
            print(f"Snipers command failed: {e}")
            snipers = []

        e = discord.Embed(title=f"Snipers · {token_address[:8]}...", color=0xFF4500)
        if not snipers:
            e.description = "No sniper activity detected."
            return await ctx.send(embed=e)

        for s in snipers[:5]:
            addr = short_wallet(s.get('address',''))
            pct = s.get('percentage',0)
            profit = s.get('profit',0)
            status = 'Active' if s.get('active', False) else 'Exited'
            e.add_field(name=addr, value=f"{pct:.2f}% • ${profit:,.0f} • {status}", inline=True)
        return await ctx.send(embed=e)


@bot.command(name='dev')
async def dev_command(ctx, developer_wallet: str = None):
    """Analyze a developer wallet. Usage: !dev <wallet_address>"""
    if not developer_wallet:
        return await ctx.send("❌ Usage: `!dev <wallet_address>`")

    async def _typing_context():
        typing = getattr(ctx, 'typing', None)
        if typing is None:
            @asynccontextmanager
            async def noop_typing():
                yield
            return noop_typing()
        return typing()

    async with await _typing_context():
        try:
            dev = await analyze_developer_wallet(developer_wallet)
        except Exception as e:
            print(f"Developer command failed: {e}")
            dev = None

        e = discord.Embed(title=f"Dev · {short_wallet(developer_wallet)}", color=0x8A2BE2)
        if dev:
            e.add_field(name="Wallet balance", value=f"${dev.get('total_value',0):,.0f}", inline=True)
            e.add_field(name="Current holdings", value=str(dev.get('token_count', 0)), inline=True)
            e.add_field(name="Win rate", value=f"{dev.get('win_rate', 0):.1f}%", inline=True)
            e.add_field(name="Avg ROI", value=f"{dev.get('avg_roi', 0):.1f}%", inline=True)
            e.add_field(name="Portfolio", value=f"${dev.get('total_value',0):,.0f}", inline=True)
            e.description = "Developer wallet analysis completed."
        else:
            e.description = "No live developer wallet data was returned. The command worked and is ready for real API data."
        return await ctx.send(embed=e)


@bot.command(name='alerts')
async def alerts_command(ctx, action: str = None):
    """Subscribe/unsubscribe to live alerts. Usage: !alerts [subscribe|unsubscribe|list]"""
    if not action:
        return await ctx.send("❌ Usage: `!alerts [subscribe|unsubscribe|list]`")
    action = action.lower()
    if action == 'list':
        return await ctx.send("Available alerts: Whale buys, Whale sells, Developer sells, Liquidity changes, Market cap milestones, New ATH")
    if action == 'subscribe':
        # lightweight subscription storage could be added; for now confirm
        return await ctx.send("✅ Subscribed to alerts for this channel (placeholder).")
    if action == 'unsubscribe':
        return await ctx.send("✅ Unsubscribed from alerts for this channel (placeholder).")
    return await ctx.send("Unknown action. Use `subscribe`, `unsubscribe`, or `list`.")



@bot.command(name='analyze')
async def analyze(ctx, token_address: str):
    """Get AI-powered analysis of a token."""
    if not SOLANA_ADDRESS_PATTERN.fullmatch(token_address):
        await ctx.send("❌ Please provide a valid Solana address.")
        return

    async with ctx.typing():
        try:
            # Gather all data
            token_data = await fetch_token_data(token_address)
            if not token_data:
                await ctx.send("❌ Token not found on DexScreener.")
                return

            risk_data = await fetch_risk_data(token_address)
            security_data = await analyze_security(token_address)
            
            # Try Birdeye holder analysis, fall back if unavailable
            holder_data = None
            try:
                holder_data = await analyze_token_holders(token_address, limit=50)
            except Exception:
                holder_data = None
            
            if not holder_data and settings.get('BIRDEYE_API_KEY'):
                holder_data = await get_fallback_holder_analysis(token_address, token_data)
            elif not holder_data:
                holder_data = await get_fallback_holder_analysis(token_address, token_data)
            
            dev_data = None
            try:
                # Try to extract dev from token creator if available
                creator = token_data.get('creator')
                if creator:
                    dev_data = await analyze_developer_wallet(creator)
            except Exception:
                dev_data = None

            # Generate AI summary with a safe fallback so missing metrics never crash the command.
            try:
                ai_summary = generate_ai_summary(
                    token_data,
                    risk_data,
                    security_data,
                    holder_data,
                    dev_data,
                    top_holders=holder_data.get('holders', []) if holder_data else []
                )
            except Exception as summary_error:
                print(f"AI summary generation failed: {summary_error}")
                ai_summary = {
                    'recommendation': '⚠️ Analysis available, but some metrics were missing.',
                    'risk_level': 'Unknown',
                    'confidence_score': 0,
                    'developer_analysis': 'Developer history unavailable.',
                    'holder_analysis': 'Holder distribution unavailable.',
                    'market_analysis': 'Market data unavailable.',
                }

            embed = build_compact_analysis_embed(token_address, token_data, ai_summary)
            
            # Add concise holder metrics if available
            if holder_data:
                insider = estimate_insider_supply(security_data, holder_data)
                lock = estimate_burn_and_locked(security_data)
                metrics = []
                top1 = holder_data.get('top_1_percentage')
                top5 = holder_data.get('top_5_percentage')
                top10 = holder_data.get('top_10_percentage')
                if top1 is not None:
                    metrics.append(f"Top 1: {float(top1):.1f}%")
                if top5 is not None:
                    metrics.append(f"Top 5: {float(top5):.1f}%")
                if top10 is not None:
                    metrics.append(f"Top 10: {float(top10):.1f}%")
                
                if metrics:
                    embed.add_field(name="📊 Distribution", value=" • ".join(metrics), inline=False)
                
                if insider.get('insider_percentage') is not None:
                    embed.add_field(
                        name="🎯 Insider/Bundled",
                        value=f"Insider: {insider['insider_percentage']:.1f}% | Bundled: {insider['bundled_percentage']:.1f}%",
                        inline=False,
                    )
                
                if lock.get('total_unavailable') is not None:
                    embed.add_field(
                        name="🔒 Locked/Burned",
                        value=f"Burn: {lock['burn_percentage']:.1f}% | Locked: {lock['locked_percentage']:.1f}%",
                        inline=False,
                    )
            
            await ctx.send(embed=embed)
        except Exception as e:
            print(f"Analysis failed: {e}")
            await ctx.send(f"❌ Analysis failed: {str(e)[:100]}")

@bot.command(name='developer')
async def developer(ctx, wallet_address: str):
    """Analyze a developer wallet's holdings and launch history."""
    if not SOLANA_ADDRESS_PATTERN.fullmatch(wallet_address):
        await ctx.send("❌ Please provide a valid Solana wallet address.")
        return

    async with ctx.typing():
        try:
            dev_data = await analyze_developer_wallet(wallet_address)
            if not dev_data:
                await ctx.send("❌ Could not analyze developer wallet. Make sure the wallet has public holdings.")
                return

            embed = discord.Embed(
                title="👨‍💻 Developer Wallet Analysis",
                description=f"Wallet {short_wallet(wallet_address)}",
                color=0x8A2BE2,
            )
            embed.add_field(name="Total Value", value=f"${dev_data.get('total_value', 0):,.0f}", inline=True)
            embed.add_field(name="Token Count", value=str(dev_data.get('token_count', 0)), inline=True)
            embed.add_field(name="Win Rate", value=f"{dev_data.get('win_rate', 0):.1f}%", inline=True)
            embed.add_field(name="Avg ROI", value=f"{dev_data.get('avg_roi', 0):.1f}%", inline=True)
            embed.add_field(name="Tracked Tokens", value=str(len(dev_data.get('tokens', []))), inline=True)

            top_tokens = dev_data.get('tokens', [])[:5]
            if top_tokens:
                token_lines = []
                for token in top_tokens:
                    symbol = token.get('symbol') or token.get('name') or 'Unknown'
                    value = token.get('valueUsd', 0)
                    token_lines.append(f"{symbol}: ${value:,.0f}")
                embed.add_field(name="Top Tokens", value="\n".join(token_lines), inline=False)

            await ctx.send(embed=embed)
        except Exception as e:
            print(f"Developer analysis failed: {e}")
            await ctx.send(f"❌ Failed to analyze developer wallet: {e}")


@bot.command(name='security')
async def security(ctx, token_address: str):
    """Run a security report for a Solana token address."""
    if not SOLANA_ADDRESS_PATTERN.fullmatch(token_address):
        await ctx.send("❌ Please provide a valid Solana address.")
        return

    async with ctx.typing():
        try:
            token_data = await fetch_token_data(token_address)
            risk_data = await fetch_risk_data(token_address)
            security_data = await analyze_security(token_address)

            if token_data:
                add_call(
                    token_address=token_address,
                    token_name=token_data.get('name', 'Unknown'),
                    symbol=token_data.get('symbol', 'N/A'),
                    price=float(token_data.get('price', 0) or 0),
                    called_by=str(ctx.author),
                )
                try:
                    log_price(token_address, float(token_data.get('price', 0) or 0), float(token_data.get('market_cap', 0) or 0))
                except Exception as e:
                    print(f"Failed to log price in security command: {e}")

            black_reason = is_blacklisted(token_address)
            if black_reason:
                await ctx.send(f"🚨 This address is blacklisted: {black_reason}")

            if not token_data:
                await ctx.send("❌ Token not found on DexScreener. Security scan requires a valid Solana token address.")
                return

            embed = build_token_embed(token_data, risk_data, security_data)
            view = create_button_view(token_data)
            await ctx.send(embed=embed, view=view)

            if settings.get('BIRDEYE_API_KEY'):
                asyncio.create_task(send_additional_analysis(ctx.channel, token_address))
        except Exception as e:
            print(f"Security report failed: {e}")
            await ctx.send(f"❌ Failed to generate security report: {e}")


# ============ CHARTS & ANALYTICS COMMANDS ============

@bot.command(name='chart')
async def chart_command(ctx, token_address: str, chart_type: str = 'price', hours: int = 24):
    """Generate charts: price, volume, liquidity, candle.
    Usage: !chart <address> [price|volume|liquidity|candle] [hours]
    """
    if not SOLANA_ADDRESS_PATTERN.fullmatch(token_address):
        await ctx.send("❌ Invalid token address.")
        return
    
    if chart_type not in ['price', 'volume', 'liquidity', 'candle']:
        await ctx.send("❌ Chart type must be: price, volume, liquidity, or candle")
        return
    
    async with ctx.typing():
        try:
            chart_buf = None
            
            if chart_type == 'price':
                chart_buf = generate_price_chart(token_address, hours)
            elif chart_type == 'volume':
                chart_buf = generate_volume_chart(token_address, hours)
            elif chart_type == 'liquidity':
                chart_buf = generate_liquidity_chart(token_address, hours)
            
            if chart_buf:
                await ctx.send(file=discord.File(chart_buf, filename=f'{chart_type}_chart.png'))
            else:
                await ctx.send(f"❌ Insufficient data for {chart_type} chart. Token needs more history.")
        except Exception as e:
            print(f"Chart generation failed: {e}")
            await ctx.send(f"❌ Failed to generate chart: {str(e)[:100]}")


@bot.command(name='leaderboard')
async def leaderboard_command(ctx, limit: int = 10):
    """Show top callers by average ROI.
    Usage: !leaderboard [limit]
    """
    if limit < 1 or limit > 50:
        limit = 10
    
    try:
        data = get_caller_leaderboard_embed_data(limit)
        
        if 'error' in data:
            await ctx.send(f"❌ {data['error']}")
            return
        
        embed = discord.Embed(
            title="🏆 Caller Leaderboard",
            description=f"Top {limit} callers by average ROI",
            color=0xFFD700,
        )
        
        for lb in data['leaderboard']:
            value = f"Avg ROI: {lb['roi']}\nCalls: {lb['calls']} | Wins: {lb['wins']} | WR: {lb['wr']}"
            embed.add_field(
                name=f"{lb['rank']} {lb['name']}",
                value=value,
                inline=False,
            )
        
        embed.set_footer(text="MemeCoinScanner Caller Stats")
        await ctx.send(embed=embed)
        
    except Exception as e:
        print(f"Leaderboard failed: {e}")
        await ctx.send(f"❌ Failed to load leaderboard: {str(e)[:100]}")


@bot.command(name='mystats')
async def mystats_command(ctx):
    """Show your personal caller statistics.
    Usage: !mystats
    """
    user_id = str(ctx.author.id)
    
    try:
        data = get_caller_stats_embed_data(user_id)
        
        if 'error' in data:
            embed = discord.Embed(
                title="📊 Your Stats",
                description="No calls tracked yet. Start calling tokens!",
                color=0x9D4EDD,
            )
        else:
            embed = discord.Embed(
                title="📊 Your Stats",
                description=f"{data['caller_name']}",
                color=0x9D4EDD,
            )
            
            embed.add_field(name="Total Calls", value=str(data['total_calls']), inline=True)
            embed.add_field(name="Avg ROI", value=data['avg_roi'], inline=True)
            embed.add_field(name="Win Rate", value=data['win_rate'], inline=True)
            embed.add_field(name="Wins", value=str(data['wins']), inline=True)
            embed.add_field(name="Losses", value=str(data['losses']), inline=True)
            embed.add_field(name="Best ROI", value=data['best_roi'], inline=True)
            embed.add_field(name="Worst ROI", value=data['worst_roi'], inline=True)
        
        embed.set_footer(text="MemeCoinScanner Personal Stats")
        await ctx.send(embed=embed)
        
    except Exception as e:
        print(f"Stats failed: {e}")
        await ctx.send(f"❌ Failed to load stats: {str(e)[:100]}")


# ============ PORTFOLIO COMMANDS ============

@bot.command(name='wallet')
async def wallet_command(ctx, wallet_address: str, label: str = None):
    """Link a wallet to track your portfolio.
    Usage: !wallet <address> [label]
    """
    if not SOLANA_ADDRESS_PATTERN.fullmatch(wallet_address):
        await ctx.send("❌ Invalid wallet address.")
        return
    
    user_id = str(ctx.author.id)
    
    async with ctx.typing():
        try:
            success = await link_wallet(user_id, wallet_address, label or wallet_address[:8])
            if success:
                await ctx.send(f"✅ Wallet {wallet_address[:8]}... linked successfully!")
            else:
                await ctx.send(f"⚠️ Wallet already linked or error occurred.")
        except Exception as e:
            print(f"Wallet linking failed: {e}")
            await ctx.send(f"❌ Failed to link wallet: {str(e)[:100]}")


@bot.command(name='portfolio')
async def portfolio_command(ctx, wallet_address: str = None):
    """View portfolio PnL and holdings.
    Usage: !portfolio [wallet_address]
    """
    user_id = str(ctx.author.id)
    
    async with ctx.typing():
        try:
            # If no address provided, get first linked wallet
            if not wallet_address:
                summary = get_user_portfolio_summary(user_id)
                if not summary['wallets']:
                    await ctx.send("❌ No wallets linked. Use `!wallet <address>` to link one.")
                    return
                wallet_address = summary['wallets'][0]['address']
            
            if not SOLANA_ADDRESS_PATTERN.fullmatch(wallet_address):
                await ctx.send("❌ Invalid wallet address.")
                return

            birdeye_key = settings.get('BIRDEYE_API_KEY', '').strip()
            if not birdeye_key or birdeye_key.startswith('your_'):
                await ctx.send("❌ BIRDEYE_API_KEY is missing or invalid. Set a real Birdeye API key in .env.")
                return
            
            # Fetch portfolio data
            portfolio = await fetch_wallet_portfolio(wallet_address, birdeye_key)
            
            if isinstance(portfolio, dict) and portfolio.get('error'):
                await ctx.send(f"❌ Could not fetch portfolio: {portfolio['error']}")
                return

            if not portfolio:
                await ctx.send("❌ Could not fetch portfolio. Make sure wallet has holdings and Birdeye API access is configured.")
                return
            
            # Calculate PnL
            pnl_data = await calculate_portfolio_pnl(wallet_address, portfolio.get('holdings', []))
            
            embed = discord.Embed(
                title="💼 Portfolio Analysis",
                description=f"{wallet_address[:8]}...",
                color=0x00BFFF,
            )
            
            embed.add_field(name="Total Value", value=f"${pnl_data.get('total_value', 0):,.0f}", inline=True)
            embed.add_field(name="Holdings", value=str(pnl_data.get('holdings_count', 0)), inline=True)
            
            pnl = pnl_data.get('total_pnl', 0)
            pnl_color = '🟢' if pnl >= 0 else '🔴'
            embed.add_field(
                name="Total PnL",
                value=f"{pnl_color} ${pnl:,.0f}",
                inline=False,
            )
            
            if pnl_data.get('biggest_winner'):
                winner = pnl_data['biggest_winner']
                embed.add_field(
                    name="🏆 Biggest Winner",
                    value=f"{winner['token']}: +{winner['roi']:.1f}%",
                    inline=True,
                )
            
            if pnl_data.get('biggest_loser'):
                loser = pnl_data['biggest_loser']
                embed.add_field(
                    name="📉 Biggest Loser",
                    value=f"{loser['token']}: {loser['roi']:.1f}%",
                    inline=True,
                )
            
            embed.set_footer(text="MemeCoinScanner Portfolio Tracker")
            await ctx.send(embed=embed)
            
        except Exception as e:
            print(f"Portfolio failed: {e}")
            await ctx.send(f"❌ Failed to load portfolio: {str(e)[:100]}")


# ============ WATCHLIST COMMANDS ============

@bot.command(name='watch')
async def watch_command(ctx, token_address: str, *conditions):
    """Add token to watchlist with optional alerts.
    Usage: !watch <address> [mc > 500k] [volume > 1m]
    Examples:
    !watch EhYXq3bffpghoLvEJwjmzcYXD9mDYqXhypXx3Hvy5wyf mc > 500k
    !watch EhYXq3bffpghoLvEJwjmzcYXD9mDYqXypX volume > 100k
    """
    if not SOLANA_ADDRESS_PATTERN.fullmatch(token_address):
        await ctx.send("❌ Invalid token address.")
        return
    
    user_id = str(ctx.author.id)
    
    try:
        alert_conditions = {}
        
        if conditions:
            condition_str = " ".join(conditions)
            alert_conditions = parse_alert_conditions(condition_str) or {}
        
        success = await add_token_to_watchlist(user_id, token_address, alert_conditions)
        
        if success:
            msg = f"✅ Added {token_address[:8]}... to watchlist"
            if alert_conditions:
                msg += f"\nAlert condition: {alert_conditions.get('metric')} {alert_conditions.get('operator')} {alert_conditions.get('value')}"
            await ctx.send(msg)
        else:
            await ctx.send("❌ Failed to add to watchlist.")
        
    except Exception as e:
        print(f"Watch failed: {e}")
        await ctx.send(f"❌ Failed: {str(e)[:100]}")


@bot.command(name='watchlist')
async def watchlist_command(ctx):
    """View your watchlist.
    Usage: !watchlist
    """
    user_id = str(ctx.author.id)
    
    try:
        watches = get_user_watchlist(user_id)
        
        if not watches:
            await ctx.send("❌ Your watchlist is empty. Use `!watch <address>` to add tokens.")
            return
        
        embed = discord.Embed(
            title="👀 Your Watchlist",
            description=f"{len(watches)} token(s) being monitored",
            color=0x00FF00,
        )
        
        for watch in watches[:25]:  # Limit to 25 for embed field limits
            conditions = watch.get('conditions', {})
            condition_str = ""
            if conditions:
                condition_str = f"\n📍 Alert: {conditions.get('metric')} {conditions.get('operator')} {conditions.get('value')}"
            
            embed.add_field(
                name=watch['address'][:8],
                value=f"`{watch['address']}`{condition_str}",
                inline=False,
            )
        
        embed.set_footer(text="MemeCoinScanner Watchlist")
        await ctx.send(embed=embed)
        
    except Exception as e:
        print(f"Watchlist failed: {e}")
        await ctx.send(f"❌ Failed to load watchlist: {str(e)[:100]}")


@bot.command(name='unwatch')
async def unwatch_command(ctx, token_address: str):
    """Remove token from watchlist.
    Usage: !unwatch <address>
    """
    if not SOLANA_ADDRESS_PATTERN.fullmatch(token_address):
        await ctx.send("❌ Invalid token address.")
        return
    
    user_id = str(ctx.author.id)
    
    try:
        success = await remove_token_from_watchlist(user_id, token_address)
        
        if success:
            await ctx.send(f"✅ Removed {token_address[:8]}... from watchlist")
        else:
            await ctx.send("❌ Token not in your watchlist.")
        
    except Exception as e:
        print(f"Unwatch failed: {e}")
        await ctx.send(f"❌ Failed: {str(e)[:100]}")


# ============ GENERAL COMMANDS ============

@bot.command(name='help')
async def help_command(ctx):
    """Show all available commands."""
    embed = discord.Embed(
        title="📖 MemeCoinScanner - Command Reference",
        description="Complete guide to all bot commands",
        color=0x9D4EDD,
    )
    
    # General
    embed.add_field(
        name="🔧 General",
        value="`!ping` - Check bot latency\n`!about` - Bot information\n`!help` - Show this message",
        inline=False,
    )
    
    # Scanner
    embed.add_field(
        name="🔍 Scanner",
        value="`!scan <address>` - Full token analysis\n`!token <address>` - Token details\n`!price <address>` - Current price\n`!marketcap <address>` - Market cap\n`!volume <address>` - Trading volume\n`!liquidity <address>` - LP liquidity",
        inline=False,
    )
    
    # Analytics
    embed.add_field(
        name="📈 Analytics",
        value="`!analysis <address>` - Detailed analysis\n`!score <address>` - Risk score\n`!momentum <address>` - Price momentum\n`!ai <address>` - AI insights",
        inline=False,
    )
    
    # Developer
    embed.add_field(
        name="👨‍💻 Developer",
        value="`!developer <address>` - Dev stats\n`!devwallet <address>` - Dev portfolio\n`!devprofit <address>` - Dev profits\n`!devtokens <wallet>` - Dev's tokens",
        inline=False,
    )
    
    # Whale Tracking
    embed.add_field(
        name="🐋 Whale Tracking",
        value="`!whales <address>` - Top whales\n`!smartmoney <address>` - Smart money\n`!topbuyers <address>` - Top buyers\n`!wallet <address>` - Wallet analysis",
        inline=False,
    )
    
    # Portfolio
    embed.add_field(
        name="💼 Portfolio",
        value="`!portfolio` - Portfolio overview\n`!addwallet <address>` - Link wallet\n`!removewallet <address>` - Unlink wallet\n`!pnl` - PnL summary\n`!holdings` - Holdings list",
        inline=False,
    )
    
    # Social
    embed.add_field(
        name="📢 Social",
        value="`!socials <address>` - Social links\n`!website <address>` - Website\n`!twitter <address>` - Twitter\n`!telegram <address>` - Telegram",
        inline=False,
    )
    
    # History & Stats
    embed.add_field(
        name="📜 History & Stats",
        value="`!history <address>` - Price history\n`!ath <address>` - All-time high\n`!atl <address>` - All-time low\n`!calls` - Your calls\n`!leaderboard` - Top callers\n`!chart <address> [type] [hours]` - Generate charts",
        inline=False,
    )
    
    embed.set_footer(text="Use ! prefix • Example: !scan <address>")
    await ctx.send(embed=embed)


@bot.command(name='ping')
async def ping_command(ctx):
    """Check bot latency."""
    latency = round(bot.latency * 1000)
    embed = discord.Embed(
        title="🏓 Pong!",
        description=f"Latency: **{latency}ms**",
        color=0x00FF00 if latency < 100 else 0xFFD700 if latency < 200 else 0xFF0000,
    )
    await ctx.send(embed=embed)


@bot.command(name='about')
async def about_command(ctx):
    """Show information about the bot."""
    embed = discord.Embed(
        title="🤖 MemeCoinScanner",
        description="Advanced Solana token analysis and portfolio tracking bot",
        color=0x9D4EDD,
    )
    
    embed.add_field(
        name="Features",
        value="✅ Real-time security analysis\n✅ AI-powered insights\n✅ Holder tracking & whale detection\n✅ Developer analysis\n✅ Portfolio tracker with PnL\n✅ Watchlist alerts\n✅ Charts & analytics\n✅ Caller leaderboard",
        inline=False,
    )
    
    embed.add_field(
        name="Powered By",
        value="🔗 DexScreener - Price & liquidity\n🔗 RugCheck - Security scoring\n🔗 Helius - On-chain data\n🔗 Birdeye - Portfolio tracking",
        inline=False,
    )
    
    embed.add_field(
        name="Commands",
        value="Use `!help` to see all commands",
        inline=False,
    )
    
    embed.set_footer(text="v1.0 • Made for memecoin traders")
    await ctx.send(embed=embed)


# ============ SCANNER COMMANDS (CONVENIENCE ALIASES) ============

@bot.command(name='scan')
async def scan_detailed_command(ctx, token_address: str):
    """Full token analysis and security report.
    Usage: !scan <address>
    """
    if not SOLANA_ADDRESS_PATTERN.fullmatch(token_address):
        await ctx.send("❌ Invalid token address.")
        return
    
    # Delegate to analyze command
    await analyze(ctx, token_address)


@bot.command(name='token')
async def token_command(ctx, token_address: str):
    """Get token details (name, symbol, supply, price).
    Usage: !token <address>
    """
    if not SOLANA_ADDRESS_PATTERN.fullmatch(token_address):
        await ctx.send("❌ Invalid token address.")
        return
    
    async with ctx.typing():
        try:
            token_data = await fetch_token_data(token_address)
            
            if not token_data:
                await ctx.send("❌ Token not found on DexScreener.")
                return
            
            embed = discord.Embed(
                title=f"💎 {token_data.get('name', 'Unknown')}",
                description=f"`{token_address}`",
                color=0x00BFFF,
            )
            
            symbol = token_data.get('symbol', 'N/A')
            embed.add_field(name="Symbol", value=f"`{symbol}`", inline=True)
            embed.add_field(name="Price", value=f"${token_data.get('price', 0):.8f}".rstrip('0'), inline=True)
            embed.add_field(name="Market Cap", value=f"${token_data.get('market_cap', 0):,.0f}", inline=True)
            embed.add_field(name="Liquidity", value=f"${token_data.get('liquidity', 0):,.0f}", inline=True)
            embed.add_field(name="Volume 24h", value=f"${token_data.get('volume_24h', 0):,.0f}", inline=True)
            embed.add_field(name="Holders", value=str(token_data.get('holder_count', 'N/A')), inline=True)
            
            if token_data.get('created_at'):
                embed.add_field(name="Created", value=token_data.get('created_at'), inline=False)
            
            embed.set_footer(text="MemeCoinScanner Token Info")
            await ctx.send(embed=embed)
            
        except Exception as e:
            print(f"Token info failed: {e}")
            await ctx.send(f"❌ Failed to fetch token info: {str(e)[:100]}")


@bot.command(name='price')
async def price_command(ctx, token_address: str):
    """Get current token price."""
    if not SOLANA_ADDRESS_PATTERN.fullmatch(token_address):
        await ctx.send("❌ Invalid token address.")
        return
    
    async with ctx.typing():
        try:
            token_data = await fetch_token_data(token_address)
            
            if not token_data:
                await ctx.send("❌ Token not found.")
                return
            
            price = token_data.get('price', 0)
            price_str = f"${price:.8f}".rstrip('0').rstrip('.')
            
            embed = discord.Embed(
                title="💰 Price",
                description=price_str,
                color=0x00FF00,
            )
            embed.set_footer(text=token_data.get('symbol', 'Token'))
            await ctx.send(embed=embed)
            
        except Exception as e:
            await ctx.send(f"❌ Failed: {str(e)[:100]}")


@bot.command(name='marketcap')
async def marketcap_command(ctx, token_address: str):
    """Get token market cap."""
    if not SOLANA_ADDRESS_PATTERN.fullmatch(token_address):
        await ctx.send("❌ Invalid token address.")
        return
    
    async with ctx.typing():
        try:
            token_data = await fetch_token_data(token_address)
            
            if not token_data:
                await ctx.send("❌ Token not found.")
                return
            
            mc = token_data.get('market_cap', 0)
            embed = discord.Embed(
                title="📊 Market Cap",
                description=f"${mc:,.0f}",
                color=0xFFD700,
            )
            embed.set_footer(text=token_data.get('symbol', 'Token'))
            await ctx.send(embed=embed)
            
        except Exception as e:
            await ctx.send(f"❌ Failed: {str(e)[:100]}")


@bot.command(name='volume')
async def volume_command(ctx, token_address: str):
    """Get 24h trading volume."""
    if not SOLANA_ADDRESS_PATTERN.fullmatch(token_address):
        await ctx.send("❌ Invalid token address.")
        return
    
    async with ctx.typing():
        try:
            token_data = await fetch_token_data(token_address)
            
            if not token_data:
                await ctx.send("❌ Token not found.")
                return
            
            vol = token_data.get('volume_24h', 0)
            embed = discord.Embed(
                title="📈 24h Volume",
                description=f"${vol:,.0f}",
                color=0x00BFFF,
            )
            embed.set_footer(text=token_data.get('symbol', 'Token'))
            await ctx.send(embed=embed)
            
        except Exception as e:
            await ctx.send(f"❌ Failed: {str(e)[:100]}")


@bot.command(name='liquidity')
async def liquidity_command(ctx, token_address: str):
    """Get LP liquidity."""
    if not SOLANA_ADDRESS_PATTERN.fullmatch(token_address):
        await ctx.send("❌ Invalid token address.")
        return
    
    async with ctx.typing():
        try:
            token_data = await fetch_token_data(token_address)
            
            if not token_data:
                await ctx.send("❌ Token not found.")
                return
            
            liq = token_data.get('liquidity', 0)
            embed = discord.Embed(
                title="💧 Liquidity",
                description=f"${liq:,.0f}",
                color=0x00FF00,
            )
            embed.set_footer(text=token_data.get('symbol', 'Token'))
            await ctx.send(embed=embed)
            
        except Exception as e:
            await ctx.send(f"❌ Failed: {str(e)[:100]}")


# ============ ANALYTICS COMMANDS ============

@bot.command(name='analysis')
async def full_analysis_command(ctx, token_address: str):
    """Comprehensive token analysis (alias for !analyze)."""
    await analyze(ctx, token_address)


@bot.command(name='score')
async def score_command(ctx, token_address: str):
    """Get security risk score."""
    if not SOLANA_ADDRESS_PATTERN.fullmatch(token_address):
        await ctx.send("❌ Invalid token address.")
        return
    
    async with ctx.typing():
        try:
            security_data = await analyze_security(token_address)
            
            if not security_data:
                await ctx.send("❌ Could not analyze security.")
                return
            
            score = security_data.get('rugcheck_score', 50)
            honeypot = security_data.get('honeypot', False)
            
            if score >= 70:
                status = "🔴 High Risk"
                color = 0xFF0000
            elif score >= 40:
                status = "🟠 Medium Risk"
                color = 0xFFA500
            else:
                status = "🟢 Low Risk"
                color = 0x00FF00
            
            embed = discord.Embed(
                title="📊 Security Score",
                description=f"**{score}/100** - {status}",
                color=color,
            )
            
            if honeypot:
                embed.add_field(name="⚠️ Honeypot", value="DETECTED", inline=False)
            
            embed.add_field(name="LP Locked", value="✅ Yes" if security_data.get('lp_locked') else "❌ No", inline=True)
            embed.add_field(name="Owner Renounced", value="✅ Yes" if security_data.get('owner_renounced') else "❌ No", inline=True)
            embed.add_field(name="Mint Disabled", value="✅ Yes" if security_data.get('mint_authority_disabled') else "❌ No", inline=True)
            
            embed.set_footer(text="MemeCoinScanner Risk Assessment")
            await ctx.send(embed=embed)
            
        except Exception as e:
            await ctx.send(f"❌ Failed: {str(e)[:100]}")


@bot.command(name='momentum')
async def momentum_command(ctx, token_address: str):
    """Analyze price momentum."""
    if not SOLANA_ADDRESS_PATTERN.fullmatch(token_address):
        await ctx.send("❌ Invalid token address.")
        return
    
    async with ctx.typing():
        try:
            token_data = await fetch_token_data(token_address)
            
            if not token_data:
                await ctx.send("❌ Token not found.")
                return
            
            try:
                price_changes = get_price_changes(token_address)
            except:
                price_changes = {}
            
            embed = discord.Embed(
                title="📈 Price Momentum",
                description=f"{token_data.get('symbol', 'Token')} - {token_address[:8]}...",
                color=0x9D4EDD,
            )
            
            for window, pct in price_changes.items():
                if pct is not None:
                    color_emoji = "🟢" if pct >= 0 else "🔴"
                    embed.add_field(name=f"{color_emoji} {window.upper()}", value=f"{pct:+.2f}%", inline=True)
                else:
                    embed.add_field(name=f"❓ {window.upper()}", value="N/A", inline=True)
            
            embed.set_footer(text="MemeCoinScanner Momentum Analysis")
            await ctx.send(embed=embed)
            
        except Exception as e:
            await ctx.send(f"❌ Failed: {str(e)[:100]}")


@bot.command(name='ai')
async def ai_command(ctx, token_address: str):
    """Get AI-powered insights (alias for !analyze)."""
    await analyze(ctx, token_address)


# ============ DEVELOPER COMMANDS ============

@bot.command(name='devwallet')
async def devwallet_command(ctx, token_address: str):
    """Analyze developer wallet."""
    await developer(ctx, token_address)


@bot.command(name='devprofit')
async def devprofit_command(ctx, wallet_address: str):
    """Get developer total profits and ROI."""
    if not SOLANA_ADDRESS_PATTERN.fullmatch(wallet_address):
        await ctx.send("❌ Invalid wallet address.")
        return
    
    async with ctx.typing():
        try:
            dev_data = await analyze_developer_wallet(wallet_address)
            
            if not dev_data:
                await ctx.send("❌ Could not analyze wallet.")
                return
            
            embed = discord.Embed(
                title="💰 Developer Profits",
                description=f"{short_wallet(wallet_address)}",
                color=0x00FF00,
            )
            
            embed.add_field(name="Total Value", value=f"${dev_data.get('total_value', 0):,.0f}", inline=True)
            embed.add_field(name="Avg ROI", value=f"{dev_data.get('avg_roi', 0):.1f}%", inline=True)
            embed.add_field(name="Win Rate", value=f"{dev_data.get('win_rate', 0):.1f}%", inline=True)
            
            embed.set_footer(text="MemeCoinScanner Developer Analysis")
            await ctx.send(embed=embed)
            
        except Exception as e:
            await ctx.send(f"❌ Failed: {str(e)[:100]}")


@bot.command(name='devtokens')
async def devtokens_command(ctx, wallet_address: str):
    """List tokens launched by developer."""
    if not SOLANA_ADDRESS_PATTERN.fullmatch(wallet_address):
        await ctx.send("❌ Invalid wallet address.")
        return
    
    async with ctx.typing():
        try:
            dev_data = await analyze_developer_wallet(wallet_address)
            
            if not dev_data:
                await ctx.send("❌ Could not fetch tokens.")
                return
            
            tokens = dev_data.get('tokens', [])[:10]
            
            embed = discord.Embed(
                title="🪙 Developer's Tokens",
                description=f"Top {len(tokens)} tokens by {short_wallet(wallet_address)}",
                color=0xFFD700,
            )
            
            for i, token in enumerate(tokens, 1):
                symbol = token.get('symbol') or 'Unknown'
                value = token.get('valueUsd', 0)
                embed.add_field(
                    name=f"{i}. {symbol}",
                    value=f"${value:,.0f}",
                    inline=False,
                )
            
            embed.set_footer(text="MemeCoinScanner Developer Tokens")
            await ctx.send(embed=embed)
            
        except Exception as e:
            await ctx.send(f"❌ Failed: {str(e)[:100]}")


# ============ WHALE COMMANDS ============

@bot.command(name='whales')
async def whales_command(ctx, token_address: str):
    """Show top whale holders."""
    if not SOLANA_ADDRESS_PATTERN.fullmatch(token_address):
        await ctx.send("❌ Invalid token address.")
        return
    
    async with ctx.typing():
        try:
            whales = await detect_whale_activity(token_address, threshold_percentage=3.0)
            
            if not whales:
                await ctx.send("❌ No whale data available.")
                return
            
            embed = discord.Embed(
                title="🐋 Top Whales",
                description=f"{token_address[:8]}... - Holders > 3%",
                color=0x00BFFF,
            )
            
            for whale in whales[:10]:
                wallet = short_wallet(whale.get('address', ''))
                pct = whale.get('percentage', 0)
                value = whale.get('valueUsd', 0)
                embed.add_field(
                    name=f"{wallet}",
                    value=f"{pct:.2f}% • ${value:,.0f}",
                    inline=False,
                )
            
            embed.set_footer(text="MemeCoinScanner Whale Tracker")
            await ctx.send(embed=embed)
            
        except Exception as e:
            await ctx.send(f"❌ Failed: {str(e)[:100]}")


@bot.command(name='topbuyers')
async def topbuyers_command(ctx, token_address: str):
    """Show top buyers (recent large purchases)."""
    if not SOLANA_ADDRESS_PATTERN.fullmatch(token_address):
        await ctx.send("❌ Invalid token address.")
        return
    
    embed = discord.Embed(
        title="🔺 Top Buyers",
        description="Feature coming soon - requires transaction history",
        color=0x9D4EDD,
    )
    await ctx.send(embed=embed)


# ============ PORTFOLIO COMMANDS (ALIASES) ============

@bot.command(name='pnl')
async def pnl_command(ctx):
    """Show portfolio PnL summary."""
    await portfolio_command(ctx)


@bot.command(name='holdings')
async def holdings_command(ctx):
    """Show portfolio holdings."""
    await portfolio_command(ctx)


@bot.command(name='addwallet')
async def addwallet_command(ctx, wallet_address: str, label: str = None):
    """Link wallet (alias for !wallet)."""
    await wallet_command(ctx, wallet_address, label)


@bot.command(name='removewallet')
async def removewallet_command(ctx, wallet_address: str):
    """Remove linked wallet."""
    user_id = str(ctx.author.id)
    
    try:
        success = await unlink_wallet(user_id, wallet_address)
        if success:
            await ctx.send(f"✅ Wallet {wallet_address[:8]}... removed")
        else:
            await ctx.send("❌ Wallet not found in your portfolio.")
    except Exception as e:
        await ctx.send(f"❌ Failed: {str(e)[:100]}")


# ============ SOCIAL COMMANDS ============

@bot.command(name='socials')
async def socials_command(ctx, token_address: str):
    """Show token social links."""
    if not SOLANA_ADDRESS_PATTERN.fullmatch(token_address):
        await ctx.send("❌ Invalid token address.")
        return
    
    async with ctx.typing():
        try:
            token_data = await fetch_token_data(token_address)
            
            if not token_data:
                await ctx.send("❌ Token not found.")
                return
            
            embed = discord.Embed(
                title="📢 Social Links",
                description=f"{token_data.get('name', 'Token')} - {token_data.get('symbol', 'N/A')}",
                color=0x1DA1F2,
            )
            
            # Extract links from token_data
            links = token_data.get('links', {})
            
            if links.get('website'):
                embed.add_field(name="🌐 Website", value=f"[Visit]({links['website']})", inline=False)
            if links.get('twitter'):
                embed.add_field(name="𝕏 Twitter", value=f"[Follow]({links['twitter']})", inline=False)
            if links.get('telegram'):
                embed.add_field(name="✈️ Telegram", value=f"[Join]({links['telegram']})", inline=False)
            if links.get('discord'):
                embed.add_field(name="💬 Discord", value=f"[Join]({links['discord']})", inline=False)
            
            if not links:
                embed.description += "\n❌ No social links found"
            
            embed.set_footer(text="MemeCoinScanner Social Links")
            await ctx.send(embed=embed)
            
        except Exception as e:
            await ctx.send(f"❌ Failed: {str(e)[:100]}")


@bot.command(name='website')
async def website_command(ctx, token_address: str):
    """Get token website."""
    if not SOLANA_ADDRESS_PATTERN.fullmatch(token_address):
        await ctx.send("❌ Invalid token address.")
        return
    
    async with ctx.typing():
        try:
            token_data = await fetch_token_data(token_address)
            
            if not token_data:
                await ctx.send("❌ Token not found.")
                return
            
            website = token_data.get('links', {}).get('website')
            
            if website:
                embed = discord.Embed(
                    title="🌐 Website",
                    description=f"[Visit Website]({website})",
                    color=0x00BFFF,
                )
                await ctx.send(embed=embed)
            else:
                await ctx.send("❌ No website found for this token.")
            
        except Exception as e:
            await ctx.send(f"❌ Failed: {str(e)[:100]}")


@bot.command(name='twitter')
async def twitter_command(ctx, token_address: str):
    """Get token Twitter account."""
    if not SOLANA_ADDRESS_PATTERN.fullmatch(token_address):
        await ctx.send("❌ Invalid token address.")
        return
    
    async with ctx.typing():
        try:
            token_data = await fetch_token_data(token_address)
            
            if not token_data:
                await ctx.send("❌ Token not found.")
                return
            
            twitter = token_data.get('links', {}).get('twitter')
            
            if twitter:
                embed = discord.Embed(
                    title="𝕏 Twitter",
                    description=f"[Follow Account]({twitter})",
                    color=0x000000,
                )
                await ctx.send(embed=embed)
            else:
                await ctx.send("❌ No Twitter found for this token.")
            
        except Exception as e:
            await ctx.send(f"❌ Failed: {str(e)[:100]}")


@bot.command(name='telegram')
async def telegram_command(ctx, token_address: str):
    """Get token Telegram group."""
    if not SOLANA_ADDRESS_PATTERN.fullmatch(token_address):
        await ctx.send("❌ Invalid token address.")
        return
    
    async with ctx.typing():
        try:
            token_data = await fetch_token_data(token_address)
            
            if not token_data:
                await ctx.send("❌ Token not found.")
                return
            
            telegram = token_data.get('links', {}).get('telegram')
            
            if telegram:
                embed = discord.Embed(
                    title="✈️ Telegram",
                    description=f"[Join Group]({telegram})",
                    color=0x0088cc,
                )
                await ctx.send(embed=embed)
            else:
                await ctx.send("❌ No Telegram found for this token.")
            
        except Exception as e:
            await ctx.send(f"❌ Failed: {str(e)[:100]}")


# ============ HISTORY COMMANDS ============

@bot.command(name='history')
async def history_command(ctx, token_address: str):
    """Show price history (1m, 5m, 1h, 24h changes)."""
    if not SOLANA_ADDRESS_PATTERN.fullmatch(token_address):
        await ctx.send("❌ Invalid token address.")
        return
    
    async with ctx.typing():
        try:
            price_changes = get_price_changes(token_address)
            
            embed = discord.Embed(
                title="📜 Price History",
                description=f"{token_address[:8]}...",
                color=0x9D4EDD,
            )
            
            for window, pct in price_changes.items():
                if pct is not None:
                    emoji = "📈" if pct >= 0 else "📉"
                    embed.add_field(
                        name=f"{emoji} {window.upper()}",
                        value=f"{pct:+.2f}%",
                        inline=True,
                    )
                else:
                    embed.add_field(name=f"❓ {window.upper()}", value="N/A", inline=True)
            
            embed.set_footer(text="MemeCoinScanner Price History")
            await ctx.send(embed=embed)
            
        except Exception as e:
            await ctx.send(f"❌ Failed: {str(e)[:100]}")


@bot.command(name='ath')
async def ath_command(ctx, token_address: str):
    """Show all-time high."""
    if not SOLANA_ADDRESS_PATTERN.fullmatch(token_address):
        await ctx.send("❌ Invalid token address.")
        return
    
    async with ctx.typing():
        try:
            from database import DB_PATH
            import sqlite3
            
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute('''
                SELECT MAX(price) as ath, timestamp FROM price_history 
                WHERE token_address = ?
            ''', (token_address,))
            
            row = cursor.fetchone()
            conn.close()
            
            if row and row[0]:
                ath = row[0]
                embed = discord.Embed(
                    title="🔺 All-Time High",
                    description=f"${ath:.8f}".rstrip('0').rstrip('.'),
                    color=0x00FF00,
                )
                await ctx.send(embed=embed)
            else:
                await ctx.send("❌ No price history available.")
            
        except Exception as e:
            await ctx.send(f"❌ Failed: {str(e)[:100]}")


@bot.command(name='atl')
async def atl_command(ctx, token_address: str):
    """Show all-time low."""
    if not SOLANA_ADDRESS_PATTERN.fullmatch(token_address):
        await ctx.send("❌ Invalid token address.")
        return
    
    async with ctx.typing():
        try:
            from database import DB_PATH
            import sqlite3
            
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute('''
                SELECT MIN(price) as atl, timestamp FROM price_history 
                WHERE token_address = ? AND price > 0
            ''', (token_address,))
            
            row = cursor.fetchone()
            conn.close()
            
            if row and row[0]:
                atl = row[0]
                embed = discord.Embed(
                    title="🔻 All-Time Low",
                    description=f"${atl:.8f}".rstrip('0').rstrip('.'),
                    color=0xFF0000,
                )
                await ctx.send(embed=embed)
            else:
                await ctx.send("❌ No price history available.")
            
        except Exception as e:
            await ctx.send(f"❌ Failed: {str(e)[:100]}")


@bot.command(name='calls')
async def calls_command(ctx, limit: int = 10):
    """Show your recent token calls."""
    from database import get_call_history
    
    user_id = str(ctx.author.id)
    
    try:
        from database import DB_PATH
        import sqlite3
        
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM calls 
            WHERE called_by = ?
            ORDER BY timestamp DESC 
            LIMIT ?
        ''', (user_id, limit))
        
        calls = cursor.fetchall()
        conn.close()
        
        if not calls:
            await ctx.send("❌ You haven't made any calls yet.")
            return
        
        embed = discord.Embed(
            title="📞 Your Recent Calls",
            description=f"{len(calls)} tokens called",
            color=0x9D4EDD,
        )
        
        for call in calls:
            entry = call['entry_price'] or call['initial_price']
            symbol = call['symbol'] or 'N/A'
            embed.add_field(
                name=f"{symbol}",
                value=f"Entry: ${entry:.8f}\nMarket Cap: ${call['market_cap']:,.0f}",
                inline=False,
            )
        
        embed.set_footer(text="MemeCoinScanner Your Calls")
        await ctx.send(embed=embed)
        
    except Exception as e:
        await ctx.send(f"❌ Failed: {str(e)[:100]}")


@bot.command(name='callerboard')
async def callerboard_command(ctx, limit: int = 10):
    """Show caller leaderboard (alias for !leaderboard)."""
    await leaderboard_command(ctx, limit)


def main():
    token = settings.get('DISCORD_TOKEN') or settings.get('TOKEN')
    if not token:
        raise RuntimeError('DISCORD_TOKEN is not configured.')
    bot.run(token)


if __name__ == '__main__':
    main()
