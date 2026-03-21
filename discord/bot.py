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
load_dotenv(ROOT / '.env', override=False)  # Railway env vars take precedence

try:
    import discord
    from discord import app_commands
except ImportError:
    print("ERROR: discord.py not installed. Run: py -m pip install discord.py")
    sys.exit(1)

from discord.bot_commands   import get_stock_embed, get_top10_embed, get_help_embed
from discord.bot_subscribe  import get_subscribe_embed, get_mystatus_embed
from discord.bot_watchlist  import get_watchlist_embed, add_watchlist_embed, remove_watchlist_embed
from discord.bot_admin      import (get_admin_list_embed, get_admin_pending_embed,
                                    confirm_member_embed, extend_member_embed,
                                    get_member_status_embed)
from dashboard.access_control import check_access

# ── Bot setup ─────────────────────────────────────────────────

intents = discord.Intents.default()
client  = discord.Client(intents=intents)
tree    = app_commands.CommandTree(client)


async def _premium_dm_gate(interaction: discord.Interaction) -> str | None:
    """
    Returns an error message string if access is denied, None if OK.
    Rules: must be a DM (not a guild channel) AND must be a premium member.
    """
    if interaction.guild is not None:
        return (
            "This command is only available in DMs. "
            "Send me a direct message to use StockPilot commands."
        )
    discord_id = str(interaction.user.id)
    if not check_access(discord_id, 'discord_bot'):
        return (
            "This command is for **StockPilot Premium** members only (\u20B199/mo). "
            "Use `/subscribe` to get started."
        )
    return None


async def _dm_only_gate(interaction: discord.Interaction) -> str | None:
    """
    Returns an error message if used in a guild channel, None if OK.
    Used for /subscribe and /mystatus which are DM-only but free to use.
    """
    if interaction.guild is not None:
        return (
            "Please send me a direct message to use this command. "
            "Your subscription details are private."
        )
    return None


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
    err = await _premium_dm_gate(interaction)
    if err:
        await interaction.response.send_message(err, ephemeral=True)
        return
    await interaction.response.defer(thinking=True)
    discord_id = str(interaction.user.id)
    data = get_stock_embed(ticker, discord_id=discord_id)
    if 'error' in data and data['error']:
        await interaction.followup.send(f"❌ {data['error']}")
        return
    embed = _build_embed(data)
    await interaction.followup.send(embed=embed)


@tree.command(name='top10', description='Show the current top 10 PSE stock rankings')
async def cmd_top10(interaction: discord.Interaction):
    err = await _premium_dm_gate(interaction)
    if err:
        await interaction.response.send_message(err, ephemeral=True)
        return
    await interaction.response.defer(thinking=True)
    discord_id = str(interaction.user.id)
    data = get_top10_embed(discord_id=discord_id)
    if 'error' in data and data['error']:
        await interaction.followup.send(f"ERROR: {data['error']}")
        return
    embed = _build_embed(data)
    await interaction.followup.send(embed=embed)


@tree.command(name='subscribe', description='See pricing and get your StockPilot Premium payment link')
async def cmd_subscribe(interaction: discord.Interaction):
    err = await _dm_only_gate(interaction)
    if err:
        await interaction.response.send_message(err, ephemeral=True)
        return
    await interaction.response.defer(thinking=True)
    discord_id   = str(interaction.user.id)
    discord_name = str(interaction.user.display_name)
    data = get_subscribe_embed(discord_id, discord_name)
    if 'error' in data and data['error']:
        await interaction.followup.send(f"❌ {data['error']}")
        return
    embed = _build_embed(data)
    await interaction.followup.send(embed=embed)


@tree.command(name='mystatus', description='Check your StockPilot subscription tier and expiry')
async def cmd_mystatus(interaction: discord.Interaction):
    err = await _dm_only_gate(interaction)
    if err:
        await interaction.response.send_message(err, ephemeral=True)
        return
    await interaction.response.defer(thinking=True)
    discord_id = str(interaction.user.id)
    data = get_mystatus_embed(discord_id)
    if 'error' in data and data['error']:
        await interaction.followup.send(f"❌ {data['error']}")
        return
    embed = _build_embed(data)
    await interaction.followup.send(embed=embed)


# ── /watchlist command group ──────────────────────────────────

watchlist_group = app_commands.Group(
    name='watchlist',
    description='Manage your personal stock watchlist (Premium, DM only)',
)


@watchlist_group.command(name='show', description='Show your watchlist with current scores')
async def watchlist_show(interaction: discord.Interaction):
    err = await _premium_dm_gate(interaction)
    if err:
        await interaction.response.send_message(err, ephemeral=True)
        return
    await interaction.response.defer(thinking=True)
    data  = get_watchlist_embed(str(interaction.user.id))
    embed = _build_embed(data)
    await interaction.followup.send(embed=embed)


@watchlist_group.command(name='add', description='Add a stock to your watchlist (e.g. DMC)')
@app_commands.describe(ticker='Stock ticker symbol (e.g. DMC)')
async def watchlist_add(interaction: discord.Interaction, ticker: str):
    err = await _premium_dm_gate(interaction)
    if err:
        await interaction.response.send_message(err, ephemeral=True)
        return
    await interaction.response.defer(thinking=True)
    data  = add_watchlist_embed(str(interaction.user.id), ticker)
    embed = _build_embed(data)
    await interaction.followup.send(embed=embed)


@watchlist_group.command(name='remove', description='Remove a stock from your watchlist')
@app_commands.describe(ticker='Stock ticker symbol to remove (e.g. DMC)')
async def watchlist_remove(interaction: discord.Interaction, ticker: str):
    err = await _premium_dm_gate(interaction)
    if err:
        await interaction.response.send_message(err, ephemeral=True)
        return
    await interaction.response.defer(thinking=True)
    data  = remove_watchlist_embed(str(interaction.user.id), ticker)
    embed = _build_embed(data)
    await interaction.followup.send(embed=embed)


tree.add_command(watchlist_group)


# ── /admin command group (Josh only) ─────────────────────────

def _is_admin(discord_id: str) -> bool:
    admin_id = os.getenv('ADMIN_DISCORD_ID', '')
    print(f'[ADMIN CHECK] user={discord_id!r} admin_id={admin_id!r} match={discord_id == admin_id}')
    return bool(admin_id) and discord_id == admin_id


async def _admin_gate(interaction: discord.Interaction) -> str | None:
    if interaction.guild is not None:
        return 'Admin commands are DM only.'
    if not _is_admin(str(interaction.user.id)):
        return 'This command is restricted to the server admin.'
    return None


admin_group = app_commands.Group(
    name='admin',
    description='StockPilot admin commands (Josh only)',
)


@admin_group.command(name='list', description='List all active members')
async def admin_list(interaction: discord.Interaction):
    print(f'[Admin] /admin list called by {interaction.user.id}')
    err = await _admin_gate(interaction)
    if err:
        print(f'[Admin] /admin list blocked: {err}')
        await interaction.response.send_message(err, ephemeral=True)
        return
    await interaction.response.defer(thinking=True)
    try:
        data  = await asyncio.to_thread(get_admin_list_embed)
        embed = _build_embed(data)
        await interaction.followup.send(embed=embed)
        print('[Admin] /admin list sent OK')
    except Exception as e:
        print(f'[Admin] /admin list ERROR: {e}')
        try:
            await interaction.followup.send(f'Error: {e}', ephemeral=True)
        except Exception:
            pass


@admin_group.command(name='pending', description='List all pending/unconfirmed members')
async def admin_pending(interaction: discord.Interaction):
    print(f'[Admin] /admin pending called by {interaction.user.id}')
    err = await _admin_gate(interaction)
    if err:
        print(f'[Admin] /admin pending blocked: {err}')
        await interaction.response.send_message(err, ephemeral=True)
        return
    await interaction.response.defer(thinking=True)
    try:
        data  = await asyncio.to_thread(get_admin_pending_embed)
        embed = _build_embed(data)
        await interaction.followup.send(embed=embed)
        print('[Admin] /admin pending sent OK')
    except Exception as e:
        print(f'[Admin] /admin pending ERROR: {e}')
        try:
            await interaction.followup.send(f'Error: {e}', ephemeral=True)
        except Exception:
            pass


@admin_group.command(name='confirm', description='Activate a pending member and send welcome DM')
@app_commands.describe(query='Member name or Discord ID')
async def admin_confirm(interaction: discord.Interaction, query: str):
    print(f'[Admin] /admin confirm "{query}" called by {interaction.user.id}')
    err = await _admin_gate(interaction)
    if err:
        print(f'[Admin] /admin confirm blocked: {err}')
        await interaction.response.send_message(err, ephemeral=True)
        return
    await interaction.response.defer(thinking=True)
    try:
        # confirm_member_embed sends a DM via synchronous requests — run in thread
        data  = await asyncio.to_thread(confirm_member_embed, query)
        embed = _build_embed(data)
        await interaction.followup.send(embed=embed)
        print(f'[Admin] /admin confirm "{query}" sent OK')
    except Exception as e:
        print(f'[Admin] /admin confirm ERROR: {e}')
        try:
            await interaction.followup.send(f'Error: {e}', ephemeral=True)
        except Exception:
            pass


@admin_group.command(name='extend', description='Extend a member\'s subscription')
@app_commands.describe(query='Member name or Discord ID', days='Number of days to add')
async def admin_extend(interaction: discord.Interaction, query: str, days: int):
    print(f'[Admin] /admin extend "{query}" {days}d called by {interaction.user.id}')
    err = await _admin_gate(interaction)
    if err:
        print(f'[Admin] /admin extend blocked: {err}')
        await interaction.response.send_message(err, ephemeral=True)
        return
    await interaction.response.defer(thinking=True)
    try:
        data  = await asyncio.to_thread(extend_member_embed, query, days)
        embed = _build_embed(data)
        await interaction.followup.send(embed=embed)
        print(f'[Admin] /admin extend "{query}" sent OK')
    except Exception as e:
        print(f'[Admin] /admin extend ERROR: {e}')
        try:
            await interaction.followup.send(f'Error: {e}', ephemeral=True)
        except Exception:
            pass


@admin_group.command(name='status', description='Show full details for one member')
@app_commands.describe(query='Member name or Discord ID')
async def admin_status(interaction: discord.Interaction, query: str):
    print(f'[Admin] /admin status "{query}" called by {interaction.user.id}')
    err = await _admin_gate(interaction)
    if err:
        print(f'[Admin] /admin status blocked: {err}')
        await interaction.response.send_message(err, ephemeral=True)
        return
    await interaction.response.defer(thinking=True)
    try:
        data  = await asyncio.to_thread(get_member_status_embed, query)
        embed = _build_embed(data)
        await interaction.followup.send(embed=embed)
        print(f'[Admin] /admin status "{query}" sent OK')
    except Exception as e:
        print(f'[Admin] /admin status ERROR: {e}')
        try:
            await interaction.followup.send(f'Error: {e}', ephemeral=True)
        except Exception:
            pass


tree.add_command(admin_group)


# ── Global error handler ──────────────────────────────────────

@tree.error
async def on_app_command_error(interaction: discord.Interaction,
                                error: app_commands.AppCommandError):
    cmd_name = interaction.command.name if interaction.command else 'unknown'
    print(f'[Bot] AppCommandError in /{cmd_name}: {type(error).__name__}: {error}')
    msg = f'Something went wrong: {error}'
    try:
        if interaction.response.is_done():
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.response.send_message(msg, ephemeral=True)
    except Exception as send_err:
        print(f'[Bot] Could not send error response: {send_err}')


@tree.command(name='help', description='How to use StockPilot PH — commands and glossary')
async def cmd_help(interaction: discord.Interaction):
    # Free and works everywhere — no gate
    data  = get_help_embed()
    embed = _build_embed(data)
    await interaction.response.send_message(embed=embed)


# ── Lifecycle ─────────────────────────────────────────────────

@client.event
async def on_ready():
    print(f'[StockPilot Bot] Logged in as {client.user} (ID: {client.user.id})')
    try:
        # Optional instant guild sync — set DISCORD_GUILD_ID in .env for immediate testing
        guild_id = os.getenv('DISCORD_GUILD_ID', '')
        if guild_id:
            guild  = discord.Object(id=int(guild_id))
            synced = await tree.sync(guild=guild)
            print(f'[StockPilot Bot] Guild sync: {len(synced)} command(s) synced instantly to guild {guild_id}.')
        else:
            synced = await tree.sync()
            print(f'[StockPilot Bot] Synced {len(synced)} slash command(s) globally.')
            print('[StockPilot Bot] Note: Global slash commands can take up to 1 hour to appear.')
            print('[StockPilot Bot] TIP: Set DISCORD_GUILD_ID in .env for instant sync during testing.')
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
