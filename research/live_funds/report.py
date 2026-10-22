"""Render the live evidence and the reasons not to overstate it."""
import json
import shutil
import zipfile
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter
import pandas as pd
from analyze import DATA, HERE, OUT, digest

LINKS = {
    'SPMO': 'https://www.invesco.com/us/en/financial-products/etfs/invesco-sp-500-momentum-etf.html',
    'AMOM': 'https://www.defianceetfs.com/aied/',
    'AIEQ': 'https://amplifyetfs.com/aieq/',
    'MTUM': 'https://www.ishares.com/us/products/251614/MTUM',
    'QMOM': 'https://funds.alphaarchitect.com/qmom/',
    'QRFT': 'https://www.sec.gov/Archives/edgar/data/1547950/000121390026071873/ea0295872-01_497.htm',
    'SPY': 'https://www.ssga.com/us/en/individual/etfs/state-street-spdr-sp-500-etf-trust-spy',
    'GLD': 'https://www.spdrgoldshares.com/usa/gld/',
}
LABELS = {'SPMO': 'SPMO · stock momentum', 'AMOM': 'AMOM · earlier AI strategy',
          'AIEQ': 'AIEQ · AI stock selection', 'MTUM': 'MTUM · stock momentum',
          'QMOM': 'QMOM · stock momentum', 'SPY': 'SPY · S&P 500', 'GLD': 'GLD · gold',
          'QRFT': 'QRFT · unavailable history'}
MONEY = lambda x: f'${x:,.0f}'
PCT = lambda x: f'{100*x:.1f}%'
PAPER = 'https://arxiv.org/html/2510.26228v1'
METHODOLOGY = 'https://www.spglobal.com/spdji/en/documents/methodologies/methodology-sp-momentum-indices.pdf'
FACTSHEET = 'https://www.invesco.com/us-rest/contentdetail?contentId=35933e4f47062510VgnVCM100000c2f1bf0aRCRD'


def entity(ticker):
    return f'<a href="{LINKS[ticker]}">{LABELS[ticker]}</a>'


def charts(label):
    fig, axes = plt.subplots(2, 1, figsize=(12, 7), sharex=True,
                             gridspec_kw={'height_ratios': [3, 1]}, layout='constrained')
    for ticker, color in [('SPMO', '#176b68'), ('SPY', '#665d9c'), ('GLD', '#9b7424'),
                          ('AMOM', '#b55d49')]:
        s = pd.read_csv(OUT / f'{label}_{ticker}.csv', index_col=0, parse_dates=True).equity
        axes[0].plot(s.index, s, color=color, lw=2, label=LABELS[ticker])
        axes[1].plot(s.index, 100 * (s / s.cummax().clip(lower=10000) - 1), color=color, lw=1)
    axes[0].set_ylabel('Value of $10,000')
    axes[0].yaxis.set_major_formatter(FuncFormatter(lambda x, _: f'${x/1000:,.0f}k'))
    axes[0].legend(frameon=False, ncol=2, fontsize=9, loc='upper left')
    axes[1].set_ylabel('Fall from peak (%)')
    for ax in axes:
        ax.spines[['top', 'right']].set_visible(False)
        ax.grid(axis='y', alpha=.16)
    fig.savefig(OUT / f'{label}.svg')
    fig.savefig(OUT / f'{label}.png', dpi=150)
    plt.close(fig)


def main():
    d = json.loads((OUT / 'results.json').read_text())
    protocol = json.loads((HERE / 'protocol.json').read_text())
    if d['protocol_sha256'] != digest(HERE / 'protocol.json'):
        raise ValueError('Analysis and report protocols differ')
    titles = {'common_live': '22 May 2019 – 16 October 2026',
              'since_2022': '2022 – 16 October 2026',
              'before_2024': '22 May 2019 – 29 December 2023',
              'since_2024': '2024 – 16 October 2026',
              'paper_window': 'AI paper comparison · January 2024 – March 2025'}
    buttons = {'common_live': 'Full comparison', 'since_2022': 'Since 2022',
               'before_2024': 'Before 2024', 'since_2024': 'Since 2024',
               'paper_window': 'Paper dates'}
    panels = []
    order = ['SPMO', 'SPY', 'GLD', 'AMOM', 'AIEQ', 'MTUM', 'QMOM', 'QRFT']
    for label, rows in d['windows'].items():
        charts(label)
        table = []
        best = max(rows[t]['ending_equity'] for t in ['SPY', 'GLD'])
        for ticker in order:
            if ticker not in rows or 'error' in rows[ticker]:
                table.append(f'<tr><th>{entity(ticker)}</th><td colspan="4">Not calculated · data failure retained</td></tr>')
                continue
            s = rows[ticker]
            beat = 'Benchmark' if ticker in ['SPY', 'GLD'] else ('Yes' if s['ending_equity'] > best else 'No')
            table.append(f'<tr><th>{entity(ticker)}</th><td><a href="{label}_{ticker}.csv">{MONEY(s["ending_equity"])}</a></td><td>{PCT(s["cagr_net"])}</td><td>{PCT(s["drawdown_net"])}</td><td>{beat}</td></tr>')
        panels.append(f'<section data-panel="{label}" {"" if label == "common_live" else "hidden"}><h2>{titles[label]}</h2><div class="scroll"><table><thead><tr><th>Fund / strategy</th><th>Ending $10,000</th><th>Per year</th><th>Worst fall</th><th>Beat both?</th></tr></thead><tbody>{"".join(table)}</tbody></table></div><img class="chart" src="{label}.svg" alt="SPMO, SPY, gold and the earlier AMOM strategy, with portfolio values and drawdowns"><p class="small">Cash-funded buy and hold; USD; dividends reinvested; fund expenses embedded; 0.10% entry and exit cost. No tax or FX. Year-start comparisons use the previous year-end close. Drawdowns use daily closes. Click ending values for every observation.</p></section>')
    roll = ''.join(f'<tr><th>{entity(t)}</th><td>{x["beat_both"]} / {x["windows"]}</td><td>{PCT(x["worst_total_return"])}</td></tr>'
                   for t, x in d['rolling_36_months'].items())
    paper_rows = ''.join(f'<tr><th>{entity(t)}</th><td>{PCT(d["windows"]["paper_window"][t]["total_before_entry_exit"])}</td><td>{PCT(d["windows"]["paper_window"][t]["cagr_before_entry_exit"])}</td><td>{PCT(d["windows"]["paper_window"][t]["annual_arithmetic_before_entry_exit"])}</td></tr>' for t in ['SPMO', 'SPY', 'GLD'])
    checks = ''.join(f'<tr><th><a href="{FACTSHEET}">{year}</a></th><td>{PCT(x["issuer_nav"])}</td><td>{PCT(x["vendor_market"])}</td><td>{x["difference_pp"]:+.2f} pp</td></tr>' for year, x in d['spmo_issuer_nav_crosscheck'].items())
    css = (HERE / 'style.css').read_text()
    css += 'td{white-space:normal}th,td{vertical-align:top}.layout{grid-template-columns:250px minmax(0,1fr)}.note{border-left:4px solid #b26936;padding:12px 18px;background:#fff5e9}.switch{flex-wrap:wrap}.pill{font-size:12px}@media(max-width:850px){.layout{grid-template-columns:1fr}}'
    html = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Aurel research · Live stock-selection evidence</title><style>{css}</style></head><body>
<header><b>AUREL / RESEARCH</b><span class="pill">22 October 2026 · exploratory evidence</span></header>
<div class="layout"><aside><h2>Research decision</h2><div class="stat"><b>1</b><span>stronger candidate for further work</span></div><div class="stat"><b>0</b><span>validated Aurel replacements</span></div><p>Cash-funded portfolios.<br>Published rules.<br>No fitted timing overlay.</p><p><a href="protocol.json">Comparison plan</a><br><a href="results.json">All calculations</a><br><a href="annual_returns.csv">Calendar returns</a><br><a href="validation.json">Arithmetic checks</a><br><a href="evidence.zip">Download evidence</a><br><a href="../redesign.html">Earlier cash-only experiments</a></p></aside><main>
<h1>A stronger lead:<br>systematic stock selection.</h1>
<p><strong>My recommendation:</strong> use {entity('SPMO')} as the next research baseline and candidate. Its live history gives us a concrete standard any home-built or AI-enhanced system must beat. It is worth investigating; the evidence does not yet justify calling it a dependable winner over stocks and gold.</p>
<div class="callout"><p>Over the common live period, $10,000 became <strong>$38,521</strong> in the stock-momentum fund, versus $29,754 in the broad stock fund and $31,707 in gold. Its largest fall was <strong>30.9%</strong>. That is better than the broad stock fund's 33.7%, but remains a substantial loss.</p></div>
<h2>How the algorithm works</h2>
<p>The <a href="{METHODOLOGY}">published index rules</a> rank large U.S. stocks by the strength of their previous year's price gains, adjusted for how erratic those gains were. The most recent month is skipped. Roughly the strongest fifth is held, with weights based on company size and momentum score. <a href="{LINKS['SPMO']}">The fund</a> refreshes the portfolio in March and September.</p>
<p>For an Aurel implementation, that means a scheduled stock-ranking and portfolio-review job. Buying the fund would delegate its internal trades to the fund; reproducing the individual holdings ourselves would require historical constituents, corporate actions, weights and execution validation. These fund returns do not prove a home-built copy will match them.</p>
<div class="switch" aria-label="Comparison period">{''.join(f'<button data-view="{key}" aria-pressed="{str(key == "common_live").lower()}">{value}</button>' for key, value in buttons.items())}</div>
{''.join(panels)}
<h2>The overfitting challenge</h2>
<p>From May 2019 through 2023, the candidate returned <strong>13.0% per year</strong>, versus <strong>13.5%</strong> for the broad stock fund. The strong endpoint depends on its subsequent run. Since 2022 it leads gold by only <strong>0.8 percentage points per year</strong>—too little to ignore implementation differences. Since 2024 its drawdown was also slightly worse than the broad stock fund's.</p>
<p>It beat both benchmarks in <strong>30 of 53</strong> overlapping three-year windows. Those windows share most of their data; 30/53 is not a future success probability. The table preserves the weaker funds, and the failed retrieval, instead of presenting only the winner.</p>
<div class="scroll"><table><thead><tr><th>Candidate</th><th>Three-year wins over both</th><th>Worst three-year total return</th></tr></thead><tbody>{roll}</tbody></table></div>
<p class="small">Month-end windows ending May 2022–September 2026. Identical entry and exit costs would not change these rankings. Figures are descriptive. Public performance headlines informed the candidate list; this is a selected sample, not an unbiased survey of every fund. No parameter search was run.</p>
<h2>What the AI research actually adds</h2>
<p>The <a href="{PAPER}">Anic–Barbon–Seiz–Zarattini paper</a> combines monthly momentum with news scoring. It reports a 30% annualized return and 17% drawdown in January 2024–March 2025, after selecting among 512 configurations; the test spans only 15 months and assumes 2-basis-point costs. It compares against plain momentum. Private inputs prevent an exact replication here.</p>
<p>Our independent benchmark calculation for those dates:</p>
<div class="scroll"><table><thead><tr><th>Live fund</th><th>Total return</th><th>Compound annual return</th><th>Mean daily return × 252</th></tr></thead><tbody>{paper_rows}</tbody></table></div>
<p class="small">Benchmark figures above exclude our added entry/exit costs, retain embedded fund expenses, and include 312 sessions from the 29 December 2023 close to 31 March 2025. The paper's table says annualized while its prose says total return. Without its daily series, we cannot reconcile the metric exactly. Neither ordinary interpretation establishes an advantage over gold here.</p>
<details><summary>Reproduction issues in the paper</summary><p>The listed grid implies 1,024 combinations, versus the reported 512. Timing differs between the method and example prompt; the exact model snapshot is not specified. News revisions and model training history need separate leakage checks. These are unresolved details, not proof of wrongdoing.</p></details>
<div class="note"><p><strong>A fund now uses a similar idea, with almost no history for the new feature.</strong> <a href="{LINKS['AMOM']}">AMOM changed to AIED on 19 October 2026</a>, adding an LLM news signal. Our AMOM results end before that change. The old track record cannot validate the new language-model component.</p></div>
<h2>Other leads checked</h2>
<div class="scroll"><table><thead><tr><th>Lead</th><th>Finding</th><th>Decision</th></tr></thead><tbody>
<tr><th><a href="https://arxiv.org/html/2606.29734v1">Fast Numbers, Slow Language</a></th><td>Earnings-call trading; reported portfolio includes shorts and a gross-exposure target of two. The <a href="https://github.com/piqueyd/Fast-Numbers-Slow-Language">repository</a> still advertises forthcoming code/data.</td><td>Does not validate a cash-only version.</td></tr>
<tr><th><a href="https://aclanthology.org/2025.finnlp-2.13/">LLM post-earnings drift study</a></th><td>Studies filing text and early price response; reported long/short event returns do not establish an executable cash-funded portfolio.</td><td>Missing portfolio-level validation.</td></tr>
<tr><th><a href="https://github.com/Fin5998104/systematic-equity-optimiser">Systematic Equity Optimiser</a></th><td>Claims strong long-only results, but its backtesting engine is private.</td><td>Not independently reproduced.</td></tr>
<tr><th>{entity('AIEQ')}</th><td>Available live history trails both main benchmarks in our full comparison.</td><td>No evidence here that the AI label delivers the required edge.</td></tr>
<tr><th>{entity('QRFT')}</th><td>Liquidation was scheduled for July 2026; the price provider returned no history.</td><td>Retained as unavailable, not silently omitted or scored as zero.</td></tr>
</tbody></table></div>
<h2>What is verified, assumed and outside this result</h2>
<div class="scroll"><table><thead><tr><th>Verified</th><th>Assumed</th><th>Out of scope / unresolved</th></tr></thead><tbody>
<tr><td><a href="results.json">35 fund-window calculations</a>; seven usable histories with no missing sessions, nulls or nonpositive adjusted prices in the common window.</td><td>Adjusted closes represent reinvested distributions adequately for screening.</td><td>No independent daily NAV reconciliation; actual reinvestment timing, Romanian tax, FX and broker charges.</td></tr>
<tr><td><a href="identity_notes.json">Ticker and strategy changes</a> checked against issuer / SEC records; original failed queries retained.</td><td>Cash-funded fund purchases with 0.10% per side. No borrowing, shorts or leverage multiplier in this calculation.</td><td>No audit of every internal historical fund holding; no live orders or Aurel runtime changes.</td></tr>
<tr><td><a href="protocol.json">Declared comparison dates and candidate list</a>, with source hashes in the <a href="manifest.json">manifest</a>.</td><td>Live fund history is useful evidence about implementation.</td><td>Choosing a past winner remains selection. No untouched holdout, confidence percentage, or validated AI contribution.</td></tr>
</tbody></table></div>
<details><summary>Cross-check against the issuer</summary><p>The <a href="{FACTSHEET}">indexed issuer factsheet for 2025</a> reports 17.87% annualized at NAV over ten years, versus 14.82% for the broad index. That document URL currently redirects when opened directly; the <a href="https://www.sec.gov/Archives/edgar/data/1378872/000119312525325661/d54028d497k.htm">SEC-filed prospectus</a> independently confirms the 2024 return. Our daily source is market-price based. Annual deviations below reach 0.37 percentage points; this is corroboration, not an exact reconciliation. Earlier 2016 and 2018 discrepancies were larger; those years are not used to extend the local result.</p><div class="scroll"><table><thead><tr><th>Year</th><th>Issuer NAV</th><th>Vendor market total return</th><th>Difference</th></tr></thead><tbody>{checks}</tbody></table></div><p>The start was declared for a common live history before these discrepancies were inspected. The <a href="{METHODOLOGY}">index methodology</a> also records a September 2026 weight-cap change, so the history does not represent one immutable algorithm.</p></details>
<h2>What is worth doing next</h2>
<p>Investigate the published stock-ranking approach as a candidate for Aurel3, keeping the actual fund as the comparison. Require an exact holdings-and-cost reconciliation before trusting a clone. The older cash-only grid experiments remain rejected.</p>
<p>For AI, the useful experiment is narrower: does a frozen news filter improve the same stock portfolio after costs? Use historical text versions, a model available before the test period, one fixed prompt, next-session execution, and identical cash limits. <a href="https://docs.alpaca.markets/us/docs/historical-news-data">Alpaca documents news history from 2015</a>, but access alone does not prove the archive preserves the text known on each trading date. No paid data or model calls were made.</p>
<p>Neither the fund screen nor the paper clears the full promotion gate. The concrete improvement is a stronger, transparent baseline and evidence against paying for an unproven AI overlay.</p>
<footer><a href="https://github.com/claudiucelfilip/aurel3">Aurel3 research</a> · branch <code>research/gold-grid-20261021</code><br>Code: <code>research/live_funds/</code> · data: <code>data/live_funds/</code><br><a href="evidence.zip">Code, inputs, results and charts</a></footer></main></div>
<script>document.querySelectorAll('[data-view]').forEach(b=>b.addEventListener('click',()=>{{document.querySelectorAll('[data-view]').forEach(x=>x.setAttribute('aria-pressed',String(x===b)));document.querySelectorAll('[data-panel]').forEach(p=>p.hidden=p.dataset.panel!==b.dataset.view)}}));</script></body></html>'''
    (OUT / 'index.html').write_text(html)
    for path in [HERE / 'protocol.json', HERE / 'identity_notes.json', DATA / 'manifest.json']:
        shutil.copy(path, OUT / path.name)
    with zipfile.ZipFile(OUT / 'evidence.zip', 'w', zipfile.ZIP_DEFLATED) as z:
        for directory, prefix in [(HERE, 'code'), (DATA, 'inputs'), (OUT, 'results')]:
            for path in sorted(directory.iterdir()):
                if path.is_file() and path.suffix != '.zip':
                    z.write(path, f'{prefix}/{path.name}')
    print(OUT / 'index.html')


if __name__ == '__main__':
    main()
