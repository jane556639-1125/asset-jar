import os, datetime as dt, requests, pandas as pd, io, time
from zoneinfo import ZoneInfo
URL=os.environ['SUPABASE_URL'].rstrip('/')+'/rest/v1/'
H={'apikey':os.environ['SUPABASE_SECRET_KEY'],'Prefer':'resolution=merge-duplicates,return=minimal'}
def get(t,params=None):
 r=requests.get(URL+t,headers=H,params=params,timeout=30);r.raise_for_status();return r.json()
def put(t,rows):
 for i in range(0,len(rows),300):
  r=requests.post(URL+t,headers=H,json=rows[i:i+300],timeout=45);r.raise_for_status()
def fetch(url,**kw):
 r=requests.get(url,timeout=40,headers={'User-Agent':'Mozilla/5.0'},**kw);r.raise_for_status();return r
errors=[]
def run(name,fn):
 try: fn();print(name,'OK')
 except Exception as e: errors.append(name);print(name,'failed:',type(e).__name__)
def date(s):
 s=str(s).replace('/','').replace('-','');return dt.date(int(s[:-4])+(1911 if len(s)==7 else 0),int(s[-4:-2]),int(s[-2:])).isoformat()
def tw():
 for url,code,price,day in [('https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL','Code','ClosingPrice','Date'),('https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes','SecuritiesCompanyCode','Close','Date')]:
  rows=[]
  for x in fetch(url).json():
   try: rows.append(dict(market='TW',ticker=x[code],price_date=date(x[day]),close_price=float(str(x[price]).replace(',','')),source='TWSE' if 'twse' in url else 'TPEx'))
   except (ValueError,KeyError,TypeError): continue
  if not rows: raise ValueError('empty TW data')
  put('stock_prices',[x for x in rows if x['close_price']>0])
def us():
 tickers={'VTI','VOO','QQQ','AAPL','NVDA','MSFT','VGIT'}
 for table in ['transactions','opening_holdings','targets']:
  offset=0
  while True:
   rows=get(table,{'select':'ticker','market':'eq.US','limit':1000,'offset':offset,'order':'id'});tickers.update(x['ticker'] for x in rows)
   if len(rows)<1000:break
   offset+=1000
 for t in sorted(tickers):
  try:
   from urllib.parse import quote
   j=fetch('https://query1.finance.yahoo.com/v8/finance/chart/'+quote(t,safe=''),params={'range':'1mo','interval':'1d'}).json()['chart']['result'][0]; rows=[]
   for stamp,p in zip(j['timestamp'],j['indicators']['quote'][0]['close']):
    d=dt.datetime.fromtimestamp(stamp,ZoneInfo('America/New_York')).date();now=dt.datetime.now(ZoneInfo('America/New_York'))
    if p and p>0 and (d<now.date() or (d==now.date() and now.hour>=17)):rows.append(dict(market='US',ticker=t,price_date=str(d),close_price=p,source='Yahoo Finance'))
   if not rows:raise ValueError()
   put('stock_prices',rows)
  except Exception: errors.append('US ticker')
  time.sleep(.3)
def fx():
 # Official historical USD table, last six months; reject ambiguous column layouts.
 r=fetch('https://rate.bot.com.tw/xrt/quote/l6m/USD');r.encoding='utf-8';tables=pd.read_html(io.StringIO(r.text));rows=[]
 for frame in tables:
  for _,x in frame.iterrows():
   vals=list(x);s=str(vals[0]).strip()
   try:
    d=date(s);b=float(vals[4]);a=float(vals[5]);assert 15<b<=a<60 and a-b<2
    rows.append(dict(rate_date=d,spot_buy=b,spot_sell=a,source='Bank of Taiwan'))
   except (ValueError,TypeError,AssertionError,IndexError):continue
 if not rows:raise ValueError('no verified FX rows')
 put('exchange_rates',rows)
def catalog():
 import json
 from bs4 import BeautifulSoup
 out={}
 for mode in (2,4):
  r=fetch('https://isin.twse.com.tw/isin/C_public.jsp',params={'strMode':mode});s=BeautifulSoup(r.content.decode('cp950',errors='replace'),'html.parser');group=''
  for tr in s.select('tr'):
   cells=tr.find_all('td');
   if len(cells)==1:group=cells[0].get_text(strip=True);continue
   if len(cells)<6 or not any(k in group for k in ('股票','ETF')):continue
   parts=cells[0].get_text(strip=True).split(maxsplit=1)
   if len(parts)==2:out[parts[0]]=parts[1]
 if len(out)<500:raise ValueError('catalog incomplete')
 with open('stock-catalog.json','w',encoding='utf8') as f:json.dump({'TW':out},f,ensure_ascii=False)
for name,fn in [('TW',tw),('US',us),('FX',fx),('catalog',catalog)]:run(name,fn)
if errors:raise SystemExit('Partial update: '+', '.join(errors))
