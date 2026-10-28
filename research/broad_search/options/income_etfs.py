import yfinance as yf, pandas as pd, numpy as np
px=yf.download(["SPY","QQQ","JEPI","XYLD","QYLD","JEPQ","SVOL","PUTW","DIVO","NUSI"],start="2013-01-01",auto_adjust=True,progress=False)["Close"]
def st(p,b):
    p=p.dropna(); b=b.reindex(p.index).ffill()
    y=(p.index[-1]-p.index[0]).days/365.25
    c=(p.iloc[-1]/p.iloc[0])**(1/y)-1; cb=(b.iloc[-1]/b.iloc[0])**(1/y)-1
    v=p.pct_change().std()*252**.5; dd=(p/p.cummax()-1).min()
    m=p.resample("ME").last().pct_change().dropna(); mb=b.resample("ME").last().pct_change().reindex(m.index)
    ex=(m-mb).dropna(); t=ex.mean()/ex.std()*len(ex)**.5
    return c,cb,v,dd,t,len(ex),p.index[0].date()
print(f"{'ETF':6}{'bench':6}{'from':>11}{'CAGR':>7}{'bench':>7}{'diff':>7}{'vol':>6}{'maxDD':>7}{'t':>6}{'n':>4}")
for s,b in [("JEPI","SPY"),("XYLD","SPY"),("PUTW","SPY"),("DIVO","SPY"),("SVOL","SPY"),("QYLD","QQQ"),("JEPQ","QQQ"),("NUSI","QQQ")]:
    if px[s].dropna().empty: print(s,"no data"); continue
    c,cb,v,dd,t,n,d0=st(px[s],px[b])
    print(f"{s:6}{b:6}{str(d0):>11}{c*100:7.1f}{cb*100:7.1f}{(c-cb)*100:7.1f}{v*100:6.1f}{dd*100:7.1f}{t:6.2f}{n:4d}")
