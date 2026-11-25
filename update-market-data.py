import json, re, requests
from pathlib import Path
from bs4 import BeautifulSoup
from datetime import date
p=Path('market-data.json')
data=json.loads(p.read_text()) if p.exists() else {'tickers':{'TW':{},'US':{}},'rates':{}}
def get(url):
    r=requests.get(url,timeout=35,headers={'User-Agent':'AssetJar personal reference data contact admin@example.com'});r.raise_for_status();return r
for url in ['https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL','https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes']:
    try:
        for x in get(url).json():
            code=x.get('Code') or x.get('SecuritiesCompanyCode'); name=x.get('Name') or x.get('CompanyName') or x.get('SecuritiesCompanyName')
            if code and name:data['tickers']['TW'][str(code)]=name
    except Exception as e: print('TW source failed:',e)
try:
    for x in get('https://www.sec.gov/files/company_tickers.json').json().values():data['tickers']['US'][x['ticker']]=x['title']
except Exception as e: print('US source failed:',e)
try:
    soup=BeautifulSoup(get('https://rate.bot.com.tw/xrt/quote/l6m/USD?Lang=zh-TW').text,'html.parser')
    count=0
    for row in soup.select('table tbody tr'):
        cells=[c.get_text(' ',strip=True) for c in row.select('td')]
        if not cells:continue
        match=re.search(r'\b(20\d\d)[/-](\d{1,2})[/-](\d{1,2})\b',cells[0])
        if not match:continue
        nums=[float(c) for c in cells[1:] if re.fullmatch(r'\d+\.\d+',c)]
        if len(nums)!=4:continue
        buy,sell=nums[-2:]
        if 10<buy<=sell<100:
            day=date(*map(int,match.groups())).isoformat();data['rates'][day]=round((buy+sell)/2,6);count+=1
    if not count:raise ValueError('No valid BOT historical rows; old rates retained')
    print('BOT rows:',count)
except Exception as e:print('BOT source failed:',e)
p.write_text(json.dumps(data,ensure_ascii=False,indent=2))
