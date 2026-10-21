"""Present the fixed cash-only evidence and its validation limits."""
from html import escape
import json
from pathlib import Path
import re
import shutil

import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter
import pandas as pd

from cash_only import HERE, OUT, load_frozen

LABELS = {
    'SPY':'SPY buy and hold', 'gold':'Gold ETF buy and hold',
    'mix_1x':'Monthly 50/50 stocks + gold',
    'diversified_trend_1x':'Stocks/gold trend with cash',
    'gold_trend_1x':'Gold trend with cash',
    'relative_strength_1x':'Hold the stronger positive trend',
    'dip_ladder_hold_1x':'Capped gold dip buying · hold gains',
    'dip_ladder_target_1x':'Capped gold dip buying · small exits',
}
MONEY = lambda x:f'${x:,.0f}'
PERCENT = lambda x:f'{x*100:.1f}%'


def chart(year):
    fig,(ax,dd)=plt.subplots(2,1,figsize=(12,7),sharex=True,
        gridspec_kw={'height_ratios':[3,1]},layout='constrained')
    for name,color in [('mix_1x','#16636b'),('diversified_trend_1x','#b66438'),
                       ('SPY','#665d9c'),('gold','#9b7424')]:
        curve=pd.read_csv(OUT/f'allocation_etf_{year}_{name}_daily.csv',index_col=0,parse_dates=True)
        ax.plot(curve.index,curve.equity,label=LABELS[name],color=color,lw=1.7)
        dd.plot(curve.index,100*(curve.equity/curve.equity.cummax().clip(lower=10000)-1),color=color,lw=1.2)
    ax.set_title(f'$10,000 from {year} · cash-funded portfolios',loc='left',weight='bold',pad=12)
    ax.yaxis.set_major_formatter(FuncFormatter(lambda x,_:f'${x/1000:,.0f}k'))
    ax.set_ylabel('Value after modeled costs')
    ax.legend(frameon=False,ncol=2,loc='upper left',fontsize=9)
    dd.set_ylabel('Fall from peak (%)')
    for axis in [ax,dd]:
        axis.spines[['top','right']].set_visible(False)
        axis.grid(axis='y',alpha=.16)
    fig.savefig(OUT/f'cash-only-{year}.svg')
    fig.savefig(OUT/f'cash-only-{year}.png',dpi=150)
    plt.close(fig)


def main():
    p=load_frozen()
    d=json.loads((OUT/'cash_only_results.json').read_text())
    from cash_only import digest
    if d['protocol_sha256']!=digest(HERE/'cash_only_protocol.json'):
        raise ValueError('Rerun cash_only.py after changing the audit protocol')
    names=['SPY','gold','mix_1x','diversified_trend_1x','gold_trend_1x',
           'relative_strength_1x','dip_ladder_hold_1x','dip_ladder_target_1x']
    if set(names)!={s['name'] for s in p['eligible_specs']}:
        raise ValueError('Report and frozen candidate family differ')
    summary=lambda year,name:d['summaries'][f'etf_{year}_{name}']
    panels=[]
    for year in [2019,2022,2020,2006]:
        chart(year)
        rows=[]
        best=max(summary(year,b)['ending_equity'] for b in ['SPY','gold'])
        for name in names:
            s=summary(year,name)
            beat='Benchmark' if name in ['SPY','gold'] else ('Yes' if s['ending_equity']>best else 'No')
            rows.append(f'<tr><th><a href="allocation_etf_{year}_{name}_daily.csv">{LABELS[name]}</a></th><td>{MONEY(s["ending_equity"])}</td><td>{PERCENT(s["cagr"])}</td><td>{PERCENT(s["max_drawdown_daily"])}</td><td>{s["trade_days"]:,}</td><td>{beat}</td></tr>')
        panels.append(f'<section data-panel="{year}" {"" if year==2019 else "hidden"}><h2>From {year} through 16 October 2026</h2><div class="scroll"><table><thead><tr><th>Rule · all eight comparisons</th><th>Ending $10,000</th><th>Per year</th><th>Fall from peak</th><th>Trade days</th><th>Beat both?</th></tr></thead><tbody>{"".join(rows)}</tbody></table></div><p class="small">USD, same dates, 0.10% per side, no deposits, before tax and FX. Fund expenses are embedded; idle cash earns zero. Daily closes miss intraday losses. Click a rule to inspect every holding day.</p><img class="chart" src="cash-only-{year}.svg" alt="Cash-funded monthly mix and trend strategy against SPY and gold, with drawdowns"><p><a href="cash-only-{year}.png" download>Download chart</a></p></section>')
    rolling=[]
    for name in names[2:]:
        x=d['rolling']['36'][name]
        rolling.append(f'<tr><th><a href="cash_only_results.json">{LABELS[name]}</a></th><td>{x["beat_both"]} / {x["windows"]}</td><td>{PERCENT(x["fraction"])}</td></tr>')
    trials=[]
    for r in d['trial_inventory']:
        trials.append(f'<tr><th><a href="{r["file"]}">{escape(r.get("stage",r["file"].replace("_snapshot.json","")))}</a></th><td>{escape(", ".join(f"{key}: {value}" for key,value in r["groups"].items()))}</td></tr>')
    checks=list(d['checks'].values())
    rows_count=sum(x['sessions'] for x in checks)
    trade_count=sum(x['trade_days'] for x in checks)
    css=re.search(r'<style>(.*?)</style>',(OUT/'redesign-archive.html').read_text(),re.S).group(1)
    css+='td{white-space:normal}th,td{vertical-align:top}'
    html=f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Aurel research · Cash only, no validated edge</title><style>{css}</style></head><body>
<header><b>AUREL / RESEARCH</b><span class="pill">Cash only · development evidence</span></header>
<div class="layout"><aside><h2>Current limits</h2><div class="stat"><b>0</b><span>borrowing or leveraged products permitted</span></div><div class="stat"><b>8</b><span>unchanged cash-only comparisons</span></div><div class="stat"><b>0</b><span>independently validated winners</span></div><p class="small">All inspected history remains development data. This audit adds no strategy or parameter search.</p><p><a href="cash_only_protocol.json">Frozen audit plan</a><br><a href="cash_only_results.json">Audit and results</a><br><a href="CASH_ONLY_FINDINGS.txt">Adversarial findings</a><br><a href="redesign-bundle.zip">Download evidence</a></p></aside><main>
<h1>Cash-only results.<br>No validated advantage yet.</h1>
<p>Every current candidate uses owned capital only. The existing cash-only rules do not establish a reliable advantage over both <a href="allocation_etf_2019_SPY_daily.csv">SPY</a> and <a href="allocation_etf_2019_gold_daily.csv">gold</a>. The earlier leveraged comparisons are excluded from the shortlist and retained in the <a href="redesign-archive.html">historical archive</a>.</p>
<div class="callout"><p><strong>The useful trade-off:</strong> a monthly 50/50 stock/gold mix ended at {MONEY(summary(2019,'mix_1x')['ending_equity'])} from $10,000 in 2019, versus {MONEY(summary(2019,'SPY')['ending_equity'])} in SPY and {MONEY(summary(2019,'gold')['ending_equity'])} in gold. Its largest daily-close fall was {PERCENT(summary(2019,'mix_1x')['max_drawdown_daily'])}, compared with {PERCENT(summary(2019,'SPY')['max_drawdown_daily'])} for SPY. It offers a historical risk/return trade-off; it does not meet the requested return objective.</p></div>
<div class="switch" aria-label="Investment start"><button data-year="2019" aria-pressed="true">From 2019</button><button data-year="2022" aria-pressed="false">From 2022</button><button data-year="2020" aria-pressed="false">From 2020</button><button data-year="2006" aria-pressed="false">From 2006</button></div>
{''.join(panels)}
<h2>Why a good-looking endpoint is insufficient</h2>
<p>The 50/50 mix beats both benchmarks from 2006 and 2020, loses to SPY from 2019, and loses to gold from 2022. Every other cash-only alternative also trails gold from 2022. Selecting the favorable start would change the story without improving the strategy.</p>
<p>Across the existing 2006-start history, the mix beat both in only 11 of 214 overlapping three-year windows. These windows are dependent observations, not 214 separate trials or a probability of future success.</p>
<div class="scroll"><table><thead><tr><th>Cash-only alternative</th><th>Three-year wins over both</th><th>Share of windows</th></tr></thead><tbody>{''.join(rolling)}</tbody></table></div>
<h2>How we keep the next test honest</h2>
<ol><li><strong>Freeze the idea first.</strong> Record the reason it might work, every variant, costs, dates and rejection criteria before examining results. Changing it afterward creates a new exploratory round.</li>
<li><strong>Keep the failures.</strong> Maintain a run register across ideas and parameter changes. Stop when the declared family fails; do not keep tweaking until one chart wins.</li>
<li><strong>Separate causality from validation.</strong> Trading on yesterday's information prevents one type of error. It does not undo our knowledge of how these years turned out. All existing periods are development evidence.</li>
<li><strong>Stress the same rules.</strong> Require nearby settings, different regimes, higher costs, delayed execution and another price source before advancing a candidate. Existing cash-only coverage is incomplete; no robustness pass is claimed.</li>
<li><strong>Require independent evidence.</strong> A quarantined sample must really be unseen, or results must arrive after a fixed forward plan. A short paper rehearsal can check execution, but cannot establish a lasting return advantage.</li></ol>
<p>This limits overfitting; it cannot guarantee its absence. We have not registered an independent holdout or a forward review date. No learned AI predictor is validated here, and a modern model's knowledge of historical outcomes would require separate leakage controls.</p>
<p>The <a href="https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf">Deflated Sharpe Ratio paper</a> explains how trying many alternatives inflates apparent performance. The <a href="https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf">Probability of Backtest Overfitting paper</a> addresses selection risk. Our complete trial history is not known, so a precise confidence percentage calculated from only these eight rows would be misleading.</p>
<details><summary>Known research history and trial accounting</summary><p>These are counts of saved simulation rows, including repeated starts, controls and stresses. They are not independent hypotheses. Earlier related research and informal design decisions are not completely inventoried. No global multiple-testing adjustment is claimed.</p><div class="scroll"><table><thead><tr><th>Saved research stage</th><th>Recorded result groups</th></tr></thead><tbody>{''.join(trials)}</tbody></table></div><p>The volatility-only round followed the first redesign outputs; the displayed variant later changed from its declared 15% target to a better-looking 20% target. That sequence is selection, not independent confirmation. Both are now ineligible because of leverage.</p></details>
<h2>What was checked, and what remains open</h2>
<p>The review found no meaningful borrowing in the saved cash-only curves. It did identify an execution shortcut: trade quantities are calculated from opening prices and filled at those same prices. Real orders would need quantities fixed before the auction, or later prices after the open. That difference remains untested.</p>
<div class="scroll"><table><thead><tr><th>Verified</th><th>Assumed</th><th>Not checked / not established</th></tr></thead><tbody>
<tr><th><a href="cash_only_results.json">32 saved cash-only curves</a>: {rows_count:,} holding rows and {trade_count:,} trade days audited for cash, positions, exposure, financing and accounting.</th><td>Floating-point cash tolerance $0.0000001; negative cash beyond this fails.</td><td>Actual broker buying power, settlement and sell-before-buy sequencing.</td></tr>
<tr><th><a href="cash_only_protocol.json">73 source, input and result hashes</a> freeze the existing eight definitions and their evidence; changed inputs stop this audit.</th><td>Historical adjusted ETF prices are a usable research proxy.</td><td>Point-in-time corporate-action availability and the unresolved daily SPY provider discrepancy.</td></tr>
<tr><th><a href="CASH_ONLY_FINDINGS.txt">Independent adversarial review</a> of cash funding, causal execution and selection evidence.</th><td>Fractional simultaneous opening-price rebalancing, 10 basis points per side, no cash interest.</td><td>Reliable outperformance, tax/FX/minimum fees, intraday drawdown, and stateful dip-ladder latency.</td></tr>
</tbody></table></div>
<p>Minimum saved cash was {min(x['minimum_cash'] for x in checks):.2e} dollars; maximum gross exposure was {max(x['maximum_exposure'] for x in checks):.16f} times equity. Those deviations are numerical roundoff. No economically meaningful borrowing was found in these curves. Owning assets outright still permits substantial losses: the 50/50 mix's long-history daily drawdown was {PERCENT(summary(2006,'mix_1x')['max_drawdown_daily'])}.</p>
<details><summary>Every research path and its current eligibility</summary><div class="scroll"><table><thead><tr><th>Path</th><th>Current treatment</th></tr></thead><tbody>
<tr><th><a href="cash_only_protocol.json">Cash-only audit</a></th><td>Exactly eight unchanged definitions; all four start periods checked, every eligible row displayed.</td></tr>
<tr><th><a href="redesign-archive.html">Legacy redesign and allocation runners</a></th><td>Retained for reproduction. All 16 cap-above-one rules excluded from the current shortlist.</td></tr>
<tr><th><a href="redesign_results.json">Annual walk-forward selector</a></th><td>Excluded: its candidate universe includes leveraged rules. Not silently retrained.</td></tr>
<tr><th><a href="index.html">Original grid</a> and <a href="loss-controls.html">loss-control experiments</a></th><td>Archived only; margined instruments violate the cash-only policy.</td></tr>
<tr><th><a href="README.txt">Live Aurel system</a></th><td>Outside this research change; no deployment, broker connection or trade.</td></tr>
</tbody></table></div></details>
<h2>Decision</h2><p>Do not promote this grid or its cash-only variants as a proven replacement for passive investing. Preserve the simpler stock/gold mix as a comparison portfolio. Any further strategy needs a distinct economic rationale and a predeclared test; adding knobs to rescue these results would increase the overfitting risk.</p>
<p><a href="cash_only_protocol.json">Audit protocol</a> · <a href="cash_only_results.json">Results and eligibility checks</a> · <a href="CASH_ONLY_FINDINGS.txt">Review findings</a> · <a href="redesign-bundle.zip">Code, inputs and all results</a></p>
<footer>Local research · <a href="https://github.com/claudiucelfilip/aurel3">Aurel3 repository</a> · branch <code>research/gold-grid-20261021</code><br>Source: <code>/Users/claudiu/Sites/aurel3-gold-grid/research/gold_grid</code><br>Output: <code>data/gold_grid/results/redesign.html</code></footer></main></div>
<script>document.querySelectorAll('[data-year]').forEach(button=>button.addEventListener('click',()=>{{const year=button.dataset.year;document.querySelectorAll('[data-year]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.year===year)));document.querySelectorAll('[data-panel]').forEach(p=>p.hidden=p.dataset.panel!==year)}}));</script></body></html>'''
    (OUT/'redesign.html').write_text(html)
    for name in ['cash_only_protocol.json','cash_only_snapshot.json','CASH_ONLY_FINDINGS.txt','README.txt',
                 'result_snapshot.json','loss_control_snapshot.json','profit_lock_snapshot.json','redesign_snapshot.json']:
        shutil.copy(HERE/name,OUT/name)


if __name__=='__main__':
    main()
