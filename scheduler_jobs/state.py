# scheduler_jobs/state.py — Shared scheduler state: pending PDF, signal cache, heartbeat, freshness gate
import json
import os
from datetime import datetime
from pathlib import Path

_STATE_DIR         = Path(os.environ.get('PSE_DATA_DIR', '/app/data')) / 'pse_quant'
_PENDING_PDF_PATH  = _STATE_DIR / 'pending_pdf.json'
_HELD_PDF_PATH     = _STATE_DIR / 'held_pdf.json'
_SIGNAL_CACHE_PATH = _STATE_DIR / 'last_signals.json'


def _load_signal_cache() -> dict:
    """Loads last-sent sentiment signals from disk. Returns {} on any error."""
    try:
        with open(_SIGNAL_CACHE_PATH, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def _save_signal_cache(cache: dict):
    """Persists the sentiment signal cache to disk."""
    try:
        _SIGNAL_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(_SIGNAL_CACHE_PATH, 'w', encoding='utf-8') as f:
            json.dump(cache, f)
    except Exception as e:
        print(f"  [signal cache] save failed: {e}")


def _signal_is_new(cache: dict, ticker: str, signal: str, score: float) -> bool:
    """
    Returns True if this signal should be sent.
    Skips if the same signal was already sent AND the sentiment score
    hasn't shifted more than 0.15 (on a -1.0 to 1.0 scale).
    """
    prev = cache.get(ticker, {})
    if prev.get('signal') != signal:
        return True
    return abs((prev.get('score') or 0.0) - score) >= 0.15


_PENDING_PDF_SIZE_LIMIT = 2 * 1024 * 1024  # 2 MB


def _make_json_safe(obj):
    """
    Recursively strip non-JSON-serializable values from dicts/lists.
    Non-serializable leaf values are replaced with None.
    """
    if isinstance(obj, dict):
        return {k: _make_json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_make_json_safe(item) for item in obj]
    try:
        json.dumps(obj)
        return obj
    except (TypeError, ValueError):
        return None


def _write_pending_pdf(ranked_sections: dict, reason: str, today: str):
    """
    Records that a PDF should be sent at the 6 PM report run.

    ranked_sections: dict[str, list] mapping portfolio type to ranked stock list.
    The full pre-scored, MoS-enriched data is embedded so run_daily_report()
    can skip re-scoring entirely.

    Falls back to trigger-only format {date, reason, tickers} if:
    - ranked_sections is not serializable, or
    - the resulting JSON exceeds 2 MB.
    Never raises.
    """
    try:
        _PENDING_PDF_PATH.parent.mkdir(parents=True, exist_ok=True)

        # Derive tickers from the first portfolio section (backward compat)
        first_section = next(iter(ranked_sections.values()), []) if ranked_sections else []
        tickers = [s['ticker'] for s in first_section if isinstance(s, dict) and 'ticker' in s]

        # Attempt to serialize ranked_sections with safety filter
        try:
            safe_sections = _make_json_safe(ranked_sections)
            full_payload = {
                'date':            today,
                'reason':          reason,
                'tickers':         tickers,
                'ranked_sections': safe_sections,
            }
            serialized = json.dumps(full_payload)
            if len(serialized.encode('utf-8')) > _PENDING_PDF_SIZE_LIMIT:
                raise ValueError(
                    f"ranked_sections JSON exceeds 2 MB "
                    f"({len(serialized.encode('utf-8'))} bytes)"
                )
            payload_to_write = full_payload
            use_json = serialized
        except Exception as serialize_err:
            print(f"  [pending pdf] ranked_sections not serializable — "
                  f"falling back to trigger-only format: {serialize_err}")
            fallback = {
                'date':    today,
                'reason':  reason,
                'tickers': tickers,
            }
            payload_to_write = fallback
            use_json = json.dumps(fallback)

        with open(_PENDING_PDF_PATH, 'w', encoding='utf-8') as f:
            f.write(use_json)
    except Exception as e:
        print(f"  [pending pdf] write failed: {e}")


def _read_pending_pdf() -> dict | None:
    """
    Returns pending PDF info if it exists and was written today, else None.

    The returned dict includes:
      'date', 'reason', 'tickers' — always present (when not None)
      'ranked_sections': dict | None — present when written by the new format;
                         None when the state file uses the old trigger-only format.
    """
    try:
        with open(_PENDING_PDF_PATH, encoding='utf-8') as f:
            data = json.load(f)
        today = datetime.now().strftime('%Y-%m-%d')
        if data.get('date') == today:
            if 'ranked_sections' not in data:
                data['ranked_sections'] = None
            return data
    except Exception:
        pass
    return None


def _clear_pending_pdf():
    try:
        _PENDING_PDF_PATH.unlink(missing_ok=True)
    except Exception:
        pass


def _write_held_pdf(pdf_path: str, reason: str, ranked_preview: list):
    """Records a PDF that was generated but held pending operator approval."""
    try:
        _HELD_PDF_PATH.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            'pdf_path':       str(pdf_path),
            'reason':         reason,
            'held_at':        datetime.now().isoformat(),
            'ranked_preview': [
                {'ticker': s['ticker'], 'score': s.get('score', 0), 'rank': s.get('rank', 0)}
                for s in (ranked_preview or [])[:10]
            ],
        }
        with open(_HELD_PDF_PATH, 'w', encoding='utf-8') as f:
            json.dump(payload, f)
    except Exception as e:
        print(f"  [held pdf] write failed: {e}")


def _read_held_pdf() -> dict | None:
    """Returns held PDF info if it exists, or None."""
    try:
        with open(_HELD_PDF_PATH, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None


def _clear_held_pdf():
    try:
        _HELD_PDF_PATH.unlink(missing_ok=True)
    except Exception:
        pass


def _record_heartbeat(job_name: str):
    """
    Write job completion timestamp to the settings table.
    Non-fatal — any DB or import error is silently logged to console.
    key: 'scheduler_heartbeat_{job_name}'
    """
    try:
        from db.db_connection import get_connection
        ts  = datetime.now().isoformat()
        key = f'scheduler_heartbeat_{job_name}'
        conn = get_connection()
        try:
            conn.execute(
                "INSERT INTO settings (key, value, updated_at) VALUES (%s, %s, %s) ON CONFLICT(key) DO UPDATE SET value = EXCLUDED.value, updated_at = EXCLUDED.updated_at",
                (key, ts, ts),
            )
            conn.commit()
        finally:
            conn.close()
        print(f"  [heartbeat] {job_name} recorded at {ts[:19]}")
    except Exception as e:
        print(f"  [heartbeat] write failed for {job_name}: {e}")


def _check_price_freshness() -> bool:
    """
    Returns True if price data is fresh enough to score.
    Queries: SELECT COUNT(*) FROM prices WHERE date >= date('now', '-N days')
    If count == 0, prices are stale — sends admin DM and returns False.
    N is PRICE_STALENESS_ERROR_DAYS from config.py.
    """
    try:
        from config import PRICE_STALENESS_ERROR_DAYS as _days
    except ImportError:
        _days = 30

    try:
        from db.db_connection import get_connection
        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT COUNT(*) AS cnt FROM prices WHERE date >= CURRENT_DATE - %s * INTERVAL '1 day'",
                (_days,),
            ).fetchone()
        finally:
            conn.close()
        count = row['cnt'] if row else 0
    except Exception as e:
        print(f"  [freshness] DB query failed — skipping gate: {e}")
        return True  # fail-open: don't block scoring on a DB error

    if count == 0:
        msg = (
            f"[PSE Quant] STALE PRICE DATA — no prices updated in the last "
            f"{_days} days. Scoring skipped. "
            f"Check PSE Edge scraper or price pipeline."
        )
        print(f"  [freshness] {msg}")
        try:
            admin_id = os.environ.get('ADMIN_DISCORD_ID', '')
            if admin_id:
                from discord.discord_dm import send_dm_text
                send_dm_text(admin_id, msg)
        except Exception as dm_err:
            print(f"  [freshness] admin DM failed: {dm_err}")
        return False

    return True
