import yfinance as yf, pandas as pd, numpy as np
T = ["SPY","MTUM","USMV","SPLV","VLUE","IWD","QUAL","SIZE","IWM","BIL"]
px = yf.download(T, start="2011-01-01", auto_adjust=True, progress=False)["Close"].dropna(how="all")
print("rows", len(px), "last", px.index[-1].date())
print("first valid:", {t: str(px[t].first_valid_index().date()) for t in T})
def stats(p, s):
    p=p.dropna(); s=s.reindex(p.index).ffill()
    yrs=(p.index[-1]-p.index[0]).days/365.25
    cagr=(p.iloc[-1]/p.iloc[0])**(1/yrs)-1
    scagr=(s.iloc[-1]/s.iloc[0])**(1/yrs)-1
    r=p.pct_change().dropna(); vol=r.std()*np.sqrt(252)
    dd=(p/p.cummax()-1).min()
    m=p.resample("ME").last().pct_change().dropna(); ms=s.resample("ME").last().pct_change().dropna().reindex(m.index)
    ex=m-ms; t=ex.mean()/ex.std()*np.sqrt(len(ex))
    return cagr, scagr, vol, dd, t, len(ex)
for lo,hi,label in [("2013-07-18","2026-12-31","since 2013-07 (common start)"),("2019-01-01","2026-12-31","since 2019"),("2023-01-01","2026-12-31","since 2023")]:
    print(f"\n== {label} ==")
    print(f"{'tkr':6}{'CAGR':>8}{'SPY':>8}{'diff':>8}{'vol':>7}{'maxDD':>8}{'t(excess vs SPY, monthly)':>28}{'n':>5}")
    for t in T:
        if t in ("SPY","BIL"): continue
        sub=px.loc[lo:hi]
        c,sc,v,dd,ts,n=stats(sub[t],sub["SPY"])
        print(f"{t:6}{c*100:8.1f}{sc*100:8.1f}{(c-sc)*100:8.1f}{v*100:7.1f}{dd*100:8.1f}{ts:28.2f}{n:5d}")
