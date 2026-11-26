import os, datetime as dt, requests, time, math, re
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
 r=requests.get(url,timeout=20,headers={'User-Agent':'Mozilla/5.0'},**kw);r.raise_for_status();return r
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
 tickers=set()
 for table in ['transactions','opening_holdings','targets']:
  offset=0
  while True:
   rows=get(table,{'select':'ticker','market':'eq.US','limit':1000,'offset':offset,'order':'id'});tickers.update(x['ticker'] for x in rows)
   if len(rows)<1000:break
   offset+=1000
 if not tickers:
  print('US: no tracked symbols; nothing to update');return
 now=dt.datetime.now(ZoneInfo('America/New_York')); count=0
 for t in sorted(tickers):
  try:
   frame=yf.Ticker(t.replace('.','-')).history(period='5d',interval='1d',auto_adjust=False,timeout=10)
   rows=[]
   for stamp,price in frame['Close'].items():
    d=stamp.date();price=float(price)
    if math.isfinite(price) and price>0 and (d<now.date() or (d==now.date() and now.hour>=17)):
     rows.append(dict(market='US',ticker=t,price_date=str(d),close_price=price,source='Yahoo Finance'))
   if not rows:raise ValueError('no completed sessions')
   put('stock_prices',rows);count+=1
  except Exception as e:print('US symbol request failed:',diagnostic(e),flush=True)
 print('US symbols updated:',count,'/',len(tickers),flush=True)
 if count!=len(tickers):raise ValueError('partial US coverage')
def fx():
 # Reference midpoint, not actual bank bid/ask. Retain existing rates.
 today=dt.datetime.now(ZoneInfo('Asia/Taipei')).date()
 start=today.replace(year=today.year-5,day=min(today.day,28))
 data=fetch('https://api.frankfurter.dev/v2/rates',params={'base':'USD','quotes':'TWD','from':start.isoformat(),'to':today.isoformat()}).json()
 if not isinstance(data,list) or not data:raise ValueError('empty FX series')
 rows={}
 for item in data:
  if item.get('base')!='USD' or item.get('quote')!='TWD':raise ValueError('unexpected FX pair')
  d=dt.date.fromisoformat(item['date']); rate=float(item['rate'])
  if not start<=d<=today or not math.isfinite(rate) or not 15<rate<60:raise ValueError('invalid FX observation')
  if d.weekday()<5:
   rows[str(d)]=dict(rate_date=str(d),spot_buy=rate,spot_sell=rate,source='Frankfurter v2 reference midpoint (not bank bid/ask)')
 if not rows or (today-dt.date.fromisoformat(max(rows))).days>7:raise ValueError('missing recent FX observations')
 # Ignore conflicts to preserve prior valuations and BOT records.
 values=list(rows.values())
 for i in range(0,len(values),300):
  r=requests.post(URL+'exchange_rates',headers={**H,'Prefer':'resolution=ignore-duplicates,return=minimal'},json=values[i:i+300],timeout=25);r.raise_for_status()
 print('FX series validated:',len(values),'latest:',max(rows),'mid:',rows[max(rows)]['spot_buy'],flush=True)
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
 import argparse
 parser=argparse.ArgumentParser();parser.add_argument('task',choices=['tw','us','fx','catalog']);args=parser.parse_args()
 run(args.task.upper(),globals()[args.task])
 if errors:raise SystemExit(1)
