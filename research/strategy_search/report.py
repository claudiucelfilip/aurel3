"""Render the strategy-search register and results as a standalone page."""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE.parents[1] / 'data' / 'gold_grid' / 'results' / 'strategy_search'
REPO = 'https://github.com/claudiucelfilip/aurel3/blob/research/gold-grid-20261021/research/strategy_search'
NAMES = {
    'C1_industry_momentum': 'Industry momentum', 'C2_small_value': 'Small-cap value',
    'C3_big_profitable': 'Profitable large caps', 'C4_big_conservative_investment': 'Low-investment large caps',
    'C5_halloween': 'Halloween (sell in May)', 'C6_global_dual_momentum': 'Global dual momentum',
    'C7_value_momentum_blend': 'Value + momentum blend', 'C8_small_cap_momentum': 'Small-cap momentum',
    'C9_net_repurchasers': 'Share buyback firms', 'C10_market_trend_filter': '10-month trend filter',
    'C11_small_value_momentum_blend': 'Small value + momentum',
}


def pp(x):
    return f'{x:+.1f}'


def main():
    res = json.loads((OUT / 'results.json').read_text())
    prot = json.loads((HERE / 'protocol.json').read_text())
    src = {**prot['batch_1'], **{k: v for k, v in prot['batch_2'].items() if k.startswith('C')}}
    rows = []
    for k, r in res.items():
        o = r['oos']
        cell = lambda ok, txt: f'<td class="{"ok" if ok else "no"}">{txt}</td>'
        etf = r['etf']
        etf_txt = (f'{etf["label"]}: {100 * etf["cagr"]:.1f}% vs SPY {100 * etf["spy_cagr"]:.1f}%' if etf else 'No matching ETF')
        ins = r['in_sample']['excess_pp']
        rows.append(f'<tr><th scope="row">{NAMES[k]}<small>{src[k]["source"].split(",")[0].split(" (")[0]} · tested from {o["from"][:4]}</small></th>'
                    f'<td>{"—" if ins is None else pp(ins)}</td>'
                    + cell(r['P1'], pp(o['excess_pp'])) + cell(r['P2'], f'{o["t_nw12"]:.1f}')
                    + cell(r['P3'], pp(r['recent_2007_excess_pp']))
                    + cell(r['P4'], f'{100 * o["dd"]:.0f}% / {100 * o["market_dd"]:.0f}%')
                    + cell(r['P5'], etf_txt) + '</tr>')
    passed = sum(r['passed'] for r in res.values())
    page = f'''<title>Aurel Strategy Search</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&family=Fraunces:opsz,wght@9..144,600&display=swap">
<style>
/* Layout: masthead, narrow rule rail, wide results column. */
:root {{ --bg:#f6f7f8; --panel:#fff; --ink:#14181d; --ink-2:#4b5560; --line:#dde2e7; --accent:#1c5cab; --accent-soft:#e4edf8;
  --good:#1d7a4a; --good-bg:#e3f3ea; --bad:#b4322f; --bad-bg:#fbe6e5;
  --display:"Fraunces",Georgia,serif; --body:"IBM Plex Sans",system-ui,sans-serif; --mono:"IBM Plex Mono",ui-monospace,monospace; }}
@media (prefers-color-scheme: dark) {{ :root:not([data-theme="light"]) {{ --bg:#111417; --panel:#181c20; --ink:#eef1f4; --ink-2:#a9b3bd; --line:#2b3238;
  --accent:#79a9e6; --accent-soft:#1d2a3a; --good:#6fcf97; --good-bg:#16291f; --bad:#f08a87; --bad-bg:#351a1a; color-scheme:dark }} }}
:root[data-theme="dark"] {{ --bg:#111417; --panel:#181c20; --ink:#eef1f4; --ink-2:#a9b3bd; --line:#2b3238;
  --accent:#79a9e6; --accent-soft:#1d2a3a; --good:#6fcf97; --good-bg:#16291f; --bad:#f08a87; --bad-bg:#351a1a; color-scheme:dark }}
body {{ background:var(--bg); color:var(--ink); font:15px/1.55 var(--body); }}
.wrap {{ max-width:1200px; margin:0 auto; padding-block:28px 64px; padding-left:max(16px, env(safe-area-inset-left, 0px)); padding-right:max(16px, env(safe-area-inset-right, 0px)); }}
header {{ display:flex; flex-wrap:wrap; gap:12px 20px; align-items:baseline; border-bottom:1px solid var(--line); padding-bottom:16px; }}
h1 {{ font:600 30px/1.15 var(--display); margin:0; }}
.meta {{ color:var(--ink-2); font-size:13px; }}
.pill {{ font:600 12px/1 var(--body); letter-spacing:.06em; text-transform:uppercase; padding:7px 10px; border-radius:999px; background:var(--bad-bg); color:var(--bad); }}
.grid {{ display:grid; grid-template-columns:260px minmax(0,1fr); gap:32px; margin-top:24px; }}
@media (max-width:860px) {{ .grid {{ grid-template-columns:minmax(0,1fr); }} }}
aside {{ display:flex; flex-direction:column; gap:18px; font-size:13.5px; }}
h2 {{ font:600 12px/1 var(--body); letter-spacing:.08em; text-transform:uppercase; color:var(--ink-2); margin:0 0 10px; }}
aside ol {{ margin:0; padding-left:18px; display:grid; gap:6px; }}
aside .note {{ color:var(--ink-2); }}
main {{ display:flex; flex-direction:column; gap:28px; min-width:0; }}
h3 {{ font:600 21px/1.25 var(--display); margin:0 0 8px; text-wrap:balance; }}
p {{ max-width:70ch; margin:0 0 10px; }}
.lead {{ font-size:17px; }}
.tbl {{ overflow-x:auto; background:var(--panel); border:1px solid var(--line); border-radius:8px; }}
table {{ border-collapse:collapse; font-size:13px; font-variant-numeric:tabular-nums; width:100%; }}
th, td {{ padding:8px 10px; border-bottom:1px solid var(--line); text-align:right; white-space:nowrap; }}
thead th {{ color:var(--ink-2); font-size:11.5px; font-weight:600; vertical-align:bottom; white-space:normal; }}
tbody th {{ text-align:left; font-weight:600; white-space:normal; min-width:170px; }}
tbody th small {{ display:block; font-weight:400; color:var(--ink-2); font-size:11.5px; }}
td.ok {{ color:var(--good); background:var(--good-bg); }} td.no {{ color:var(--bad); }}
td:last-child {{ text-align:left; font-size:12px; }}
.box {{ background:var(--accent-soft); border-radius:8px; padding:14px 16px; }}
ul {{ margin:0; padding-left:18px; max-width:72ch; }} li {{ margin-bottom:6px; }}
a {{ color:var(--accent); }}
</style>
<div class="wrap">
<header><span class="pill">{passed} of {len(res)} passed</span><h1>Aurel strategy search</h1>
<span class="meta">Rules registered before testing · US data 1926 to Aug 2026 · ETFs to Oct 16 2026 · no live system touched</span></header>
<div class="grid">
<aside>
  <div><h2>Pass bar, all required</h2><ol>
    <li>Beats the US market by 3+ points a year after costs, after the idea was published.</li>
    <li>Strong enough not to be luck after 12 tries (t ≥ 2.64).</li>
    <li>Not behind the market since 2007.</li>
    <li>Worst fall no more than 10 points deeper than the market's.</li>
    <li>A real ETF version beat SPY over its own history.</li></ol></div>
  <p class="note">Each candidate uses the original paper's rules and headline settings, recorded and pushed before testing. One of 12 slots is unused.</p>
</aside>
<main>
<section><h3>No strategy cleared the bar</h3>
<p class="lead">Eleven well-known, cash-only ideas were tested on decades of US data. Inside the data the original authors used, most beat the market by 2–5 points a year. After publication that shrank to between −3 and +1.5 points, and none came close to statistical confidence.</p>
<p>This matches published research on how documented market edges fade once known and traded. Nothing here was tuned, so the shrinkage is not caused by our testing.</p></section>
<section><h2>Results after publication (yearly points vs US market, after costs)</h2>
<div class="tbl"><table><thead><tr><th>Strategy</th><th>Before publication</th><th>After publication</th><th>Confidence (t)</th><th>Since 2007</th><th>Worst fall / market</th><th>Real ETF since launch</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table></div>
<p style="margin-top:10px;font-size:13.5px">Green cells meet that rule. Academic portfolios are rebuilt monthly from all US stocks (Kenneth French data); costs are flat yearly drags or turnover at 0.10% a side, as recorded per candidate.</p></section>
<section class="box"><h2>What this means</h2>
<p><b>Beating an index fund by 3+ points a year without leverage is not something any published, simple rule has done reliably since its publication.</b> Continuing to loop would eventually produce a winner by chance, and it would not be real.</p>
<p>Three of the results are useful even though they failed. The trend filter gave up about 2 points a year but cut the worst fall from 50% to 19%. Profitable large caps and buyback firms roughly matched the market. The SPY + gold mix matched or beat every ETF version tested since 2005.</p></section>
<section><h2>Options from here</h2><ul>
<li><b>Change the goal to the same return with smaller falls.</b> A trend filter or the SPY + gold mix both have real out-of-sample support for that.</li>
<li><b>Accept the index + gold mix as the core</b> and let Aurel3 track it and suggest rebalancing.</li>
<li><b>Test the running Aurel2 strategy</b> on matched dates, which has still not been done.</li></ul></section>
<section><h2>Sources</h2><ul>
<li><a href="{REPO}/protocol.json">Registered rules and pass bar</a> and <a href="{REPO}/engine.py">test code</a>.</li>
<li><a href="https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/12_Industry_Portfolios_CSV.zip">Kenneth French data library files</a> (industry, size, value, profitability, investment, momentum, issuance portfolios).</li></ul></section>
</main></div></div>
'''
    (OUT / 'index.html').write_text(page)
    print('wrote', OUT / 'index.html')


if __name__ == '__main__':
    main()
