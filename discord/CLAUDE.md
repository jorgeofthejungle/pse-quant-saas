# discord/CLAUDE.md — Discord Bot & Publisher Implementation Details
> See root CLAUDE.md for system rules, stock data format, DB schema, and architecture.
> This file covers discord-specific implementation details only.

Async safety rules are in root CLAUDE.md Section 7. For message and embed writing tone, see `reports/CLAUDE.md` Section 7A — the educational communication standard applies to all Discord content too.

---

## discord/publisher.py (facade)
Loads webhook URLs from `.env`. 4 webhooks: `rankings`, `alerts`, `deep_analysis`, `daily_briefing`.
Functions: `send_report`, `send_dividend_alert`, `send_price_alert`, `send_earnings_alert`,
`send_rescore_notice`, `send_weekly_briefing`, `send_stock_of_week`,
`send_dividend_calendar`, `send_model_performance`

## discord/bot.py
Slash command bot. Run with `py discord/bot.py`.
- `_premium_dm_gate(interaction)` — DM-only + premium member check (returns error string or None)
- `_dm_only_gate(interaction)` — DM-only, no premium check (for /subscribe, /mystatus)
- `_admin_gate(interaction)` — DM-only + ADMIN_DISCORD_ID check
- All admin handlers use `asyncio.to_thread()` to avoid blocking the event loop
- Guild sync: set `DISCORD_GUILD_ID` in `.env` for instant command propagation (testing)
- Global sync (no DISCORD_GUILD_ID): takes up to 1 hour to propagate

## discord/bot_admin.py
Josh-only commands via `/admin` group. All functions return embed dicts.
- `get_admin_list_embed()` — all active members
- `get_admin_pending_embed()` — pending members
- `confirm_member_embed(query)` — activates member + sends welcome DM (calls `send_welcome_dm` synchronously — bot.py wraps in asyncio.to_thread)
- `extend_member_embed(query, days)` — extends subscription
- `get_member_status_embed(query)` — full member detail
- `_find_member(query)` — finds by exact discord_id or partial name match

## discord/discord_dm.py
Sends embeds/text DMs via Discord REST API (bot token, not webhook).
- `send_dm_embed(discord_id, embed)` → `(bool, str)`
- `send_welcome_dm(discord_id, member_name, expiry_date)` → `(bool, str)`
- `send_dm_text(discord_id, content)` → `(bool, str)`
Uses synchronous `requests` — always call from a thread (not directly from async).

---

## Discord Channels

| Channel | Access | Webhook Env Var | Purpose |
|---------|--------|----------------|---------|
| `#rankings` | Premium | `DISCORD_WEBHOOK_RANKINGS` | Full PDF rankings report |
| `#deep-analysis` | Premium | `DISCORD_WEBHOOK_DEEP_ANALYSIS` | Stock of the Week, monthly reports |
| `#alerts` | Public | `DISCORD_WEBHOOK_ALERTS` | Price, dividend, earnings alerts |
| `#daily-briefing` | Public | `DISCORD_WEBHOOK_DAILY_BRIEFING` | Top 3 grades (no scores) |
