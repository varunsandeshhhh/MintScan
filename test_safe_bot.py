import asyncio
from contextlib import asynccontextmanager
import discord
from discord.ext import commands
from unittest.mock import AsyncMock

import bot as bot_module
from bot import SafeBot


class DummyContext:
    def __init__(self, command):
        self.command = command
        self.sent_messages = []
        self.bot = None
        self.message = type('Message', (), {'content': '', 'attachments': [], 'embeds': [], 'reference': None})()
        self.channel = type('Channel', (), {'send': None})()
        self.guild = None
        self.author = None
        self.args = []
        self.kwargs = {}
        self.view = None
        self.cog = None
        self.invoked_parents = []
        self.invoked_with = None
        self.subcommand_passed = None
        self.command_failed = False

    async def send(self, content=None, embed=None):
        self.sent_messages.append((content, embed))

    async def reply(self, content=None, embed=None):
        await self.send(content=content, embed=embed)


async def _run_broken_command():
    bot = SafeBot(command_prefix='!', intents=discord.Intents.none())

    @bot.command(name='broken')
    async def broken(ctx):
        raise RuntimeError('boom')

    ctx = DummyContext(bot.get_command('broken'))
    ctx.bot = bot
    await bot.invoke_command(ctx)
    return ctx.sent_messages


async def _run_duplicate_send_command():
    bot = SafeBot(command_prefix='!', intents=discord.Intents.none())

    @bot.command(name='double')
    async def double(ctx):
        await ctx.send('first response')
        await ctx.send('second response')

    ctx = DummyContext(bot.get_command('double'))
    ctx.bot = bot
    await bot.invoke_command(ctx)
    return ctx.sent_messages


def test_bot_returns_placeholder_when_command_crashes():
    messages = __import__('asyncio').run(_run_broken_command())
    assert messages
    assert any('under development' in (content or '').lower() for content, _ in messages)


def test_bot_only_sends_one_response_per_command():
    messages = __import__('asyncio').run(_run_duplicate_send_command())
    assert len(messages) == 1
    assert messages[0][0] == 'first response'


async def _run_alpha_with_missing_data():
    ctx = DummyContext(None)
    ctx.bot = None
    bot_module.fetch_token_data = AsyncMock(return_value=None)
    bot_module.detect_whale_activity = AsyncMock(return_value=None)
    bot_module.detect_smart_money_buys = AsyncMock(return_value=None)
    bot_module.detect_sniper_wallets = AsyncMock(return_value=None)
    await bot_module.alpha_command(ctx, 'token_address')
    return ctx.sent_messages


async def _run_dev_with_missing_data():
    ctx = DummyContext(None)
    ctx.bot = None
    bot_module.analyze_developer_wallet = AsyncMock(return_value=None)
    await bot_module.dev_command(ctx, 'wallet_address')
    return ctx.sent_messages


def test_alpha_command_returns_embed_when_data_missing():
    messages = __import__('asyncio').run(_run_alpha_with_missing_data())
    assert messages
    assert any(embed is not None for _, embed in messages)


def test_dev_command_returns_embed_when_data_missing():
    messages = __import__('asyncio').run(_run_dev_with_missing_data())
    assert messages
    assert any(embed is not None for _, embed in messages)


async def _run_address_message_once():
    class DummyChannel:
        def __init__(self):
            self.sent_messages = []

        def typing(self):
            @asynccontextmanager
            async def _typing():
                yield
            return _typing()

        async def send(self, *args, **kwargs):
            self.sent_messages.append((args, kwargs))

    class DummyMessage:
        def __init__(self, channel):
            self.channel = channel
            self.author = type('Author', (), {'bot': False})()
            self.content = '6b4MSJrpopLBTdSMnEwWAo1FwYWWkKUHuAd3c1CZpump'
            self.replies = []

        async def reply(self, *args, **kwargs):
            self.replies.append((args, kwargs))

    channel = DummyChannel()
    message = DummyMessage(channel)
    bot_module.fetch_token_data = AsyncMock(return_value={'price': 1, 'market_cap': 2, 'symbol': 'TEST'})
    bot_module.fetch_risk_data = AsyncMock(return_value=None)
    bot_module.get_price_changes = lambda *_args, **_kwargs: {}
    bot_module.analyze_security = AsyncMock(return_value=None)
    bot_module.is_blacklisted = lambda *_args, **_kwargs: None
    bot_module.build_large_token_embed = lambda *args, **kwargs: object()
    bot_module.create_button_view = lambda *args, **kwargs: object()
    bot_module.bot.process_commands = AsyncMock()
    bot_module.settings = {'get': lambda *args, **kwargs: 'fake-key'}

    await bot_module.on_message(message)
    await asyncio.sleep(0)
    return message, channel


def test_address_messages_only_send_one_reply():
    message, channel = asyncio.run(_run_address_message_once())
    assert len(message.replies) == 1
    assert channel.sent_messages == []
