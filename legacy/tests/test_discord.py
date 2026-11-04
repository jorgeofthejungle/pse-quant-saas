import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'engine'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'reports'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'discord'))

from publisher import test_webhook, send_report, WEBHOOKS

# ============================================================
# Step 1 — Test that each webhook URL is reachable
# ============================================================

print("=" * 55)
print("  PSE QUANT SAAS — Discord Webhook Test")
print("=" * 55)

all_ok = True
for channel, url in WEBHOOKS.items():
    if not url:
        print(f"  SKIP  #{channel} — no webhook URL set in .env")
        continue
    ok = test_webhook(url, f'pse-{channel}')
    if not ok:
        all_ok = False

print()
if all_ok:
    print("All configured webhooks are working.")
else:
    print("One or more webhooks failed. Check the URLs in config.py.")

# ============================================================
# Step 2 — Send a sample report to the dividend channel
# Run this only after Step 1 passes
# ============================================================

DIVIDEND_WEBHOOK = WEBHOOKS.get('pure_dividend', '')
DESKTOP          = os.path.join(os.path.expanduser('~'), 'Desktop')
PDF_PATH         = os.path.join(DESKTOP, 'PSE_PURE_DIVIDEND_REPORT.pdf')

if DIVIDEND_WEBHOOK and os.path.exists(PDF_PATH):
    print()
    print("Sending sample Dividend report to Discord...")

    sample_stocks = [
        {
            'ticker':         'DMC',
            'score':          81.0,
            'dividend_yield': 8.35,
            'mos_pct':        22.4,
            'mos_price':      10.88,
        },
        {
            'ticker':         'AREIT',
            'score':          72.5,
            'dividend_yield': 6.20,
            'mos_pct':        -4.3,
            'mos_price':      36.50,
        },
        {
            'ticker':         'MER',
            'score':          68.0,
            'dividend_yield': 4.20,
            'mos_pct':        8.1,
            'mos_price':      354.20,
        },
    ]

    ok = send_report(
        webhook_url    = DIVIDEND_WEBHOOK,
        pdf_path       = PDF_PATH,
        portfolio_type = 'pure_dividend',
        ranked_stocks  = sample_stocks,
    )

    print("Report delivered." if ok else "Delivery failed.")
elif not DIVIDEND_WEBHOOK:
    print()
    print("Skipping report send — add your #pse-dividend webhook URL to .env first.")
elif not os.path.exists(PDF_PATH):
    print()
    print(f"Skipping report send — PDF not found at: {PDF_PATH}")
    print("Run tests/test_pdf.py first to generate the PDF.")

print()
print("=" * 55)
