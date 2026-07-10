import re
import discord
from discord.ext import commands
from config import settings
from embed import build_token_embed, create_button_view
from dexscreener import fetch_token_data
from rugcheck import fetch_risk_data
from birdeye import get_token_holders, get_wallet_tokens
from developer_analysis import analyze_developer_wallet, detect_dev_movements
from holder_analysis import analyze_token_holders, detect_whale_activity
from smart_money import analyze_smart_wallet, detect_smart_money_buys
from alerts import alert_manager, create_user_alert
from database import init_database, add_call, get_call_history
import asyncio

# Initialize database
init_database()

SOLANA_ADDRESS_PATTERN = re.compile(r'\b[1-9A-HJ-NP-Za-km-z]{32,44}\b')

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix=settings['PREFIX'], intents=intents)

# Store token data for monitoring
monitored_tokens = {}


@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    print(f"🔍 Listening for Solana token addresses...")
    print(f"📊 Database initialized")


@bot.event
async def on_message(message):
    if message.author.bot:
        return

    content = message.content.strip()
    print(f"[{message.author}] {content}")
    
    # Check if message contains a Solana address
    if SOLANA_ADDRESS_PATTERN.fullmatch(content):
        async with message.channel.typing():
            try:
                # Fetch token data from DexScreener
                token_data = await fetch_token_data(content)
                
                if token_data:
                    # Add to call history
                    add_call(
                        token_address=content,
                        token_name=token_data.get('name', 'Unknown'),
                        symbol=token_data.get('symbol', 'N/A'),
                        price=token_data.get('price', 0),
                        called_by=str(message.author)
                    )
                    
                    # Fetch risk data
                    risk_data = await fetch_risk_data(content)
                    
                    # Fetch holder analysis
                    holder_analysis = await analyze_token_holders(content, limit=30)
                    
                    # Build embed with core data
                    embed = build_token_embed(token_data, risk_data)
                    
                    # Add holder risk info if available
                    if holder_analysis:
                        concentration_risk = holder_analysis.get('concentration_risk', 'UNKNOWN')
                        top_10_pct = holder_analysis.get('top_10_percentage', 0)
                        embed.add_field(
                            name="🎯 Holder Concentration",
                            value=f"Top 10: {top_10_pct:.1f}% ({concentration_risk} RISK)",
                            inline=True
                        )
                        
                        # Trigger holder concentration alert
                        await alert_manager.check_holder_concentration_alert(content, top_10_pct)
                    
                    # Add volume info
                    volume_24h = token_data.get('volume_24h', 0)
                    if volume_24h:
                        embed.add_field(
                            name="📈 24h Volume",
                            value=f"${volume_24h:,.0f}",
                            inline=True
                        )
                        await alert_manager.check_volume_alert(content, volume_24h)
                    
                    # Create buttons
                    view = create_button_view(token_data)
                    
                    # Send main embed
                    await message.reply(embed=embed, view=view)
                    
                    # Send additional analysis if Birdeye API is available
                    if settings.get('BIRDEYE_API_KEY'):
                        analysis_task = asyncio.create_task(
                            send_additional_analysis(message, content, holder_analysis)
                        )
                    
                else:
                    await message.reply("❌ Token not found on DexScreener. Make sure it's a valid Solana token.")
                    
            except Exception as e:
                print(f"Error analyzing token: {e}")
                await message.reply(f"❌ Error analyzing token: {str(e)[:100]}")

    await bot.process_commands(message)


async def send_additional_analysis(message, token_address: str, holder_analysis):
    """Send additional analysis in a follow-up message."""
    try:
        # Detect whale activity
        whales = await detect_whale_activity(token_address, threshold_percentage=5.0)
        
        if whales:
            whale_embed = discord.Embed(
                title="🐋 Whale Detected",
                description=f"Found {len(whales)} wallet(s) holding >5% of supply",
                color=0xFFA500
            )
            
            for whale in whales[:5]:
                percentage = whale.get('percentage', 0)
                whale_embed.add_field(
                    name=f"Wallet {whale.get('address', '')[:8]}...",
                    value=f"{percentage:.2f}% of supply",
                    inline=False
                )
            
            await message.channel.send(embed=whale_embed)
            
            # Trigger alert
            await alert_manager.check_whale_deposit_alert(token_address, whales)
    
    except Exception as e:
        print(f"Error sending additional analysis: {e}")


@bot.command(name='scan')
async def scan(ctx):
    """Send a token address to scan it."""
    await ctx.send('🔍 Send a Solana token contract address to scan it!')


@bot.command(name='history')
async def history(ctx, limit: int = 10):
    """Get recent call history."""
    calls = get_call_history(limit)
    
    if not calls:
        await ctx.send("No call history found.")
        return
    
    embed = discord.Embed(title="📋 Call History", color=0x00FF00)
    
    for call in calls:
        symbol = call[3] if len(call) > 3 else 'N/A'
        price = call[5] if len(call) > 5 else 0
        timestamp = call[7] if len(call) > 7 else 'Unknown'
        
        embed.add_field(
            name=f"{symbol}",
            value=f"${price:.6f} • {timestamp}",
            inline=False
        )
    
    await ctx.send(embed=embed)


@bot.command(name='alerts')
async def list_alerts(ctx):
    """Show active alerts."""
    alerts = alert_manager.get_alert_history(limit=5)
    
    if not alerts:
        await ctx.send("No recent alerts.")
        return
    
    embed = discord.Embed(title="🚨 Recent Alerts", color=0xFF0000)
    
    for alert in alerts:
        alert_type = alert.get('type', 'Unknown').upper()
        timestamp = alert.get('timestamp', '')
        
        embed.add_field(
            name=alert_type,
            value=f"🕐 {timestamp}",
            inline=False
        )
    
    await ctx.send(embed=embed)


if __name__ == '__main__':
    bot.run(settings['DISCORD_TOKEN'])
