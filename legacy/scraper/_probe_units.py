"""
Check the unit text on AREIT's financial page vs DMC.
Run: py scraper/_probe_units.py
"""
import requests
from bs4 import BeautifulSoup
import re, time

session = requests.Session()
session.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'})
session.get('https://edge.pse.com.ph', timeout=20)
time.sleep(1)

for ticker, cmpy_id in [('DMC', '188'), ('AREIT', '679'), ('BDO', '89')]:
    r = session.get('https://edge.pse.com.ph/companyPage/financial_reports_view.do',
                    params={'cmpy_id': cmpy_id}, timeout=20)
    soup = BeautifulSoup(r.text, 'lxml')
    page_text = soup.get_text()

    # Find currency/unit line
    unit_matches = re.findall(r'[Cc]urrency[^:\n]{0,30}:([^\n]{0,60})', page_text)
    unit_text = unit_matches[0].strip() if unit_matches else 'NOT FOUND'

    # Also find fiscal year
    yr_matches = re.findall(r'[Ff]or the fiscal year ended[^:]*:\s*([^\n]{0,30})', page_text)
    yr_text = yr_matches[0].strip() if yr_matches else 'NOT FOUND'

    # Find first Revenue row to see raw number
    revenue_val = 'NOT FOUND'
    for table in soup.find_all('table'):
        rows = table.find_all('tr')
        if not rows:
            continue
        header_text = ' '.join(c.get_text(strip=True).lower() for c in rows[0].find_all(['th','td']))
        if 'current year' not in header_text:
            continue
        for row in rows[1:]:
            cells = row.find_all(['td','th'])
            if len(cells) >= 2:
                label = cells[0].get_text(strip=True).lower()
                if 'revenue' in label or 'gross' in label:
                    revenue_val = cells[1].get_text(strip=True)
                    break
        if revenue_val != 'NOT FOUND':
            break

    print(f'\n{ticker} (cmpy_id={cmpy_id}):')
    print(f'  Unit:    {unit_text!r}')
    print(f'  FY:      {yr_text!r}')
    print(f'  Revenue raw cell: {revenue_val!r}')
    time.sleep(1)
