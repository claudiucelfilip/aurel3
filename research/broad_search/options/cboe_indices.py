import requests, io, pandas as pd, numpy as np, yfinance as yf
base="https://cdn.cboe.com/api/global/us_indices/daily_prices/{}_History.csv"
ser={}
for s in ["BXM","BXMD","BXY","PUT","CLL","PPUT","CMBO","SPTR"]:
    r=requests.get(base.format(s),timeout=30,headers={"User-Agent":"Mozilla/5.0"})
    print(s,r.status_code,len(r.text))
    if r.status_code==200 and len(r.text)>1000:
        d=pd.read_csv(io.StringIO(r.text)); d.columns=[c.strip().lower() for c in d.columns]
        dc=[c for c in d.columns if "date" in c][0]; vc=[c for c in d.columns if c!=dc][-1]
        d[dc]=pd.to_datetime(d[dc]); ser[s]=d.set_index(dc)[vc].astype(float).sort_index()
        print("   ",d.columns.tolist(),ser[s].index[0].date(),ser[s].index[-1].date())
tr=yf.download("^SP500TR",start="1986-01-01",progress=False,auto_adjust=True)["Close"].squeeze().dropna()
ser["SP500TR_yahoo"]=tr
px=pd.DataFrame(ser)
bench="SPTR" if "SPTR" in ser else "SP500TR_yahoo"
def st(p,b):
    p=p.dropna(); b=b.reindex(p.index).ffill().dropna(); p=p.reindex(b.index).dropna(); b=b.reindex(p.index)
    y=(p.index[-1]-p.index[0]).days/365.25
    c=(p.iloc[-1]/p.iloc[0])**(1/y)-1; cb=(b.iloc[-1]/b.iloc[0])**(1/y)-1
    v=p.pct_change().std()*252**.5; vb=b.pct_change().std()*252**.5
    dd=(p/p.cummax()-1).min(); ddb=(b/b.cummax()-1).min()
    m=p.resample("ME").last().pct_change().dropna(); mb=b.resample("ME").last().pct_change().reindex(m.index)
    ex=(m-mb).dropna(); t=ex.mean()/ex.std()*len(ex)**.5
    return c,cb,v,vb,dd,ddb,t,len(ex),p.index[0].date()
for lo,label in [("1986-01-01","full history"),("2010-01-01","since 2010"),("2019-01-01","since 2019")]:
    print(f"\n== {label}, benchmark {bench} ==")
    print(f"{'index':7}{'from':>11}{'CAGR':>7}{'bench':>7}{'diff':>7}{'vol':>6}{'bvol':>6}{'maxDD':>7}{'bDD':>7}{'t':>6}{'n':>5}")
    for s in ser:
        if s in (bench,"SP500TR_yahoo"): continue
        try:
            c,cb,v,vb,dd,ddb,t,n,d0=st(px[s].loc[lo:],px[bench].loc[lo:])
            print(f"{s:7}{str(d0):>11}{c*100:7.1f}{cb*100:7.1f}{(c-cb)*100:7.1f}{v*100:6.1f}{vb*100:6.1f}{dd*100:7.1f}{ddb*100:7.1f}{t:6.2f}{n:5d}")
        except Exception as e: print(s,"ERR",e)
