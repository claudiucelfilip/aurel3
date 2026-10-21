"""Generate a local, self-contained research dashboard and exportable plots."""
from html import escape
import json
from pathlib import Path
import shutil

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter
import pandas as pd


ROOT = Path('data/gold_grid/results')
DATA = json.loads((ROOT/'results.json').read_text())
PCT = lambda v: '—' if v is None else f'{v*100:.1f}%'
WIN = lambda v: '—' if v is None else f'{v*100:.3f}%'
USD = lambda v: f'${v:,.0f}'


def row(name,s,benchmark=False):
    wr = '—' if benchmark else WIN(s['win_rate'])
    dd = s['max_drawdown_daily'] if benchmark else s['max_drawdown']
    fate = 'Hold' if benchmark else ('Forced exit '+s['stopped_at'][:10] if s['forced_liquidations'] else
                                   (f"Open batch: {USD(s['open_cycle_pnl'])}" if s['open_ounces'] else 'No open batch'))
    return f'<tr><th>{name}</th><td>{USD(s["ending_equity"])}</td><td>{PCT(s["total_return"])}</td><td>{PCT(s["cagr"])}</td><td>{PCT(dd)}</td><td>{wr}</td><td>{fate}</td></tr>'


def charts(year):
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,
                         'axes.spines.right':False,'axes.edgecolor':'#c9d1d5','figure.facecolor':'#f9faf7',
                         'axes.facecolor':'#f9faf7','text.color':'#1e2a33','axes.labelcolor':'#1e2a33'})
    fig,ax=plt.subplots(figsize=(12,5),layout='constrained')
    for mode,color in [('doubling','#9c3c32'),('fixed','#246b72')]:
        f=pd.read_csv(ROOT/f'{year}_{mode}_low_first_daily.csv',index_col=0,parse_dates=True)
        ax.plot(f.index,f.equity,label=mode.title()+' grid',color=color,lw=2)
    for name,color in [('SPY','#665d9c'),('gold','#9b7424')]:
        f=pd.read_csv(ROOT/f'{year}_{name}_daily.csv',index_col=0,parse_dates=True)
        ax.plot(f.index,f.equity,label=name.title()+' buy & hold' if name=='gold' else 'SPY buy & hold',color=color,lw=2)
    ax.axhline(10000,color='#818d96',lw=1,ls=':')
    ax.yaxis.set_major_formatter(FuncFormatter(lambda x,_:f'${x/1000:,.0f}k'))
    ax.grid(axis='y',alpha=.15)
    ax.legend(loc='upper left',frameon=False,ncol=2,fontsize=11)
    ax.set_title('Gold grids vs SPY and gold · same $10,000 starting capital',loc='left',weight='bold',pad=16)
    ax.set_ylabel('Account value, including open losses')
    fig.savefig(ROOT/f'chart-{year}.svg')
    fig.savefig(ROOT/f'chart-{year}.png',dpi=150)
    plt.close(fig)


for year in [2019,2022]:
    charts(year)

panels=[]
for year in [2019,2022]:
    rows=''.join(row(label,DATA['baseline'][f'{year}_{mode}_low_first']) for label,mode in [('Doubling grid','doubling'),('Fixed-size grid','fixed')])
    rows+=row('SPY · adjusted daily',DATA['benchmarks'][f'{year}_SPY'],True)
    rows+=row('Gold · unleveraged spot',DATA['benchmarks'][f'{year}_gold'],True)
    path_rows=''.join(row(f'{mode.title()} · {path.replace("_"," ")}',DATA['baseline'][f'{year}_{mode}_{path}'])
                      for mode in ['doubling','fixed'] for path in ['low_first','high_first'])
    header='<thead><tr><th>Strategy</th><th>Ending value</th><th>Total return</th><th>Annualized</th><th>Worst fall</th><th>Batch win rate</th><th>State</th></tr></thead>'
    panels.append(f'''<section class="period" id="period-{year}" {'hidden' if year==2022 else ''}>
    <h2>Fresh account starting in {year}</h2><div class="table-scroll"><table>{header}<tbody>{rows}</tbody></table></div>
    <p class="note">Grid drawdown includes simulated intraminute lows. Benchmark drawdown uses daily closes and understates intraday falls. SPY uses adjusted prices; gold excludes storage/fund fees. The trading clocks differ.</p>
    <img class="chart" src="chart-{year}.svg?v=all-four" alt="Doubling grid, fixed-size grid, SPY buy and hold, and gold buy and hold from {year}">
    <p><a href="chart-{year}.png" download>Download chart</a> · <a href="{year}_doubling_low_first_daily.csv" download>Daily account values</a> · <a href="{year}_doubling_low_first_cycles.csv" download>Every batch</a> · <a href="{year}_doubling_low_first_ledger.csv.gz" download>Every fill</a></p>
    <details><summary>What changes when the high comes before the low?</summary><div class="table-scroll"><table>{header}<tbody>{path_rows}</tbody></table></div>
    <p>These are two assumed intraminute paths, not proven best/worst bounds. Tick data is required for exact quote ordering.</p></details></section>''')

sensitivity=''.join(f'<tr><td>{"Double" if s["settings"]["multiplier"]==2 else "Fixed"}</td><td>{s["settings"]["initial_ounces"]:g}</td><td>${s["settings"]["grid_dollars"]:g}</td><td>${s["settings"]["target_dollars"]:g}</td><td>{USD(s["ending_equity"])}</td><td>{PCT(s["max_drawdown"])}</td><td>{WIN(s["win_rate"])}</td><td>{s["stopped_at"][:10] if s["stopped_at"] else "Survived sample"}</td></tr>' for s in DATA['sensitivity'])
starts=''.join(f'<tr><td>{s["start_year"]}</td><td>{"Double" if s["settings"]["multiplier"]==2 else "Fixed"}</td><td>{USD(s["ending_equity"])}</td><td>{PCT(s["max_drawdown"])}</td><td>{s["stopped_at"][:10] if s["stopped_at"] else "Survived sample"}</td></tr>' for s in DATA['fresh_starts'])
stress=''.join(f'<tr><td>{s["label"].replace("_"," ")}</td><td>{"Double" if s["settings"]["multiplier"]==2 else "Fixed"}</td><td>{USD(s["ending_equity"])}</td><td>{PCT(s["max_drawdown"])}</td><td>{s["stopped_at"][:10] if s["stopped_at"] else "Survived sample"}</td></tr>' for s in DATA['stress'])
q=DATA['data_quality'];b=DATA['baseline']['2019_doubling_low_first'];fixed=DATA['baseline']['2019_fixed_low_first']
fills=sum(v['ledger_entries'] for v in DATA['verification'].values())
worst=max(v['maximum_cash_error'] for v in DATA['verification'].values())
failed=sum(x['forced_liquidations']>0 for x in DATA['sensitivity'] if x['settings']['multiplier']==2)
headline='Frequent wins did not prevent a forced exit.' if b['forced_liquidations'] else 'Baseline measured. Survival is not proof of an edge.'
html=f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Gold grid · baseline research</title><style>
:root{{--ink:#1e2a33;--muted:#5d6a73;--line:#d4dbdd;--paper:#f9faf7;--accent:#246b72;--danger:#9c3c32}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--paper);color:var(--ink);font:16px/1.6 'Avenir Next',system-ui,sans-serif}}
header{{padding:28px 40px;border-bottom:1px solid var(--line);display:flex;justify-content:space-between;align-items:center;background:#eaf0ed}}
header b{{font-size:21px;letter-spacing:1px}}.pill{{border:1px solid var(--accent);border-radius:20px;padding:5px 13px;color:var(--accent);font-size:13px}}
.layout{{max-width:1500px;margin:auto;display:grid;grid-template-columns:250px minmax(0,1fr);gap:38px;padding:32px 40px}}aside{{border-right:1px solid var(--line);padding-right:24px}}aside h2{{font-size:12px;text-transform:uppercase;letter-spacing:2px;color:var(--muted)}}
.stat{{padding:18px 0;border-bottom:1px solid var(--line)}}.stat b{{display:block;font:30px/1.2 Georgia,serif}}.stat span{{font-size:13px;color:var(--muted)}}
h1{{font:38px/1.15 Georgia,serif;max-width:760px;margin:5px 0 18px}}h2{{font-size:22px;line-height:1.3;margin-top:32px}}h3{{font-size:17px}}p{{max-width:920px}}a{{color:var(--accent);text-underline-offset:3px}}.note,.small{{font-size:13px;color:var(--muted)}}.callout{{padding:18px 22px;border-left:4px solid var(--danger);background:#f3e9e4;margin:24px 0}}.callout p{{margin:0}}
button{{font:inherit;border:1px solid var(--line);border-radius:5px;padding:10px 18px;background:transparent;cursor:pointer}}button[aria-pressed=true]{{background:var(--ink);color:white}}button:focus-visible,a:focus-visible,summary:focus-visible{{outline:3px solid #b87b21;outline-offset:3px}}.switch{{display:flex;gap:8px;margin:24px 0}}
table{{border-collapse:collapse;width:100%;font-size:13px;text-align:left;font-variant-numeric:tabular-nums}}th,td{{padding:12px 10px;border-bottom:1px solid var(--line);white-space:nowrap}}thead th{{font-size:11px;letter-spacing:1px;text-transform:uppercase;color:var(--muted)}}tbody th{{font-weight:600}}.table-scroll{{overflow:auto}}.chart{{width:100%;height:auto;margin-top:24px}}details{{border-top:1px solid var(--line);padding:18px 0}}summary{{cursor:pointer;font-weight:600}}code{{font-size:12px;overflow-wrap:anywhere}}li{{margin:8px 0}}footer{{border-top:1px solid var(--line);padding-top:20px;margin-top:30px;color:var(--muted);font-size:13px}}
@media(max-width:800px){{header{{padding:20px}}.layout{{display:block;padding:24px 20px}}aside{{border:0;display:flex;gap:22px;flex-wrap:wrap;margin-bottom:28px}}aside h2,aside .small{{width:100%}}.stat{{padding:4px 0;border:0}}.stat b{{font-size:24px}}h1{{font-size:30px}}}}
</style><header><b>AUREL / RESEARCH</b><span class="pill">Baseline only · no live trading</span></header>
<div class="layout"><aside><h2>2019 baseline / 21 Oct 2026</h2><div class="stat"><b>{q['rows']:,}</b><span>active one-minute observations</span></div>
<div class="stat"><b>{WIN(b['win_rate'])}</b><span>doubling · completed batches won</span></div><div class="stat"><b>{PCT(b['max_drawdown'])}</b><span>doubling · worst account fall</span></div>
<div class="stat"><b>{failed}/27</b><span>doubling settings forced to liquidate</span></div><p class="small">Verified: accounting and source overlap.<br>Assumed: missing strategy settings and intraminute paths.<br>Out of scope: loss limits and live deployment.</p></aside>
<main><h1>{headline}</h1><p>This implements the <a href="https://www.tiktok.com/@thequantbuilder/video/7699030814419422497">gold grid in your video</a>: buy falling gold, increase the next purchase, and close the batch after a rebound. The creator did not provide the exact settings, so this is a declared reconstruction.</p>
<div class="callout"><p><strong>This is the correct strategy family, not a reproduction of the advertised numbers.</strong> The earlier Nasdaq opening-move backtest does not apply. No AI or loss-limiting filter has been added.</p></div>
<div class="switch" aria-label="Choose start date"><button aria-pressed="true" data-year="2019">From 2019</button><button aria-pressed="false" data-year="2022">From 2022</button></div>
{''.join(panels)}
<h2>What exactly was tested?</h2><p>Start with $10,000. Buy 1 ounce. Buy 2, 4, 8… ounces whenever gold falls another $10 from the last purchase. Close when the batch earns $1 per ounce after costs. The fixed-size variant buys 1 ounce each time. Start the next batch in the following active minute.</p>
<p>Assumed margin: 20:1 leverage; reject unaffordable additions; force a complete exit when equity reaches 50% of used margin. Trading then stops for that account. There are no hidden deposits or restarts. A margin exit can leave cash; it is not necessarily a total wipeout.</p>
<p>Use observed bid/ask spreads, $0.035 commission and $0.05 slippage per ounce per side, plus 5% yearly financing on notional exposure. Financing is a research assumption, not a recovered historical swap schedule. All figures are before personal tax.</p>
<details><summary>All 54 parameter combinations — no winning setting selected</summary><p>Three starting sizes, three grid spacings, three targets, and two purchase-sizing rules. This checks sensitivity; it is not independent evidence for the best row.</p><div class="table-scroll"><table><thead><tr><th>Rule</th><th>Start oz</th><th>Spacing</th><th>Target/oz</th><th>Ending value</th><th>Worst fall</th><th>Win rate</th><th>State</th></tr></thead><tbody>{sensitivity}</tbody></table></div></details>
<details><summary>Fresh start in each year</summary><p>Each row is a separate $10,000 account held through the dataset end or its first margin exit. These are not combined or replenished returns.</p><div class="table-scroll"><table><thead><tr><th>Start</th><th>Rule</th><th>Ending value</th><th>Worst fall</th><th>State</th></tr></thead><tbody>{starts}</tbody></table></div></details>
<details><summary>Financing, slippage and leverage sensitivity</summary><div class="table-scroll"><table><thead><tr><th>Changed assumption</th><th>Rule</th><th>Ending value</th><th>Worst fall</th><th>State</th></tr></thead><tbody>{stress}</tbody></table></div></details>
<h2>Evidence and limits</h2><p><strong>Verified:</strong> eleven targeted tests cover weighted basket exits, doubling, fixed sizing, open losses, margin exits, price gaps, funding, costs, rejected orders, intraminute order and future-data isolation. An independent cash ledger reconciled {fills:,} fills across the eight main runs; the largest cash discrepancy was ${worst:.9f}.</p>
<p><strong>Data:</strong> {escape(q['start'])} through {escape(q['end'])}. The <a href="{q['mirror']}">archived Dukascopy dataset</a> was checked against {q['matching_original_archives']} original-provider daily archives ({q['matching_original_side_minutes']:,} side-minute observations), with exact price agreement on that sample. One unmatched quote minute was excluded. Entirely flat minutes were excluded because the archive does not include volume; that can also exclude genuine quiet minutes.</p>
<p><strong>Assumed:</strong> entry timing, spacing, sizing, target, margin policy, financing and quote ordering. Bid and ask highs/lows can occur at different instants. The two paths do not reconstruct actual ticks. Exact broker fills, swaps and partial liquidations remain unvalidated.</p>
<p><strong>Out of scope:</strong> optimizing loss limits, AI filters, taxes and live trading. All of this history has now been inspected; it must not later be called an untouched test set.</p>
<h2>Next experiment</h2><p>Keep this baseline fixed. Then compare capped additions, fixed exposure and a maximum batch loss on the same costs and data. Count the extra small losses as well as the avoided disasters. A lower drawdown alone is insufficient if it removes the profits.</p>
<p><a href="results.json" download>Full results JSON</a> · <a href="protocol.json" download>Frozen assumptions</a> · <a href="quality.json" download>Data checks</a> · <a href="research-bundle.zip" download>Code and result bundle</a></p>
<footer>Local research branch: <code>research/gold-grid-20261021</code><br>Workspace: <code>/Users/claudiu/Sites/aurel3-gold-grid/research/gold_grid</code><br>Raw data and results: <code>/Users/claudiu/Sites/aurel3-gold-grid/data/gold_grid</code></footer>
</main></div><script>document.querySelectorAll('[data-year]').forEach(b=>b.addEventListener('click',()=>{{document.querySelectorAll('[data-year]').forEach(x=>x.setAttribute('aria-pressed',String(x===b)));document.querySelectorAll('.period').forEach(x=>x.hidden=x.id!=='period-'+b.dataset.year)}}));</script></html>'''
(ROOT/'index.html').write_text(html)
shutil.copy('research/gold_grid/protocol.json',ROOT/'protocol.json')
shutil.copy('data/gold_grid/quality.json',ROOT/'quality.json')
print(ROOT/'index.html')
