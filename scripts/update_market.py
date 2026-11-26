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
def fx_row(d,b,a,source):
 b,a=float(b),float(a)
 if not (15<b<=a<60 and a-b<2):raise ValueError('invalid spot pair')
 if d>str(dt.datetime.now(ZoneInfo('Asia/Taipei')).date()):raise ValueError('future quote')
 return dict(rate_date=d,spot_buy=b,spot_sell=a,source=source)
def spot_pair(tr):
 # BOT uses sight (spot), not cash; desktop and mobile may duplicate cells.
 cells=tr.select('td.rate-content-sight')
 if len(cells)>=2:
  return [c.get_text(strip=True) for c in cells[:2]]
 # Historical rows can have duplicated date/currency columns. Select numeric
 # cells only, in the published cash-buy, cash-sell, spot-buy, spot-sell order.
 nums=[c.get_text(strip=True) for c in tr.find_all('td',recursive=False)]
 nums=[v for v in nums if re.fullmatch(r'[0-9]+(?:\.[0-9]+)?',v) or v=='-']
 if len(nums)>=4:return nums[2:4]
 raise ValueError('spot columns absent')
def parse_live(html):
 soup=BeautifulSoup(html,'html.parser')
 # Prefer published date near the quote label or heading; no time required.
 candidates=[]
 for el in soup.select('.time, .pull-left, h1, h2, h3, title, time'):
  text=el.get_text(' ',strip=True)
  if '牌' in text or '匯率' in text or '掛牌' in text or el.name=='time':candidates.append(text)
 text=soup.get_text(' ',strip=True)
 pattern=r'(20\d{2})[年/.-]\s*(\d{1,2})[月/.-]\s*(\d{1,2})'
 match=re.search(r'(?:牌價最新掛牌時間|最新掛牌時間|掛牌時間|牌告日期|掛牌日期)\s*[：:]?\s*'+pattern,text)
 if not match:
  for candidate in candidates:
   match=re.search(pattern,candidate)
   if match:break
 if not match:raise ValueError('published date missing')
 d=dt.date(*map(int,match.groups())).isoformat()
 for tr in soup.select('table tr'):
  if re.search(r'\bUSD\b',tr.get_text(' ',strip=True)):
   b,a=spot_pair(tr);return fx_row(d,b,a,'Bank of Taiwan live')
 raise ValueError('USD row missing')
def fx():
 r=fetch('https://rate.bot.com.tw/xrt',params={'Lang':'zh-TW'});r.encoding='utf-8'
 try: live=parse_live(r.text)
 except ValueError as e:
  print('FX parse:',str(e),'; HTTP',r.status_code,'; bytes',len(r.content),'; tables',len(BeautifulSoup(r.text,'html.parser').select('table')),flush=True);raise
 existing=get('exchange_rates',{'select':'source','rate_date':'eq.'+live['rate_date']})
 if not existing or existing[0]['source']=='Bank of Taiwan live':put('exchange_rates',[live])
 print('FX live date:',live['rate_date'],'spot:',live['spot_buy'],live['spot_sell'],flush=True)
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
