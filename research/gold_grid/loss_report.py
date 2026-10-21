"""Compare loss limits and profit locks with the original grid and benchmarks."""
from html import escape
import json
from pathlib import Path
import re
import shutil

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter
import pandas as pd


ROOT = Path('data/gold_grid/results')
R = json.loads((ROOT/'loss_controls.json').read_text())
P = json.loads((ROOT/'profit_locks.json').read_text())
MAIN = R['protocol']['display_variant_chosen_before_results']
LOCK = P['protocol']['display_variant_chosen_before_profit_lock_results']
LABELS = {
    'entries_4':'At most four purchases', 'exposure_2x':'At most 2× exposure on new buys',
    'batch_loss_2pct':'Exit batch at 2% loss','batch_loss_5pct':'Exit batch at 5% loss',
    'combined_2pct':'Four buys + 2× exposure + 2% loss',
    'combined_5pct':'Four buys + 2× exposure + 5% loss',
    'combined_2pct_pause24':'Combined 2% loss + 24-hour pause',
    'combined_5pct_pause24':'Combined 5% loss + 24-hour pause',
    'combined_5pct_pause24_account20':'Combined 5% + pause + 20% account exit'}
USD = lambda v:f'${v:,.0f}'
PCT = lambda v:f'{v*100:.1f}%'


def control_name(year,mode,path,variant=MAIN):
    return f'controls_{year}_{mode}_{path}_{variant}'


def lock_name(year,mode,path,activation=LOCK['activation_multiple'],drawdown=LOCK['trailing_drawdown_fraction']):
    return f'profit_lock_{year}_{mode}_{path}_{activation:g}_{drawdown:g}'


def state(s):
    if s.get('stopped'):
        reason=s.get('stop_reason') or ('margin exit' if s.get('forced_liquidations') else 'Trading stopped')
        return escape(reason)+' · '+s['stopped_at'][:10]
    if s.get('open_ounces',0):
        return 'Open batch '+USD(s['open_cycle_pnl'])
    return 'Trading through sample end'


def row(label,s,link=None,benchmark=False):
    label = f'<a href="{escape(link)}">{escape(label)}</a>' if link else escape(label)
    dd = s['max_drawdown_daily'] if benchmark else s['max_drawdown']
    stops = '—' if benchmark else str(s.get('batch_loss_exits',0))
    status = 'Buy and hold' if benchmark else state(s)
    return f'<tr><th>{label}</th><td>{USD(s["ending_equity"])}</td><td>{PCT(s["total_return"])}</td><td>{PCT(dd)}</td><td>{stops}</td><td>{status}</td></tr>'


def table(rows):
    return '<div class="table-scroll"><table><thead><tr><th>Rule</th><th>Ending value</th><th>Return</th><th>Worst fall</th><th>Batch stops</th><th>Final state</th></tr></thead><tbody>'+rows+'</tbody></table></div>'


def chart(year,mode):
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,
                         'axes.spines.right':False,'figure.facecolor':'#f9faf7','axes.facecolor':'#f9faf7'})
    fig,ax=plt.subplots(figsize=(12,5.5),layout='constrained')
    sources=[(f'{year}_{mode}_low_first','Original grid','#859198','--'),
             (control_name(year,mode,'low_first'),'2% loss + caps + pause','#246b72','-'),
             (lock_name(year,mode,'low_first'),'Trail 20% after doubling account','#1d4e89','-'),
             (f'{year}_SPY','SPY buy & hold','#665d9c','-'),
             (f'{year}_gold','Gold buy & hold','#9b7424','-')]
    for name,label,color,style in sources:
        f=pd.read_csv(ROOT/f'{name}_daily.csv',index_col=0,parse_dates=True)
        ax.plot(f.index,f.equity,label=label,color=color,lw=1.8,ls=style)
    ax.axhline(10000,color='#89959b',ls=':',lw=1)
    ax.yaxis.set_major_formatter(FuncFormatter(lambda x,_:f'${x/1000:,.0f}k'))
    ax.set_title(f'{mode.title()}-size grid · $10,000 from {year}' if mode=='fixed' else f'Doubling grid · $10,000 from {year}',loc='left',weight='bold',pad=16)
    ax.set_ylabel('Account value, including open losses')
    ax.grid(axis='y',alpha=.15)
    ax.legend(frameon=False,loc='upper left',ncol=2,fontsize=9)
    fig.savefig(ROOT/f'loss-controls-{year}-{mode}.svg')
    fig.savefig(ROOT/f'loss-controls-{year}-{mode}.png',dpi=150)
    plt.close(fig)


panels=[]
for year in [2019,2022]:
    for mode in ['fixed','doubling']:
        chart(year,mode)
        c=control_name(year,mode,'low_first')
        p=lock_name(year,mode,'low_first')
        b=f'{year}_{mode}_low_first'
        rows=row('Original grid',R['baseline'][b],b+'_cycles.csv')
        rows+=row('Caps + 2% batch loss + 24-hour pause',R['main'][c],c+'_cycles.csv')
        rows+=row('Trail 20% after account reaches $20,000',P['main'][p],p+'_cycles.csv')
        for name in ['SPY','gold']:
            rows+=row(('Gold' if name=='gold' else name)+' buy and hold',R['benchmarks'][f'{year}_{name}'],f'{year}_{name}_daily.csv',True)
        all_controls=''.join(row(LABELS[s['variant']]+' · '+s['path'].replace('_',' '),s,n+'_cycles.csv')
                             for n,s in R['main'].items() if s['year']==year and s['mode']==mode)
        all_locks=''.join(row(f'Activate at {s["settings"]["drawdown_activation_multiple"]:g}× · trail {PCT(s["settings"]["account_drawdown_fraction"])} · '+s['path'].replace('_',' '),s,n+'_cycles.csv')
                          for n,s in P['main'].items() if s['year']==year and s['mode']==mode)
        panels.append(f'''<section class="result-panel" data-period="{year}" data-mode="{mode}" {'' if year==2019 and mode=='fixed' else 'hidden'}>
        <h2>{'Fixed-size' if mode=='fixed' else 'Doubling'} purchases · fresh account from {year}</h2>{table(rows)}
        <p class="note">Both displayed controls were specified before their own runs. Every other setting is below. Figures use the low-first path; the alternate path is included in the full tables. Benchmark drawdowns use daily closes; strategy drawdowns include simulated intraminute lows.</p>
        <img class="chart" src="loss-controls-{year}-{mode}.svg" alt="Original grid, bounded losses, profit lock, SPY and gold from {year}">
        <p><a href="loss-controls-{year}-{mode}.png" download>Download chart</a> · <a href="{c}_daily.csv">Loss-limit account history</a> · <a href="{p}_daily.csv">Profit-lock account history</a></p>
        <details><summary>All nine loss-control rules, both minute paths</summary>{table(all_controls)}</details>
        <details><summary>All nine profit-lock settings, both minute paths</summary>{table(all_locks)}</details>
        </section>''')

beats=[]
for source in [R['main'],P['main']]:
    grouped={}
    for s in source.values():
        setting=s['variant'] if 'variant' in s else (s['settings']['drawdown_activation_multiple'],s['settings']['account_drawdown_fraction'])
        grouped.setdefault((s['mode'],str(setting)),[]).append(s)
    for key,values in grouped.items():
        if len(values)==4 and all(s['ending_equity']>R['benchmarks'][f'{s["year"]}_SPY']['ending_equity'] for s in values):
            beats.append(key)
fills=sum(x['ledger_entries'] for source in [R,P] for x in source['verification'].values())
maxerror=max(x['maximum_cash_error'] for source in [R,P] for x in source['verification'].values())
headline='The loss controls did not produce a convincing SPY replacement.' if not beats else 'Some historical comparisons improved; independent validation remains.'
primary=R['main'][control_name(2019,'fixed','low_first')]
profit=P['main'][lock_name(2019,'fixed','low_first')]
profit2022=P['main'][lock_name(2022,'fixed','low_first')]
css=re.search(r'<style>(.*?)</style>',(ROOT/'index.html').read_text(),re.S).group(1)
sensitivity=''.join(f'<tr><td>{"Fixed" if s["settings"]["multiplier"]==1 else "Doubling"}</td><td>{s["settings"]["max_entries"]}</td><td>{PCT(s["settings"]["batch_loss_fraction"])}</td><td>{s["settings"]["cooldown_hours"]:g}h</td><td>{USD(s["ending_equity"])}</td><td>{PCT(s["max_drawdown"])}</td></tr>' for s in R['sensitivity'])
stress=''.join(row(s['mode']+' · '+str(s['year'])+' · '+LABELS[s['variant']]+' · '+s['path'].replace('_',' '),s) for s in R['cost_stress'])
html=f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Gold grid · loss-control experiments</title><style>{css}</style>
<header><b>AUREL / RESEARCH</b><span class="pill">Exploratory · previously inspected history</span></header>
<div class="layout"><aside><h2>Loss-control experiments</h2><div class="stat"><b>{len(R['main'])}</b><span>loss-control comparisons</span></div><div class="stat"><b>{len(P['main'])}</b><span>profit-lock comparisons</span></div><div class="stat"><b>{len(beats)}</b><span>rules beating SPY in both periods and paths</span></div><p class="small">Verified: all eight original baselines reproduced.<br>Assumed: the same costs, quotes and execution model.<br>Out of scope: AI filters and live trading.</p><p><a href="index.html">Original baseline report</a></p></aside>
<main><h1>{headline}</h1><p>We tested limits on repeated purchases, exposure, losses per batch and total account drawdown, plus pauses after losses. A second round activated trailing exits only after fixed profit milestones, prompted by the large peak in the original chart.</p>
<div class="callout"><p><strong>Protecting against a single disaster did not preserve the original profit curve.</strong> The 2% loss limit with caps and a one-day pause ended at {USD(primary['ending_equity'])} from $10,000 in the fixed-size 2019 run. The displayed profit lock ended at {USD(profit['ending_equity'])}; SPY ended at {USD(R['benchmarks']['2019_SPY']['ending_equity'])}.</p></div>
<div class="switch" aria-label="Start year"><button data-year="2019" aria-pressed="true">From 2019</button><button data-year="2022" aria-pressed="false">From 2022</button></div>
<div class="switch" aria-label="Purchase sizing"><button data-sizing="fixed" aria-pressed="true">Fixed-size purchases</button><button data-sizing="doubling" aria-pressed="false">Doubling purchases</button></div>
{''.join(panels)}
<h2>What the controls actually do</h2><p>The combined rule allows at most four purchases and approves a new purchase only if total exposure stays within twice the cash available at the start of the batch. It exits at a 2% loss after costs and waits 24 calendar hours before buying again. Repeated stops use the remaining money; there are no deposits or resets.</p>
<p>The profit lock starts with the original grid. Once the account reaches $20,000, it exits permanently after a 20% fall from its running peak. It can sell before a later recovery and never see the original $33,664 peak. Cash then earns zero. All activation levels of 1.25×, 1.5× and 2×, with trailing limits of 10%, 20% and 30%, are reported.</p>
<p><strong>A delayed 20% trail is not a 20% maximum drawdown.</strong> Before this protection activated, the displayed fixed-size rule had already fallen {PCT(profit['max_drawdown'])} from a peak in the 2019 account and {PCT(profit2022['max_drawdown'])} in the fresh-2022 account. The latter finished at {USD(profit2022['ending_equity'])}, above SPY's {USD(R['benchmarks']['2022_SPY']['ending_equity'])}, after surviving that earlier loss.</p>
<p>An admission cap can eventually make the fixed one-ounce initial order unaffordable. Such an account stops instead of shrinking its initial order; the table identifies this separately from a margin exit. Gaps and accumulated financing can cause losses beyond the nominal stop limit.</p>
<details><summary>All 54 nearby loss-limit combinations</summary><p>Full 2019 period, low-first path: two sizing rules, maximum two/four/eight purchases, 1%/2%/5% loss limits and zero/24/72-hour pauses, all with the same 2× admission cap. No best row was selected as the recommended strategy.</p><div class="table-scroll"><table><thead><tr><th>Sizing</th><th>Max buys</th><th>Loss limit</th><th>Pause</th><th>Ending value</th><th>Worst fall</th></tr></thead><tbody>{sensitivity}</tbody></table></div></details>
<details><summary>Higher financing and slippage</summary><p>Financing raised from 5% to 10% annual notional; slippage tripled from $0.05 to $0.15 per ounce per side. This stress covers the two combined rules with 24-hour pauses.</p>{table(stress)}</details>
<h2>What is verified, and what is still assumed?</h2><p><strong>Verified:</strong> 22 targeted tests pass. All eight original baseline summaries reproduce with controls disabled. Independent accounting reconciles {fills:,} fills across the 144 main and profit-lock comparisons, with maximum cash error ${maxerror:.9f}. Open losses, financing, fees, pauses and idle cash are included.</p>
<p><strong>Assumed:</strong> original entry/spacing/target settings, fixed one-ounce initial purchases, synthetic minute paths, flat-minute filtering, financing and margin policy remain the baseline assumptions. The controls do not establish exact tick-level execution or historical broker costs.</p>
<p><strong>Previously inspected data:</strong> all baseline history had already been seen. The loss-control grid was fixed before its results; the profit-lock round was designed afterward and separately recorded. Neither is an untouched test set. No AI prediction filter or live account was used.</p>
<p><strong>Interpretation:</strong> the evidence does not justify replacing SPY with this grid. A small-loss exit also closes trades that would have recovered. Exposure caps can leave a losing basket open for months, while a trailing exit can stop the account before a later profitable period. These tests do not prove every possible grid fails.</p>
<p><a href="loss_controls.json">All loss-control results</a> · <a href="profit_locks.json">All profit-lock results</a> · <a href="loss_control_protocol.json">First-round rules</a> · <a href="profit_lock_protocol.json">Second-round rules</a> · <a href="risk-research-bundle.zip">Code and results bundle</a></p>
<footer>Local research only · <code>/Users/claudiu/Sites/aurel3-gold-grid/research/gold_grid</code></footer></main></div>
<script>let year='2019',sizing='fixed';function show(){{document.querySelectorAll('[data-year]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.year===year)));document.querySelectorAll('[data-sizing]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.sizing===sizing)));document.querySelectorAll('.result-panel').forEach(p=>p.hidden=p.dataset.period!==year||p.dataset.mode!==sizing)}}document.querySelectorAll('[data-year]').forEach(b=>b.addEventListener('click',()=>{{year=b.dataset.year;show()}}));document.querySelectorAll('[data-sizing]').forEach(b=>b.addEventListener('click',()=>{{sizing=b.dataset.sizing;show()}}));</script></html>'''
(ROOT/'loss-controls.html').write_text(html)
for name in ['loss_control_protocol.json','profit_lock_protocol.json']:
    shutil.copy(Path('research/gold_grid')/name,ROOT/name)
print(ROOT/'loss-controls.html')
