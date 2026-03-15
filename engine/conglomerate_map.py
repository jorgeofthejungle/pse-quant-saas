# ============================================================
# conglomerate_map.py — PH Conglomerate Parent-Child Registry
# PSE Quant SaaS
# ============================================================
# Defines which PSE tickers are subsidiaries/associates of
# which parent conglomerates.
#
# 'ticker': PSE ticker if the subsidiary is separately listed.
#           None if unlisted — those stay as manual entries.
# 'ownership': approximate % ownership by parent (informational).
# 'notes': brief description.
#
# This map drives auto-segmentation: when a listed subsidiary's
# financials are updated by the weekly scraper, the parent's
# segment data auto-updates too.
# ============================================================

CONGLOMERATE_MAP: dict[str, list[dict]] = {

    # ── SM INVESTMENTS CORPORATION ──────────────────────────────
    'SM': [
        {'name': 'Property (SM Prime)',        'ticker': 'SMPH', 'ownership': 44.4},
        {'name': 'Banking (BDO Unibank)',       'ticker': 'BDO',  'ownership': 43.5},
        {'name': 'Banking (China Banking)',     'ticker': 'CHIB', 'ownership': 46.5},
        {'name': 'Retail (SM Retail)',          'ticker': None,   'ownership': 100.0,
         'notes': 'Unlisted. SM Supermarket, SaveMore, SM Department Store'},
    ],

    # ── AYALA CORPORATION ───────────────────────────────────────
    'AC': [
        {'name': 'Real Estate (Ayala Land)',    'ticker': 'ALI',  'ownership': 64.0},
        {'name': 'Banking (BPI)',               'ticker': 'BPI',  'ownership': 30.0},
        {'name': 'Telecommunications (Globe)',  'ticker': 'GLO',  'ownership': 21.0},
        {'name': 'Power (ACEN)',                'ticker': 'ACEN', 'ownership': 56.0},
        {'name': 'Industrials (IMI)',           'ticker': 'IMI',  'ownership': 51.0},
        {'name': 'Water (Manila Water)',        'ticker': 'MWC',  'ownership': 6.2,
         'notes': 'Associate stake. MWC also partly owned by DMC'},
    ],

    # ── JG SUMMIT HOLDINGS ──────────────────────────────────────
    'JGS': [
        {'name': 'Food & Beverages (URC)',      'ticker': 'URC',  'ownership': 81.0},
        {'name': 'Aviation (Cebu Pacific)',     'ticker': 'CEB',  'ownership': 66.0},
        {'name': 'Real Estate (Robinsons)',     'ticker': 'RLC',  'ownership': 60.0},
        {'name': 'Petrochemicals (JGSOC)',      'ticker': None,   'ownership': 100.0,
         'notes': 'Unlisted. Indefinite shutdown Jan 2026. Drag on group NI'},
        {'name': 'Digital Banking (GoTyme)',    'ticker': None,   'ownership': 50.0,
         'notes': 'Unlisted. JV with Tyme Group. Not yet profitable'},
    ],

    # ── GT CAPITAL HOLDINGS ─────────────────────────────────────
    'GTCAP': [
        {'name': 'Banking (Metrobank)',         'ticker': 'MBT',  'ownership': 57.8},
        {'name': 'Infrastructure (MPIC)',       'ticker': 'MPI',  'ownership': 13.0,
         'notes': 'Associate via Ty family interests. Equity-accounted'},
        {'name': 'Automotive (Toyota PH)',      'ticker': None,   'ownership': 51.0,
         'notes': 'Unlisted. Largest Toyota dealer in PH. ~PHP 242B revenue'},
        {'name': 'Real Estate (Federal Land)',  'ticker': None,   'ownership': 65.0,
         'notes': 'Unlisted. Federal Land Inc. not the same as FLI (Filinvest)'},
        {'name': 'Insurance (AXA Philippines)', 'ticker': None,   'ownership': 51.0,
         'notes': 'Unlisted. JV with AXA SA. Gross premiums ~PHP 30.4B'},
    ],

    # ── DMCI HOLDINGS ───────────────────────────────────────────
    'DMC': [
        {'name': 'Coal Mining & Power (Semirara)', 'ticker': 'SCC', 'ownership': 56.0},
        {'name': 'Water Utility (Maynilad)',    'ticker': 'MWC',  'ownership': 25.0,
         'notes': 'Also partly owned by AC. Equity-accounted'},
        {'name': 'Cement (Cemex PH)',           'ticker': 'CHP',  'ownership': 100.0,
         'notes': 'Acquired 2024. Integration phase'},
        {'name': 'Real Estate (DMCI Homes)',    'ticker': None,   'ownership': 100.0,
         'notes': 'Unlisted'},
        {'name': 'Off-grid Power (DMCI Power)', 'ticker': None,   'ownership': 100.0,
         'notes': 'Unlisted. Serves island grids (Palawan, etc.)'},
        {'name': 'Nickel Mining (DMCI Mining)', 'ticker': None,   'ownership': 100.0,
         'notes': 'Unlisted'},
        {'name': 'Construction (D.M. Consunji)', 'ticker': None,  'ownership': 100.0,
         'notes': 'Unlisted. Net loss 2024 on project delays'},
    ],

    # ── ABOITIZ EQUITY VENTURES ─────────────────────────────────
    'AEV': [
        {'name': 'Power (AboitizPower)',        'ticker': 'AP',   'ownership': 76.0},
        {'name': 'Banking (UnionBank)',         'ticker': 'UBP',  'ownership': 55.0},
        {'name': 'Food (Pilmico/Gold Coin)',    'ticker': None,   'ownership': 100.0,
         'notes': 'Unlisted. Animal nutrition + flour milling'},
        {'name': 'Real Estate (Aboitiz Land)', 'ticker': None,   'ownership': 100.0,
         'notes': 'Unlisted. Residential and commercial developments'},
        {'name': 'Infrastructure/Land',        'ticker': None,   'ownership': 100.0,
         'notes': 'Unlisted. Industrial estates, port operations'},
    ],

    # ── ALLIANCE GLOBAL GROUP ───────────────────────────────────
    'AGI': [
        {'name': 'Real Estate (Megaworld)',     'ticker': 'MEG',  'ownership': 73.0},
        {'name': 'Liquor (Emperador)',          'ticker': 'EMI',  'ownership': 78.0},
        {'name': 'Tourism (Travellers Intl)',   'ticker': 'RWM',  'ownership': 55.0,
         'notes': 'Resorts World Manila. Limited data — may not have full financials'},
        {'name': 'Food (Golden Arches / McDo)', 'ticker': None,   'ownership': 100.0,
         'notes': "Unlisted. McDonald's PH master franchisor"},
    ],

    # ── LT GROUP INCORPORATED ───────────────────────────────────
    'LTG': [
        {'name': 'Banking (PNB)',               'ticker': 'PNB',  'ownership': 78.0},
        {'name': 'Tobacco (Philip Morris PH)',  'ticker': None,   'ownership': 100.0,
         'notes': 'Unlisted. PMFTC Inc. — largest tobacco co. in PH'},
        {'name': 'Spirits (Tanduay Distillers)', 'ticker': None,  'ownership': 100.0,
         'notes': 'Unlisted. #1 selling rum globally by volume'},
        {'name': 'Real Estate (Eton Properties)', 'ticker': None, 'ownership': 100.0,
         'notes': 'Unlisted. Mixed-use developments'},
    ],

    # ── FIRST PHILIPPINE HOLDINGS ───────────────────────────────
    'FPH': [
        {'name': 'Power (First Gen)',           'ticker': 'FGEN', 'ownership': 66.0},
        {'name': 'Real Estate (Rockwell Land)', 'ticker': 'ROCK', 'ownership': 55.0},
        {'name': 'Industrial Parks',            'ticker': None,   'ownership': 100.0,
         'notes': 'Unlisted. First Philippine Industrial Park'},
    ],

    # ── SAN MIGUEL CORPORATION ──────────────────────────────────
    'SMC': [
        {'name': 'Food & Beverage (San Miguel FB)', 'ticker': 'FB',   'ownership': 94.0},
        {'name': 'Fuel & Oil (Petron)',          'ticker': 'PCOR', 'ownership': 68.0},
        {'name': 'Spirits (Ginebra San Miguel)', 'ticker': 'GSMI', 'ownership': 99.0},
        {'name': 'Infrastructure (SMC Global)', 'ticker': None,   'ownership': 100.0,
         'notes': 'Unlisted. Toll roads, airport (NAIA), telecom'},
        {'name': 'Packaging (SMC Global Pack)', 'ticker': None,   'ownership': 100.0,
         'notes': 'Unlisted. Bottles, cans, PET, paper'},
    ],

    # ── FILINVEST DEVELOPMENT CORPORATION ───────────────────────
    'FDC': [
        {'name': 'Banking (EastWest Bank)',     'ticker': 'EW',   'ownership': 80.0},
        {'name': 'Real Estate (Filinvest Land)', 'ticker': 'FLI',  'ownership': 67.0},
        {'name': 'Hospitality (Crimson Hotels)', 'ticker': None,  'ownership': 100.0,
         'notes': 'Unlisted. Hotel and resort operations'},
        {'name': 'Power (FDC Utilities)',       'ticker': None,   'ownership': 100.0,
         'notes': 'Unlisted. Biomass and solar power'},
        {'name': 'Sugar (Filinvest Sugar)',     'ticker': None,   'ownership': 100.0,
         'notes': 'Unlisted'},
    ],
}

# All parent tickers that have conglomerate-level analysis
ALL_CONGLOMERATE_TICKERS = list(CONGLOMERATE_MAP.keys())

# Quick lookup: child ticker → parent ticker(s)
CHILD_TO_PARENT: dict[str, list[str]] = {}
for _parent, _segs in CONGLOMERATE_MAP.items():
    for _seg in _segs:
        if _seg.get('ticker'):
            CHILD_TO_PARENT.setdefault(_seg['ticker'], []).append(_parent)
