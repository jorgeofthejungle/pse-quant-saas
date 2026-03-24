# dashboard/CLAUDE.md — Flask Dashboard Implementation Details
> See root CLAUDE.md for system rules, stock data format, DB schema, and architecture.
> This file covers dashboard-specific implementation details only.

Flask dashboard on port 8080. Run via `py dashboard/app.py`. Each request opens its own DB connection per the thread-safety rule in root CLAUDE.md Section 12.

---

## dashboard/access_control.py
Member tier and access control for bot commands and portal.
- `check_access(discord_id, feature)` → `bool`
- `get_member_tier(discord_id)` → `'free' | 'paid'`
- `get_member_by_discord_id(discord_id)` → `dict | None`
Features: `'discord_bot'`, `'stock_lookup'`, `'watchlist'`, `'pdf_reports'`

## dashboard/app.py
Flask app — run with `py dashboard/app.py`, open `http://localhost:8080`.
Pages: Overview, Pipeline, Stock Lookup, Members, Analytics, Settings, Portal, Conglomerates.

## dashboard/background.py
`start_scheduler()` — launches `py scheduler.py` via subprocess.Popen.
`stop_scheduler()` / `get_scheduler_status()` — process lifecycle management.

## Other dashboard files
- `routes_home.py`, `routes_pipeline.py`, `routes_members.py`, `routes_analytics.py`, `routes_settings.py`, `routes_portal.py` — Flask route handlers (one file per page)
- `db_members.py` — member and subscription DB operations
- `templates/` — Jinja2 HTML templates (one per page)
- `static/style.css`, `static/dashboard.js` — frontend assets
