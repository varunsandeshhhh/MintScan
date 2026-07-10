import discord
from discord.ext import commands

from bot import register_slash_commands


def test_register_slash_commands_registers_expected_commands():
    test_bot = commands.Bot(command_prefix="!", intents=discord.Intents.none())

    register_slash_commands(test_bot)

    registered_names = {command.name for command in test_bot.tree.get_commands()}
    expected_names = {"alpha", "smartmoney", "fresh", "snipers", "dev", "alerts"}

    assert expected_names <= registered_names
