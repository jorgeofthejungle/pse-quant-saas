# ============================================================
# bot.py — Discord Slash Command Bot
# PSE Quant SaaS — Discord Bot
# ============================================================
# Run standalone:  py discord/bot.py
# Or start/stop from the Dashboard → Pipeline page.
#
# Required env var:  DISCORD_BOT_TOKEN=...
# Set in .env at project root.
#
# Slash commands:
#   /stock <ticker>  — Full stock analysis
#   /top10           — Current top 10 rankings
#   /help            — Glossary and usage guide
# ============================================================

import sys
import os
import asyncio
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / '.env')

try:
    import discord
    from discord import app_commands
except ImportError:
    print("ERROR: discord.py not installed. Run: py -m pip install discord.py")
    sys.exit(1)

from discord.bot_commands import get_stock_embed, get_top10_embed, get_help_embed

# ── Bot setup ─────────────────────────────────────────────────

intents = discord.Intents.default()
client  = discord.Client(intents=intents)
tree    = app_commands.CommandTree(client)


def _build_embed(data: dict) -> discord.Embed:
    """Converts a bot_commands embed dict to a discord.Embed object."""
    embed = discord.Embed(
        title       = data.get('title', ''),
        description = data.get('description', ''),
        color       = data.get('color', 0x95A5A6),
    )
    for field in data.get('fields', []):
        embed.add_field(
            name   = field.get('name', '\u200b'),
            value  = field.get('value', '\u200b'),
            inline = field.get('inline', False),
        )
    footer = data.get('footer', {})
    if footer:
        embed.set_footer(text=footer.get('text', ''))
    return embed


# ── Slash commands ────────────────────────────────────────────

@tree.command(name='stock', description='Show full analysis for a PSE stock (e.g. DMC, BDO, ALI)')
@app_commands.describe(ticker='Stock ticker symbol (e.g. DMC)')
async def cmd_stock(interaction: discord.Interaction, ticker: str):
    await interaction.response.defer(thinking=True)
    data = get_stock_embed(ticker)
    if 'error' in data and data['error']:
        await interaction.followup.send(f"❌ {data['error']}")
        return
    embed = _build_embed(data)
    await interaction.followup.send(embed=embed)


@tree.command(name='top10', description='Show the current top 10 PSE stock rankings')
async def cmd_top10(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True)
    discord_id = str(interaction.user.id)
    data = get_top10_embed(discord_id=discord_id)
    if 'error' in data and data['error']:
        await interaction.followup.send(f"ERROR: {data['error']}")
        return
    embed = _build_embed(data)
    await interaction.followup.send(embed=embed)


@tree.command(name='help', description='How to use StockPilot PH — commands and glossary')
async def cmd_help(interaction: discord.Interaction):
    data  = get_help_embed()
    embed = _build_embed(data)
    await interaction.response.send_message(embed=embed)


# ── Lifecycle ─────────────────────────────────────────────────

@client.event
async def on_ready():
    print(f'[StockPilot Bot] Logged in as {client.user} (ID: {client.user.id})')
    try:
        synced = await tree.sync()
        print(f'[StockPilot Bot] Synced {len(synced)} slash command(s) globally.')
        print('[StockPilot Bot] Note: Global slash commands can take up to 1 hour to appear.')
        print('[StockPilot Bot] Bot is ready. Press Ctrl+C to stop.')
    except Exception as e:
        print(f'[StockPilot Bot] Failed to sync commands: {e}')


# ── Entry point ───────────────────────────────────────────────

if __name__ == '__main__':
    token = os.getenv('DISCORD_BOT_TOKEN', '')
    if not token:
        print('ERROR: DISCORD_BOT_TOKEN not set in .env')
        print('Add DISCORD_BOT_TOKEN=your_token_here to your .env file.')
        print('Get a bot token at: https://discord.com/developers/applications')
        sys.exit(1)

    print('=' * 55)
    print('  StockPilot PH — Discord Bot')
    print('  Commands: /stock /top10 /help')
    print('  Press Ctrl+C to stop')
    print('=' * 55)

    try:
        client.run(token)
    except discord.LoginFailure:
        print('ERROR: Invalid DISCORD_BOT_TOKEN. Check your .env file.')
        sys.exit(1)
    except KeyboardInterrupt:
        print('\n[StockPilot Bot] Stopped.')
