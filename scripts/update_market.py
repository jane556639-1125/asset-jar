import os, datetime as dt, requests, time, math
from urllib.parse import urlsplit
from bs4 import BeautifulSoup
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
 except Exception as e: errors.append(name);print(name,'failed:',diagnostic(e),flush=True)
def diagnostic(e):
 if isinstance(e,requests.HTTPError) and e.response is not None:
  return f'HTTP {e.response.status_code} host={urlsplit(e.response.url).hostname}'
 if isinstance(e,ImportError): return 'ImportError module='+str(getattr(e,'name',None))
 return type(e).__name__
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
 import yfinance as yf
 from concurrent.futures import ThreadPoolExecutor
 tickers={'VTI','VOO','QQQ','AAPL','NVDA','MSFT','VGIT'}
 for table in ['transactions','opening_holdings','targets']:
  offset=0
  while True:
   rows=get(table,{'select':'ticker','market':'eq.US','limit':1000,'offset':offset,'order':'id'});tickers.update(x['ticker'] for x in rows)
   if len(rows)<1000:break
   offset+=1000
 now=dt.datetime.now(ZoneInfo('America/New_York'))
 def one(t):
  try:
   frame=yf.Ticker(t).history(period='1mo',interval='1d',auto_adjust=False,timeout=15,raise_errors=True)
   rows=[]
   for stamp,p in frame['Close'].items():
    d=stamp.date();p=float(p)
    if math.isfinite(p) and p>0 and (d<now.date() or (d==now.date() and now.hour>=17)):
     rows.append(dict(market='US',ticker=t,price_date=str(d),close_price=p,source='Yahoo Finance'))
   if not rows:raise ValueError('no completed sessions')
   return rows
  except Exception as e:
   print('US symbol request failed:',diagnostic(e),flush=True);return []
 with ThreadPoolExecutor(max_workers=3) as pool: results=list(pool.map(one,sorted(tickers)))
 rows=[r for group in results for r in group]
 if rows:put('stock_prices',rows)
 print('US symbols updated:',sum(bool(x) for x in results),'/',len(results),flush=True)
 if not all(results):raise ValueError('partial US coverage')
def parse_fx(html):
 soup=BeautifulSoup(html,'html.parser');rows={}
 for tr in soup.select('table tbody tr'):
  cells=tr.find_all('td',recursive=False)
  if not cells:continue
  try:
   d=date(cells[0].get_text(strip=True))
   # BOT historical table has date, currency, cash buy/sell, spot buy/sell.
   # Desktop rate cells are identified by their official class, avoiding mobile duplicates.
   ratecells=tr.select('td.rate-content-cash.text-right.print_hide, td.rate-content-sight.text-right.print_hide')
   if len(ratecells)!=4:
    ratecells=tr.select('td.rate-content-cash, td.rate-content-sight')
   if len(ratecells)==4: b,a=[float(c.get_text(strip=True)) for c in ratecells[-2:]]
   elif len(cells)==6: b,a=[float(c.get_text(strip=True)) for c in cells[4:6]]
   else:continue
   if not (15<b<=a<60 and a-b<2):continue
   if d>str(dt.datetime.now(ZoneInfo('Asia/Taipei')).date()):continue
   rows[d]=dict(rate_date=d,spot_buy=b,spot_sell=a,source='Bank of Taiwan')
  except (ValueError,TypeError,IndexError):continue
 return list(rows.values())
def fx():
 rows={}
 for path in ['l6m','ltm']:
  try:
   r=fetch('https://rate.bot.com.tw/xrt/quote/'+path+'/USD');r.encoding='utf-8'
   for row in parse_fx(r.text):rows[row['rate_date']]=row
  except Exception as e:print('FX source failed:',diagnostic(e),flush=True)
 if not rows:raise ValueError('no verified FX rows')
 put('exchange_rates',list(rows.values()))
 print('FX dates:',min(rows),'to',max(rows),'count',len(rows),flush=True)
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
if __name__=='__main__':
 for name,fn in [('TW',tw),('FX',fx),('US',us),('catalog',catalog)]:run(name,fn)
 if errors:raise SystemExit('Partial update: '+', '.join(errors))
