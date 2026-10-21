"""Generate the local, inspectable comparison without publishing externally."""
from html import escape
import json
from pathlib import Path
import shutil
import zipfile

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter
import pandas as pd

from redesign import OUT

R = json.loads((OUT/'redesign_results.json').read_text())
A = json.loads((OUT/'allocation_results.json').read_text())
V = json.loads((OUT/'redesign_audit.json').read_text())
LABELS = {
    'SPY':'SPY buy and hold','gold':'Gold ETF buy and hold',
    'mix_1x':'50/50 SPY + gold · no borrowing',
    'mix_1p5x':'50/50 SPY + gold · 1.5× exposure',
    'mix_2x':'50/50 SPY + gold · 2× exposure',
    'balanced_vol20_1p5x':'Volatility control · 20% target, 1.5× cap',
    'balanced_vol15_1p5x':'Volatility control · 15% target, 1.5× cap',
    'balanced_vol15_2x':'Volatility control · 15% target, 2× cap',
    'balanced_vol20_2x':'Volatility control · 20% target, 2× cap',
    'diversified_trend_1p5x':'Trend portfolio · 15% target, 1.5× cap',
    'dip_ladder_hold_1x':'Capped gold dip ladder · hold gains',
    'dip_ladder_target_1x':'Capped gold dip ladder · take small gains',
    'dip_ladder_hold_1p5x':'Capped gold dip ladder · 1.5× cap'}
USD = lambda x:f'${x:,.0f}'
PCT = lambda x:f'{x*100:.1f}%'


def result(year,name):
    return V['additional_2019_results'][name] if year==2019 else A['main'][f'etf_{year}_{name}']


def label(name):
    return LABELS.get(name,name.replace('_',' '))


def row(year,name):
    s=result(year,name)
    href=f'allocation_etf_{year}_{name}_daily.csv'
    beats=s['ending_equity']>max(result(year,x)['ending_equity'] for x in ['SPY','gold'])
    return f'<tr><th><a href="{href}">{escape(label(name))}</a></th><td>{USD(s["ending_equity"])}</td><td>{PCT(s["cagr"])}</td><td>{PCT(s["max_drawdown_daily"])}</td><td>{s["trade_days"]:,}</td><td>{"Yes" if beats else "No"}</td></tr>'


def table(year,names):
    return '<div class="scroll"><table><thead><tr><th>Rule</th><th>Ending $10,000</th><th>Per year</th><th>Fall from peak</th><th>Trade days</th><th>Beat both?</th></tr></thead><tbody>'+''.join(row(year,n) for n in names)+'</tbody></table></div>'


def chart(year):
    fig,(ax,dd)=plt.subplots(2,1,figsize=(12,7),sharex=True,gridspec_kw={'height_ratios':[3,1]},layout='constrained')
    for name,title,color in [('mix_1p5x','Monthly 50/50, 1.5×','#16636b'),
                             ('balanced_vol20_1p5x','Volatility control, 1.5× cap','#b66438'),
                             ('SPY','SPY','#665d9c'),('gold','Gold ETF','#9b7424')]:
        c=pd.read_csv(OUT/f'allocation_etf_{year}_{name}_daily.csv',index_col=0,parse_dates=True)
        ax.plot(c.index,c.equity,label=title,color=color,lw=1.7)
        peak=c.equity.cummax().clip(lower=10000)
        dd.plot(c.index,100*(c.equity/peak-1),color=color,lw=1.2)
    ax.set_title(f'$10,000 invested at the first session of {year}',loc='left',weight='bold',pad=12)
    ax.yaxis.set_major_formatter(FuncFormatter(lambda x,_:f'${x/1000:,.0f}k'))
    ax.set_ylabel('Value after modeled costs')
    ax.legend(frameon=False,ncol=2,loc='upper left',fontsize=9)
    dd.set_ylabel('Fall from peak (%)')
    for chart_axis in [ax,dd]:
        chart_axis.spines[['top','right']].set_visible(False)
        chart_axis.grid(axis='y',alpha=.16)
    fig.savefig(OUT/f'redesign-{year}.svg')
    fig.savefig(OUT/f'redesign-{year}.png',dpi=150)
    plt.close(fig)


def main():
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'figure.facecolor':'#fafbf8','axes.facecolor':'#fafbf8'})
    names=['SPY','gold','mix_1x','mix_1p5x','balanced_vol20_1p5x','diversified_trend_1p5x','dip_ladder_hold_1x']
    all_names=[s['name'] for s in R['protocol']['strategies']+R['protocol']['controls']+A['protocol']['variants']]
    panels=[]
    for year in [2019,2022,2020,2006]:
        chart(year)
        panels.append(f'<section data-panel="{year}" {"" if year==2019 else "hidden"}><h2>From {year} through 16 October 2026</h2>{table(year,names)}<p class="small">USD, no deposits, no taxes. Same dates and costs for every row. Gold means actual GLD shares; fund expenses are already in its prices. Daily drawdowns can miss larger intraday losses.</p><img class="chart" src="redesign-{year}.svg" alt="SPY, gold ETF, leveraged monthly mix and volatility-controlled mix, including drawdowns"><p><a href="redesign-{year}.png" download>Download chart</a></p><details><summary>All 24 rules and controls for this period</summary>{table(year,all_names)}</details></section>')
    pass_names=[]
    for name in all_names:
        if name in ['SPY','gold']:
            continue
        if all(result(y,name)['max_drawdown_daily']<=.25 and result(y,name)['ending_equity']>max(result(y,b)['ending_equity'] for b in ['SPY','gold']) for y in [2020,2022]):
            pass_names.append(name)
    checks=list(A['verification'].values())+list(V['verification'].values())
    num_fills=sum(x['trade_days'] for x in checks)
    max_error=max(x['max_error'] for x in checks)
    cost_rows=''.join(f'<tr><th><a href="redesign_audit.json">{escape(label(s["name"]))}</a></th><td>{PCT(s["borrowing_rate"])}</td><td>{USD(s["ending_equity"])}</td><td>{PCT(s["max_drawdown_daily"])}</td></tr>' for s in V['funding_diagnostic'] if s['start']==2022)
    rolling_rows=''.join(f'<tr><th><a href="allocation_results.json">{escape(label(name))}</a></th><td>{A["rolling"]["24"][name]["beat_both"]} / {A["rolling"]["24"][name]["windows"]} ({PCT(A["rolling"]["24"][name]["fraction"])})</td><td>{A["rolling"]["36"][name]["beat_both"]} / {A["rolling"]["36"][name]["windows"]} ({PCT(A["rolling"]["36"][name]["fraction"])})</td></tr>' for name in ['mix_1p5x','balanced_vol20_1p5x','diversified_trend_1p5x'])
    old_rows=''.join(f'<tr><th><a href="allocation_old_{name}_daily.csv">{escape(label(name))}</a></th><td>{USD(A["old_period"][name]["ending_equity"])}</td><td>{PCT(A["old_period"][name]["cagr"])}</td><td>{PCT(A["old_period"][name]["max_drawdown_daily"])}</td></tr>' for name in names)
    css='''*{box-sizing:border-box}body{margin:0;background:#fafbf8;color:#203339;font-family:Verdana,sans-serif;font-size:14px;line-height:1.6}a{color:#165f72;text-underline-offset:3px}header{padding:20px 32px;border-bottom:1px solid #d6dfd9;display:flex;justify-content:space-between;gap:20px}header b{letter-spacing:2px;font-size:12px}.pill{background:#f4e5ca;color:#734619;border-radius:20px;padding:4px 12px;font-size:12px}.layout{display:grid;grid-template-columns:240px minmax(0,1fr);gap:38px;max-width:1530px;margin:auto;padding:32px}aside{border-right:1px solid #d6dfd9;padding-right:28px}h1{font-family:Georgia,serif;font-size:36px;line-height:1.2;margin:0 0 18px}h2{font-family:Georgia,serif;font-size:23px;margin:30px 0 14px}aside h2{font-size:22px;margin-top:0}.stat{padding:18px 0;border-bottom:1px solid #d6dfd9}.stat b{display:block;font-size:30px;line-height:1.1}.stat span,.small{font-size:12px;color:#5d7074}.callout{border-left:4px solid #b27034;background:#f4eee3;padding:14px 20px;margin:20px 0}.callout p{margin:4px 0}.switch{display:flex;flex-wrap:wrap;gap:8px;margin:24px 0}button{cursor:pointer;font:inherit;border:1px solid #9aabad;border-radius:5px;background:transparent;padding:8px 15px;color:#24494f}button[aria-pressed=true]{background:#16636b;color:white;border-color:#16636b}button:focus-visible,a:focus-visible,summary:focus-visible{outline:3px solid #b97732;outline-offset:3px}.scroll{overflow:auto;border:1px solid #d6dfd9;border-radius:7px}table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums;font-size:12px}th,td{padding:12px 10px;border-bottom:1px solid #d6dfd9;text-align:right;white-space:nowrap}th:first-child{text-align:left;white-space:normal;min-width:220px}thead{background:#e9eeea}tbody tr:last-child td,tbody tr:last-child th{border-bottom:0}tbody th{font-weight:normal}.chart{width:100%;height:auto;margin-top:18px}details{margin:16px 0;border-top:1px solid #d6dfd9;padding-top:12px}summary{cursor:pointer;font-weight:bold;margin-bottom:12px}code{font-size:12px;overflow-wrap:anywhere}footer{margin-top:28px;border-top:1px solid #d6dfd9;padding-top:18px;color:#5d7074;font-size:12px}[hidden]{display:none!important}@media(max-width:1000px){.layout{grid-template-columns:1fr;padding:20px;gap:18px}aside{border:0;padding:0;display:grid;grid-template-columns:repeat(3,1fr);gap:15px}aside h2,aside p{grid-column:1/-1}.stat{padding:4px 0}h1{font-size:29px}header{padding:16px 20px}}'''
    html=f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Aurel research · Can it beat SPY and gold?</title><style>{css}</style></head><body>
<header><b>AUREL / RESEARCH</b><span class="pill">Exploratory · no live changes</span></header><div class="layout"><aside><h2>What survived testing?</h2><div class="stat"><b>24</b><span>rules and comparison portfolios</span></div><div class="stat"><b>20 years</b><span>actual ETF history tested</span></div><div class="stat"><b>{len(pass_names)}</b><span>pass both-return + 25% drawdown screen</span></div><p class="small">Two documented rounds. Every candidate is disclosed. History was already inspected, so this is development evidence.</p><p><a href="index.html">Original grid</a><br><a href="loss-controls.html">Earlier loss controls</a><br><a href="redesign-bundle.zip">Download this study</a></p></aside><main>
<h1>Higher returns are possible.<br>The trade-off is still substantial.</h1>
<p>A modestly leveraged stock/gold portfolio beat both benchmarks in the headline backtests. The repairs closest to the original grid did not. None of the 24 portfolios met the combined goal of beating both benchmarks from 2020 and 2022 while keeping daily drawdown at or below 25%.</p>
<div class="callout"><p><strong>The strongest simple alternative:</strong> invest $7,500 in SPY and $7,500 in gold for each $10,000 of account equity, borrowing $5,000. Rebalance monthly. From 2019, $10,000 became {USD(result(2019,'mix_1p5x')['ending_equity'])}, versus {USD(result(2019,'SPY')['ending_equity'])} in SPY and {USD(result(2019,'gold')['ending_equity'])} in gold. Its largest fall from a peak, measured at daily closes, was {PCT(result(2019,'mix_1p5x')['max_drawdown_daily'])}; extending back to 2006 raises that to {PCT(result(2006,'mix_1p5x')['max_drawdown_daily'])}.</p></div>
<div class="switch" aria-label="Investment start"><button data-year="2019" aria-pressed="true">From 2019</button><button data-year="2022" aria-pressed="false">From 2022</button><button data-year="2020" aria-pressed="false">From 2020</button><button data-year="2006" aria-pressed="false">From 2006</button></div>
{''.join(panels)}
<h2>What changed, in plain English</h2>
<p><strong>Grid repairs:</strong> buy only when gold is above its 200-session average; begin with half the permitted exposure and add two smaller purchases on further declines. Cap the total, exit a broken trend or a 5% basket loss at the next open, and wait 20 sessions after losing exits. Keeping winners helped, but still failed to beat both benchmarks. A next-open exit can lose more than 5%.</p>
<p><strong>Monthly portfolio:</strong> keep half of the investment exposure in stocks and half in gold. Neither is doubled merely because it falls. Exposure is reset to 1.5 times current equity at each monthly rebalance. It benefits from diversification and borrowing; it has no demonstrated prediction advantage.</p>
<p><strong>Volatility control:</strong> review the previous 60 sessions each week, give the less volatile asset more weight, and reduce total exposure when their combined estimated risk rises. Exposure stays below a 1.5× cap at each rebalance. A 20% volatility target is a sizing rule, not a maximum-loss promise. This cut the long-history daily drawdown to {PCT(result(2006,'balanced_vol20_1p5x')['max_drawdown_daily'])}, but gave up returns.</p>
<h2>The apparent edge has limits</h2><p>From 2006, the volatility-controlled version returned {PCT(result(2006,'balanced_vol20_1p5x')['cagr'])} per year, versus {PCT(result(2006,'SPY')['cagr'])} for SPY and {PCT(result(2006,'gold')['cagr'])} for gold. From 2022, its annual advantage over gold was only {(result(2022,'balanced_vol20_1p5x')['cagr']-result(2022,'gold')['cagr'])*100:.2f} percentage points. This is too small to call robust before implementation costs and taxes.</p>
<p>The monthly mix beat both benchmarks in just {PCT(A['rolling']['36']['mix_1p5x']['fraction'])} of the overlapping three-year windows. A strong final endpoint does not mean consistent superiority.</p><div class="scroll"><table><thead><tr><th>Portfolio</th><th>24-month windows beating both</th><th>36-month windows beating both</th></tr></thead><tbody>{rolling_rows}</tbody></table></div>
<h2>Borrowing costs can erase the win</h2><p>These fresh-2022 runs keep trading costs at 0.10% per side and vary only the annual borrowing rate. Gold buy and hold ends at {USD(result(2022,'gold')['ending_equity'])}. The wider stress also triples trading costs; every result is in the download.</p><div class="scroll"><table><thead><tr><th>Portfolio</th><th>Borrowing rate</th><th>Ending $10,000</th><th>Fall from peak</th></tr></thead><tbody>{cost_rows}</tbody></table></div>
<details><summary>Earlier market regimes: 2006–2019</summary><p>These tests end before the recent sample. They include the financial crisis and gold's long decline after 2011. They are a historical stress check, not an untouched holdout.</p><div class="scroll"><table><thead><tr><th>Rule</th><th>Ending $10,000</th><th>Per year</th><th>Fall from peak</th></tr></thead><tbody>{old_rows}</tbody></table></div></details>
<details><summary>All assumptions, checks and remaining gaps</summary><p><strong>Verified:</strong> 34 targeted tests pass across the original and new engines. Independent replay reconciles {num_fills:,} trade days in {len(checks)} curves; maximum account error is ${max_error:.9f}. Signals use earlier closes, orders use the following open, and synthetic tests perturb future prices to check that earlier orders stay unchanged. Calendar-time financing and estimated final exit costs are included.</p>
<p><strong>Data:</strong> actual adjusted SPY/GLD daily OHLC from an existing Yahoo Finance archive, copied locally and verified against its saved hashes. GLD history starts in November 2004; 2005 warms up the long test. Common terminal date is 16 October 2026. <a href="allocation_etf_inputs.csv">Inspect the adjusted ETF inputs</a>. No extra gold fee is subtracted from GLD, where expenses are already reflected.</p>
<p>The first round used the existing gold quote archive and Alpaca SPY data, with a 0.4% annual gold holding-cost proxy. SPY daily returns differ across the two providers by as much as 2.69 percentage points on some March 2020 dates. Their cumulative returns are very close, but the discrepancy can change risk signals. Its cause is unresolved; the headline tables use the ETF archive. Gold quote/ETF returns also differ through fund costs and quote timing. This is why the full second-source comparison is retained.</p>
<p><strong>Assumed:</strong> 5% annual borrowing on negative cash, 0.10% of traded value per side, fractional adjusted-price units, no interest on positive cash. The stated cap applies at rebalances; exposure can drift between them. Broker lending availability, maintenance rules, actual execution, minimum fees, tax and FX conversion remain unverified. These are investment simulations, not executable order instructions.</p>
<p><strong>Selection:</strong> 11 redesign rules and nine controls were frozen first. After seeing their results, four volatility-only rules were separately declared. The initial display choices were the 15%-target trend portfolio and the 15%-target volatility-only portfolio; both failed the recent return screen. The 20% variant and monthly mix are shown because they illustrate the trade-off, not as independently validated winners. 2019 starts and funding diagnostics were added afterward for context. The annual walk-forward selector also uses previously inspected history.</p>
<p><strong>Out of scope:</strong> a live Aurel3 recommendation policy, live trading, broker selection, an AI predictor and a claim of future outperformance. Additional execution-latency stress is excluded for the stateful dip ladder, which would need a pending-order model; it is tested for portfolio allocation rules and benchmarks. The original grid's minute-path drawdown and this report's daily-close drawdown have different sampling frequencies.</p></details>
<h2>Assessment</h2><p>The grid repair is not justified as a replacement for passive investing. The monthly stock/gold mix is a concrete alternative worth evaluating only if its borrowing cost and potential 47% historical drawdown are acceptable. The volatility-controlled version reduces that drawdown, but its recent excess return is thin. Neither is ready to be presented as a reliably superior trading algorithm.</p>
<p>Research motivation: <a href="https://www.aqr.com/Insights/Research/Journal-Article/A-Century-of-Evidence-on-Trend-Following-Investing">AQR's long-history trend study</a>, <a href="https://www.nber.org/papers/w22208">Moreira and Muir's volatility-managed portfolios</a>, and <a href="https://www.aqr.com/insights/research/alternative-thinking/hold-the-dip">AQR's dip-buying comparison</a>. These motivate tests; none endorses this particular construction. <a href="https://www.ssga.com/us/en/individual/etfs/spdr-gold-shares-gld">GLD's fund documentation</a> describes its gold exposure and embedded expenses.</p>
<p><a href="redesign_protocol.json">First-round rules</a> · <a href="allocation_protocol.json">Second-round rules</a> · <a href="redesign_results.json">First-round results</a> · <a href="allocation_results.json">ETF comparisons and stresses</a> · <a href="redesign_audit.json">Accounting and funding diagnostics</a> · <a href="redesign-bundle.zip">Code, inputs and results</a></p>
<footer>Local research · <a href="https://github.com/claudiucelfilip/aurel3">Aurel3 repository</a> · branch <code>research/gold-grid-20261021</code><br>Source: <code>/Users/claudiu/Sites/aurel3-gold-grid/research/gold_grid</code><br>Output: <code>data/gold_grid/results/redesign.html</code></footer></main></div>
<script>document.querySelectorAll('[data-year]').forEach(button=>button.addEventListener('click',()=>{{const year=button.dataset.year;document.querySelectorAll('[data-year]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.year===year)));document.querySelectorAll('[data-panel]').forEach(p=>p.hidden=p.dataset.panel!==year)}}));</script></body></html>'''
    notice='<div class="callout"><strong>Historical archive — leveraged strategies are excluded.</strong> This page preserves the earlier study. <a href="redesign.html">Open the current cash-only assessment.</a></div>'
    html=html.replace('<main>','<main>'+notice)
    (OUT/'redesign-archive.html').write_text(html)
    for name in ['redesign_protocol.json','allocation_protocol.json']:
        shutil.copy(Path('research/gold_grid')/name,OUT/name)
    snapshot={'redesign':R,'allocation':A,'audit':V}
    Path('research/gold_grid/redesign_snapshot.json').write_text(json.dumps(snapshot,indent=2,allow_nan=False))
    from cash_only_report import main as current_report
    current_report()
    with zipfile.ZipFile(OUT/'redesign-bundle.zip','w',zipfile.ZIP_DEFLATED) as bundle:
        for file in Path('research/gold_grid').glob('*'):
            if file.is_file():
                bundle.write(file,str(file))
        patterns=['redesign*','allocation*','cash*','CASH_ONLY_FINDINGS.txt','README.txt','*snapshot.json']
        for file in sorted({f for pattern in patterns for f in OUT.glob(pattern)}):
            if file.is_file() and file.suffix!='.zip':
                bundle.write(file,'results/'+file.name)
        for file in (OUT.parent/'etf_archive').glob('*'):
            bundle.write(file,'etf_archive/'+file.name)
    print('Report:',OUT/'redesign.html')
    print('Screen passes:',pass_names)
    print('Verified',len(checks),'curves,',num_fills,'trade days; error',max_error)


if __name__=='__main__':
    main()
