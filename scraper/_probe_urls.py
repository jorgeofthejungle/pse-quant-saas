"""
Probe: Get full financial_reports_view.do tables + report edge_nos.
Run: py scraper/_probe_urls.py
"""
import requests
from bs4 import BeautifulSoup
import re
import time

session = requests.Session()
session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
})
session.get('https://edge.pse.com.ph', timeout=20)
time.sleep(1)

BASE = 'https://edge.pse.com.ph'

# --- Full financial_reports_view.do tables ---
print('=== financial_reports_view.do — all table rows ===')
r = session.get(BASE + '/companyPage/financial_reports_view.do',
                params={'cmpy_id': '188'}, timeout=20)
soup = BeautifulSoup(r.text, 'lxml')

# Print fiscal year / units line
page_text = soup.get_text()
# Find the fiscal year and units line
for line in page_text.split('\n'):
    line = line.strip()
    if line and any(k in line.lower() for k in ['fiscal year', 'currency', 'thousand', 'million', 'units']):
        print(f'  HEADER: {line}')

print()
for i, table in enumerate(soup.find_all('table')):
    rows = table.find_all('tr')
    print(f'--- Table {i} ({len(rows)} rows) ---')
    for row in rows:
        cells = row.find_all(['td', 'th'])
        vals = [c.get_text(strip=True) for c in cells]
        if vals:
            print(f'  {vals}')
    print()

time.sleep(1)

# --- financialReports/search.ax to get edge_nos ---
print('=== financialReports/search.ax — annual reports for DMC ===')
session.get(BASE + '/financialReports/form.do', timeout=20)
time.sleep(0.5)
r2 = session.get(BASE + '/financialReports/search.ax',
                 params={'companyId': '188', 'tmplNm': '',
                         'fromDate': '01-01-2018', 'toDate': '12-31-2026',
                         'sortType': 'D', 'pageNo': '1'},
                 timeout=20)
print(f'Status: {r2.status_code}  Size: {len(r2.text)}')
soup2 = BeautifulSoup(r2.text, 'lxml')

# Look for edge_no / report number in all links + onclick
print('All links on results page:')
for tag in soup2.find_all(True):
    href   = tag.get('href', '')
    onclick = tag.get('onclick', '')
    if href or onclick:
        for val in [href, onclick]:
            if any(k in val.lower() for k in ['edge', 'report', 'disc', 'open']):
                print(f'  tag={tag.name}  href={href!r}  onclick={onclick[:100]!r}')
                break

# Print all rows
print('\nAll table rows:')
for row in soup2.find_all('tr'):
    cells = row.find_all(['td','th'])
    if cells:
        print(f'  {[c.get_text(strip=True)[:50] for c in cells]}')
