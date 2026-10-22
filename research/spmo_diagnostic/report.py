"""Render the SPMO concentration diagnostic as a standalone HTML page from results.json."""
import html
import json
from pathlib import Path
import numpy as np
import pandas as pd
import analyze as A

OUT = A.OUT
REPO = 'https://github.com/claudiucelfilip/aurel3/blob/research/gold-grid-20261021/research/spmo_diagnostic'
SPMO_URL = 'https://www.invesco.com/us/en/financial-products/etfs/invesco-sp-500-momentum-etf.html'
METHOD_URL = 'https://www.spglobal.com/spdji/en/documents/methodologies/methodology-sp-momentum-indices.pdf'
FRENCH_URL = 'https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/6_Portfolios_ME_Prior_12_2_CSV.zip'
NPORT_URL = ('https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=S000050154'
             '&type=NPORT-P&dateb=&owner=include&count=100')


def pp(x, d=1):
    return f'{x:+.{d}f} pts'


def pct(x, d=1):
    return f'{100 * x:.{d}f}%'


def esc(s):
    return html.escape(str(s))


def series_json(s):
    return json.dumps([[d.strftime('%Y-%m-%d'), round(float(v), 4)] for d, v in s.items()])


def main():
    r = json.loads((OUT / 'results.json').read_text())
    f = A.load_funds()
    q1, q2, q3, q4 = r['Q1'], r['Q2'], r['Q3'], r['Q4']
    liq, stale, com = q1['liquid_start']['SPY'], q1['protocol_start_stale_prices']['SPY'], q1['common_live_start']['SPY']
    s24 = q3['since_2023_11_30']
    bh = q2['buy_and_hold']['liquid_start']
    d1 = q4['drag_1pct']
    r1 = all(x['share_from_2024'] >= .75 and x['annualized_excess_before_2024_pp'] < 1 for x in (liq, stale))
    r2 = s24['active']['excess_without_top5_pp'] < 3
    r3 = any(bh[c]['cagr'] >= bh['SPMO']['cagr'] - .01 and bh[c]['drawdown'] <= bh['SPMO']['drawdown'] for c in ['SPYG', 'QQQ'])
    cont = d1['decades_at_least_1pp'] > len(d1['decades_excess_pp']) / 2
    verdict = 'Rejected' if (r1 or r2 or r3) else ('Continue to a frozen spec' if cont else 'Rejected')

    # Chart data: relative wealth vs SPY (weekly) and the 1927+ long-only momentum ratio (monthly).
    rel = f[['SPMO', 'MTUM', 'SPY']].loc[A.START_LIQUID:].resample('W-FRI').last().dropna()
    spmo_rel = rel['SPMO'] / rel['SPMO'].iloc[0] / (rel['SPY'] / rel['SPY'].iloc[0])
    mtum_rel = rel['MTUM'] / rel['MTUM'].iloc[0] / (rel['SPY'] / rel['SPY'].iloc[0])
    _, fr = A.q4()
    long_rel = (1 + fr['big_high']).cumprod() / (1 + fr['market']).cumprod()

    years = [y for y in q1['annual_returns'] if 2016 <= int(y) <= 2026]
    annual_rows = ''.join(
        f'<tr><td>{y}{" (to Oct 16)" if y == "2026" else ""}</td>' + ''.join(
            f'<td>{pct(q1["annual_returns"][y][t])}</td>' for t in ['SPMO', 'SPY', 'GLD', 'MTUM']) +
        f'<td class="{"pos" if q1["annual_returns"][y]["SPMO"] > q1["annual_returns"][y]["SPY"] else "neg"}">'
        f'{pp(100 * (q1["annual_returns"][y]["SPMO"] - q1["annual_returns"][y]["SPY"]))}</td></tr>' for y in years)
    fc = q2['factor_contributions_2024_on']['SPMO_minus_SPY_pp']
    fc_old = q2['factor_contributions_2018_2023']['SPMO_minus_SPY_pp']
    labels = {'Mkt-RF': 'Extra stock-market exposure (beta above 1)', 'Mom': 'Momentum factor',
              'RMW': 'Tilt away from steady, profitable firms', 'SMB': 'Tilt to the very largest firms',
              'HML': 'Value tilt', 'CMA': 'Investment tilt', 'alpha_pp': 'Unexplained remainder'}
    factor_rows = ''.join(f'<tr><td>{labels[k]}</td><td>{pp(fc_old[k])}</td><td>{pp(fc[k])}</td></tr>'
                          for k in ['Mkt-RF', 'Mom', 'RMW', 'SMB', 'HML', 'CMA', 'alpha_pp'])
    top_rows = ''.join(f'<tr><td>{esc(t["ticker"])}</td><td>{esc(t["name"]).title()[:34]}</td><td>{pp(t["sum_pp"], 2)}</td></tr>'
                       for t in s24['active']['top'][:8])
    k_rows = ''.join(f'<tr><td>{k}</td><td>{pp(s24["active"][f"excess_without_top{k}_pp"])}</td>'
                     f'<td>{pp(q3["before_2023_11_30"]["active"][f"excess_without_top{k}_pp"])}</td></tr>' for k in [1, 3, 5, 10])
    sec = q3['sectors_since_2023_11_30']
    sec_rows = ''.join(f'<tr><td>{esc(k)}</td><td>{pct(v["avg_spmo_weight"], 0)}</td><td>{pct(v["avg_ivv_weight"], 0)}</td><td>{pp(v["active_sum_pp"])}</td></tr>'
                       for k, v in list(sec.items())[:4])
    dec_rows = ''.join(f'<tr><td>{k}</td><td>{pp(q4["drag_0pct"]["decades_excess_pp"][k])}</td><td>{pp(v)}</td></tr>'
                       for k, v in d1['decades_excess_pp'].items())
    ctrl_rows = ''.join(f'<tr><td>{t}</td><td>{pct(bh[t]["cagr"], 2)}</td><td>{pct(q2["buy_and_hold"]["before_2024_liquid"][t]["cagr"], 2)}</td>'
                        f'<td>{pct(q2["buy_and_hold"]["since_2024"][t]["cagr"], 2)}</td><td>{pct(bh[t]["drawdown"])}</td></tr>'
                        for t in ['SPMO', 'SPY', 'GLD', 'MTUM', 'SPYG', 'QQQ', 'RSP'])
    fid = q3['fidelity']

    def gate(ok, name, text):
        cls, word = ('fail', 'Triggered') if not ok else ('pass', 'Clear')
        return f'<li class="{cls}"><span class="chip">{word}</span><b>{name}</b><span>{text}</span></li>'
    gates = ''.join([
        gate(not r1, 'R1 · time concentration', f'{pct(liq["share_from_2024"], 0)} of the lead came from 2024 on; before 2024 it was {pp(liq["annualized_excess_before_2024_pp"])} a year (limit: 75% and +1 pt).'),
        gate(not r2, 'R2 · few stocks', f'Without the top 5 contributors, 2024-on lead is {pp(s24["active"]["excess_without_top5_pp"])} a year (limit: 3 pts). Narrow pass.'),
        gate(not r3, 'R3 · simple control', f'QQQ returned more ({pct(bh["QQQ"]["cagr"], 2)} vs {pct(bh["SPMO"]["cagr"], 2)}) but with a deeper fall ({pct(bh["QQQ"]["drawdown"])}).'),
        f'<li class="{"pass" if cont else "fail"}"><span class="chip">{"Met" if cont else "Not met"}</span><b>Century base rate</b>'
        f'<span>{d1["decades_at_least_1pp"]} of {len(d1["decades_excess_pp"])} decades ahead by 1 pt after a 1% cost drag; both decades since 2007 were behind.</span></li>'])

    page = f'''<title>SPMO Concentration Check</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&family=Fraunces:opsz,wght@9..144,600&display=swap">
<style>
/* Layout: masthead, narrow evidence rail (gates + stats), wide narrative column. */
:root {{
  --bg: #f6f7f8; --panel: #ffffff; --ink: #14181d; --ink-2: #4b5560; --line: #dde2e7;
  --accent: #1c5cab; --accent-soft: #e4edf8; --good: #1d7a4a; --good-bg: #e3f3ea; --bad: #b4322f; --bad-bg: #fbe6e5;
  --series-1: #2a78d6; --series-2: #eb6834; --grid: #e7ebef;
  --display: "Fraunces", Georgia, serif; --body: "IBM Plex Sans", system-ui, sans-serif; --mono: "IBM Plex Mono", ui-monospace, monospace;
}}
@media (prefers-color-scheme: dark) {{ :root:not([data-theme="light"]) {{
  --bg: #111417; --panel: #181c20; --ink: #eef1f4; --ink-2: #a9b3bd; --line: #2b3238;
  --accent: #79a9e6; --accent-soft: #1d2a3a; --good: #6fcf97; --good-bg: #16291f; --bad: #f08a87; --bad-bg: #351a1a;
  --series-1: #3987e5; --series-2: #d95926; --grid: #252b31; color-scheme: dark }} }}
:root[data-theme="dark"] {{
  --bg: #111417; --panel: #181c20; --ink: #eef1f4; --ink-2: #a9b3bd; --line: #2b3238;
  --accent: #79a9e6; --accent-soft: #1d2a3a; --good: #6fcf97; --good-bg: #16291f; --bad: #f08a87; --bad-bg: #351a1a;
  --series-1: #3987e5; --series-2: #d95926; --grid: #252b31; color-scheme: dark }}
body {{ background: var(--bg); color: var(--ink); font: 15px/1.55 var(--body); }}
.wrap {{ max-width: 1180px; margin: 0 auto; padding-block: 28px 64px; padding-left: max(16px, env(safe-area-inset-left, 0px)); padding-right: max(16px, env(safe-area-inset-right, 0px)); }}
header.mast {{ display: flex; flex-wrap: wrap; gap: 12px 20px; align-items: baseline; border-bottom: 1px solid var(--line); padding-bottom: 16px; }}
.mast h1 {{ font: 600 30px/1.15 var(--display); margin: 0; text-wrap: balance; }}
.mast .meta {{ color: var(--ink-2); font-size: 13px; }}
.pill {{ font: 600 12px/1 var(--body); letter-spacing: .06em; text-transform: uppercase; padding: 7px 10px; border-radius: 999px; background: var(--bad-bg); color: var(--bad); }}
.grid {{ display: grid; grid-template-columns: 260px minmax(0, 1fr); gap: 32px; margin-top: 24px; }}
@media (max-width: 860px) {{ .grid {{ grid-template-columns: minmax(0, 1fr); }} }}
aside {{ display: flex; flex-direction: column; gap: 20px; font-size: 13.5px; }}
aside h2, main h2 {{ font: 600 12px/1 var(--body); letter-spacing: .08em; text-transform: uppercase; color: var(--ink-2); margin: 0 0 10px; }}
.gates {{ list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 10px; }}
.gates li {{ background: var(--panel); border: 1px solid var(--line); border-left: 3px solid var(--good); border-radius: 6px; padding: 10px 12px; display: grid; gap: 4px; }}
.gates li.fail {{ border-left-color: var(--bad); }}
.chip {{ justify-self: start; font: 600 11px/1 var(--body); text-transform: uppercase; letter-spacing: .05em; padding: 4px 6px; border-radius: 4px; background: var(--good-bg); color: var(--good); }}
.fail .chip {{ background: var(--bad-bg); color: var(--bad); }}
.gates span:last-child {{ color: var(--ink-2); }}
dl.stats {{ margin: 0; display: grid; gap: 8px; }}
dl.stats div {{ display: flex; justify-content: space-between; gap: 12px; border-bottom: 1px dashed var(--line); padding-bottom: 6px; }}
dl.stats dt {{ color: var(--ink-2); }} dl.stats dd {{ margin: 0; font: 500 13px var(--mono); font-variant-numeric: tabular-nums; }}
main {{ display: flex; flex-direction: column; gap: 32px; min-width: 0; }}
main section {{ min-width: 0; }}
main h3 {{ font: 600 21px/1.25 var(--display); margin: 0 0 8px; text-wrap: balance; }}
main p {{ max-width: 70ch; margin: 0 0 10px; }}
.lead {{ font-size: 17px; }}
.tbl {{ overflow-x: auto; }}
table {{ border-collapse: collapse; font-size: 13.5px; font-variant-numeric: tabular-nums; min-width: 100%; }}
th, td {{ text-align: right; padding: 6px 10px; border-bottom: 1px solid var(--line); white-space: nowrap; }}
th:first-child, td:first-child {{ text-align: left; }}
th {{ font-weight: 600; color: var(--ink-2); font-size: 12px; }}
td.pos {{ color: var(--good); }} td.neg {{ color: var(--bad); }}
.two {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 24px; }}
.chart {{ background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 12px; position: relative; }}
.chart svg {{ width: 100%; height: auto; display: block; }}
.chart .cap {{ font-size: 12.5px; color: var(--ink-2); margin-top: 6px; }}
.legend {{ display: flex; gap: 16px; font-size: 12.5px; color: var(--ink-2); margin-bottom: 6px; }}
.legend i {{ display: inline-block; width: 14px; height: 2px; vertical-align: middle; margin-right: 6px; }}
.tip {{ position: absolute; pointer-events: none; background: var(--panel); border: 1px solid var(--line); border-radius: 6px; padding: 6px 8px; font: 12px var(--mono); box-shadow: 0 2px 8px rgba(0,0,0,.12); }}
.box {{ background: var(--accent-soft); border-radius: 8px; padding: 14px 16px; }}
.box p:last-child {{ margin-bottom: 0; }}
ul.plain {{ margin: 0; padding-left: 18px; max-width: 72ch; }} ul.plain li {{ margin-bottom: 6px; }}
.vao {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 16px; }}
.vao div {{ background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 12px 14px; font-size: 13.5px; }}
.vao h4 {{ margin: 0 0 6px; font-size: 13px; }}
a {{ color: var(--accent); }}
code {{ font: 12.5px var(--mono); }}
</style>
<div class="wrap">
<header class="mast">
  <span class="pill">{verdict}</span>
  <h1>Why SPMO pulled ahead after 2023</h1>
  <span class="meta">Aurel research · diagnostic recorded before computing · data to 16 Oct 2026 · no live system touched</span>
</header>
<div class="grid">
<aside>
  <div><h2>Declared gates</h2><ul class="gates">{gates}</ul></div>
  <div><h2>Key numbers</h2><dl class="stats">
    <div><dt>SPMO yearly lead vs SPY, 2018–2023</dt><dd>{pp(liq["annualized_excess_before_2024_pp"])}</dd></div>
    <div><dt>SPMO yearly lead vs SPY, 2024 on</dt><dd>{pp(liq["annualized_excess_2024_on_pp"])}</dd></div>
    <div><dt>Share of lead from 2024 on</dt><dd>{pct(liq["share_from_2024"], 0)}</dd></div>
    <div><dt>Factor-adjusted extra, 2018–2023</dt><dd>{pp(q2["factor_regression"]["liquid_start:before_2024"]["alpha_annual_pp"])}</dd></div>
    <div><dt>MTUM time behind SPY high</dt><dd>{q1["MTUM_vs_SPY"]["relative_drawdown"]["longest_years"]} yrs</dd></div>
    <div><dt>Academic momentum below 2008 peak</dt><dd>{q4["drag_0pct"]["relative_drawdown"]["longest_years"]:.0f} yrs</dd></div>
    <div><dt>Holdings model error per period</dt><dd>{fid["spmo_mean_abs_gap_pp"]:.2f} pts</dd></div>
  </dl></div>
</aside>
<main>
<section>
  <h3>Answer: the lead is a recent run, not a steady edge</h3>
  <p class="lead">Your chart reading holds. From 2018 to the end of 2023, <a href="{SPMO_URL}">SPMO</a> beat SPY by under one point a year, which costs and mistakes would erase. Almost all of its advantage came from 2024 onward. The rule set before computing says to reject it as an Aurel candidate.</p>
  <p>The 2024–2026 lead is real in the fund's results, but it came from a strong period for momentum stocks in general, extra stock-market exposure, and a handful of chip and AI-linked stocks. A momentum strategy did not have to look like this: a second momentum fund (MTUM) spent {q1["MTUM_vs_SPY"]["relative_drawdown"]["longest_years"]} years behind SPY, and the academic long-only version has not gained on the market since 2008.</p>
</section>
<section>
  <h2>1 · When the lead was earned</h2>
  <div class="two">
    <div class="chart" id="c1"><div class="legend"><span><i style="background:var(--series-1)"></i>SPMO ÷ SPY</span><span><i style="background:var(--series-2)"></i>MTUM ÷ SPY</span></div>
      <svg viewBox="0 0 520 260" role="img" aria-label="SPMO and MTUM value relative to SPY since 2018"></svg>
      <div class="cap">Value of $1 in each fund divided by $1 in SPY, from Dec 29 2017, weekly. Above 1.0 means ahead of SPY.</div></div>
    <div class="tbl"><table><thead><tr><th>Year</th><th>SPMO</th><th>SPY</th><th>Gold</th><th>MTUM</th><th>SPMO − SPY</th></tr></thead><tbody>{annual_rows}</tbody></table></div>
  </div>
  <p style="margin-top:12px">SPMO traded rarely before late 2017, so its 2016–2017 prices are mostly stale and are shown for completeness only. The result does not depend on the start date: from Oct 2015, {pct(stale["share_from_2024"], 0)} of the lead came after 2023; from May 2019, all of it did. Monthly, SPMO was ahead of SPY in {pct(q1["monthly_excess_vs_SPY"]["liquid_start:before_2024"]["share_months_ahead"], 0)} of months before 2024, a coin flip.</p>
</section>
<section>
  <h2>2 · What explains 2024 onward</h2>
  <p>Standard academic return factors explain about 90% of SPMO's monthly moves. Before 2024 they account for all of its result. After 2023 the lead splits into the pieces below; the unexplained remainder is small for so short a period and could easily be chance (t ≈ {q2["factor_regression"]["liquid_start:2024_on"]["t_alpha"]:.1f}).</p>
  <div class="tbl"><table><thead><tr><th>Source of SPMO's lead over SPY, per year</th><th>2018–2023</th><th>2024–Aug 2026</th></tr></thead><tbody>{factor_rows}</tbody></table></div>
  <p style="margin-top:10px">The momentum factor itself returned {q2["factor_contributions_2024_on"]["mean_factor_annual_pp"]["Mom"]:.1f}% a year from 2024 versus {q2["factor_contributions_2018_2023"]["mean_factor_annual_pp"]["Mom"]:.1f}% in 2018–2023. SPMO's market sensitivity also rose from about 1.0 to 1.27, so part of the lead is extra risk taken in a rising market.</p>
</section>
<section>
  <h2>3 · Which stocks did it</h2>
  <p>Rebuilt from SPMO's quarterly SEC holdings reports, split at each March and September rebalance. The rebuild matches the fund's real return to within {fid["spmo_mean_abs_gap_pp"]:.2f} points per period on average (worst {fid["spmo_max_abs_gap_pp"]:.1f}). Lead is measured against S&amp;P 500 weights from IVV's reports.</p>
  <div class="two">
    <div class="tbl"><table><thead><tr><th>Top contributors</th><th>Company</th><th>Added, Dec 2023–Oct 2026</th></tr></thead><tbody>{top_rows}</tbody></table></div>
    <div class="tbl"><table><thead><tr><th>Remove top k</th><th>Yearly lead, 2024 on</th><th>Dec 2019–Nov 2023</th></tr></thead><tbody>{k_rows}</tbody></table>
    <p style="margin-top:10px;font-size:13.5px">Full 2024-on lead before removal: {pp(s24["implied_excess_vs_ivv_pp"])} a year. Any stock picker loses when its best picks are removed after the fact, so this shows how concentrated the result is, not that it is fake.</p></div>
  </div>
  <p style="margin-top:12px">Technology made up about the same share of SPMO as of the index ({pct(sec["Technology"]["avg_spmo_weight"], 0)} vs {pct(sec["Technology"]["avg_ivv_weight"], 0)}). The gain came from which tech stocks it held, mainly chipmakers, worth {pp(sec["Technology"]["active_sum_pp"])} in total over the period. Before 2024 its biggest sector gain came from energy stocks in 2022. The winning theme changes; nothing here shows it can be picked in advance.</p>
</section>
<section>
  <h2>4 · A century of the same idea</h2>
  <div class="two">
    <div class="chart" id="c2"><svg viewBox="0 0 520 260" role="img" aria-label="Large-company momentum stocks relative to the US market since 1927, log scale"></svg>
      <div class="cap">Large-company, high-momentum US stocks (Kenneth French data, before costs) divided by the whole US market, 1927–Aug 2026, log scale.</div></div>
    <div class="tbl"><table><thead><tr><th>Decade</th><th>Lead, before costs</th><th>After 1% a year</th></tr></thead><tbody>{dec_rows}</tbody></table></div>
  </div>
  <p style="margin-top:12px">Long-only momentum in large companies beat the market by {q4["drag_0pct"]["annualized_excess_pp"]:.1f} points a year over 99 years before costs, and still {d1["annualized_excess_pp"]:.1f} after a 1% drag. But it has been below its mid-2008 relative high ever since; both recent decades were flat before costs and negative after. SPMO's monthly moves track this series closely (correlation {q4["spmo_vs_french_big_high_monthly_corr_2018_on"]:.2f}). This passes the pre-set base-rate check on decade count, but the recent two decades are the ones that look like today's market.</p>
</section>
<section>
  <h2>5 · Simple alternatives on the same dates</h2>
  <div class="tbl"><table><thead><tr><th>Fund</th><th>Yearly, 2018–Oct 2026</th><th>2018–2023</th><th>2024–Oct 2026</th><th>Worst fall</th></tr></thead><tbody>{ctrl_rows}</tbody></table></div>
  <p style="margin-top:10px">0.10% to buy and sell, dividends reinvested, before tax and currency. QQQ beat SPMO over the full period with a deeper fall; it was also chosen with hindsight, so it is not a recommendation.</p>
</section>
<section class="box">
  <h2>Decision and next step</h2>
  <p><b>Reject SPMO and the "buy a momentum fund" idea as the replacement.</b> Its advantage depends on one recent period, a few stocks and higher risk. Do not add a switch that holds it only in good years; that is fitting the chart.</p>
  <p><b>Next experiment, if wanted:</b> run the current Aurel2 strategy on the same 2018–2026 dates against SPY, gold and a 50/50 mix, using these same costs. This was planned in the handoff and never done, and it shows whether the system already running beats the simple options. Any new idea after that needs its own economic reason and its rules recorded before it is tested.</p>
</section>
<section>
  <h2>Verified, assumed, out of scope</h2>
  <div class="vao">
    <div><h4>Verified</h4>Rules recorded and pushed before any result. Holdings rebuild matches actual returns. Results do not change across three start dates. A separate reviewer recalculated every gate figure independently and found one error, in how stock splits were handled in the holdings rebuild. It is fixed and no gate changed.</div>
    <div><h4>Assumed</h4>Yahoo adjusted closes include dividends. Current sector labels apply to past holdings. About 2–4% of weight in delisted stocks is priced from SEC filings or left out. Academic portfolios carry no trading costs unless stated.</div>
    <div><h4>Out of scope</h4>Future returns. Romanian tax, currency and broker access. A copy of SPMO's exact rules. Any change to Aurel or live trading.</div>
  </div>
</section>
<section>
  <h2>Sources</h2>
  <ul class="plain">
    <li><a href="{REPO}/protocol.json">Recorded rules</a>, <a href="{REPO}/analyze.py">analysis code</a> and <a href="{REPO}/report.py">this report's code</a>.</li>
    <li><a href="{NPORT_URL}">SPMO quarterly holdings filings at the SEC</a> and the <a href="{METHOD_URL}">S&amp;P momentum index rules</a>.</li>
    <li><a href="{FRENCH_URL}">Kenneth French size and momentum portfolios</a>.</li>
  </ul>
</section>
</main>
</div>
</div>
<script>
const D1 = {{spmo: {series_json(spmo_rel)}, mtum: {series_json(mtum_rel)}}};
const D2 = {series_json(long_rel)};
function draw(id, series, colors, names, opts) {{
  const box = document.getElementById(id), svg = box.querySelector('svg'), W = 520, H = 260, L = 44, R = 12, T = 10, B = 26;
  const ns = 'http://www.w3.org/2000/svg', css = getComputedStyle(document.documentElement);
  const t = series[0].map(p => +new Date(p[0]));
  const vals = series.flat().map(p => opts.log ? Math.log10(p[1]) : p[1]);
  const lo = Math.min(...vals), hi = Math.max(...vals);
  const x = v => L + (v - t[0]) / (t[t.length - 1] - t[0]) * (W - L - R);
  const y = v => T + (hi - (opts.log ? Math.log10(v) : v)) / (hi - lo) * (H - T - B);
  const el = (n, a) => {{ const e = document.createElementNS(ns, n); for (const k in a) e.setAttribute(k, a[k]); svg.appendChild(e); return e; }};
  for (const v of opts.ticks) {{
    el('line', {{x1: L, x2: W - R, y1: y(v), y2: y(v), stroke: 'var(--grid)', 'stroke-width': v === 1 ? 1.5 : 1}});
    el('text', {{x: L - 6, y: y(v) + 4, 'text-anchor': 'end', 'font-size': 11, fill: 'var(--ink-2)'}}).textContent = opts.fmt(v);
  }}
  for (const yr of opts.years) {{
    const tx = x(+new Date(yr + '-01-01'));
    el('text', {{x: tx, y: H - 8, 'text-anchor': 'middle', 'font-size': 11, fill: 'var(--ink-2)'}}).textContent = yr;
  }}
  series.forEach((s, i) => el('path', {{d: s.map((p, j) => (j ? 'L' : 'M') + x(t[j]).toFixed(1) + ' ' + y(p[1]).toFixed(1)).join(''),
    fill: 'none', stroke: colors[i], 'stroke-width': 2, 'stroke-linejoin': 'round'}}));
  const hair = el('line', {{y1: T, y2: H - B, stroke: 'var(--ink-2)', 'stroke-width': 1, opacity: 0}});
  const tip = document.createElement('div'); tip.className = 'tip'; tip.hidden = true; box.appendChild(tip);
  svg.addEventListener('pointermove', e => {{
    const r = svg.getBoundingClientRect(), px = (e.clientX - r.left) / r.width * W;
    let j = 0, best = Infinity; t.forEach((v, k) => {{ const d = Math.abs(x(v) - px); if (d < best) {{ best = d; j = k; }} }});
    hair.setAttribute('x1', x(t[j])); hair.setAttribute('x2', x(t[j])); hair.setAttribute('opacity', .5);
    tip.textContent = ''; const h = document.createElement('div'); h.textContent = series[0][j][0]; tip.appendChild(h);
    series.forEach((s, i) => {{ const d = document.createElement('div'); d.textContent = s[j][1].toFixed(2) + '  ' + names[i]; tip.appendChild(d); }});
    tip.hidden = false; const left = x(t[j]) / W * r.width; tip.style.left = Math.min(left + 14, r.width - 150) + 'px'; tip.style.top = '28px';
  }});
  svg.addEventListener('pointerleave', () => {{ tip.hidden = true; hair.setAttribute('opacity', 0); }});
}}
draw('c1', [D1.spmo, D1.mtum], ['var(--series-1)', 'var(--series-2)'], ['SPMO ÷ SPY', 'MTUM ÷ SPY'],
  {{ticks: [0.8, 1, 1.2, 1.4, 1.6], fmt: v => v.toFixed(1), years: [2018, 2020, 2022, 2024, 2026]}});
draw('c2', [D2], ['var(--series-1)'], ['momentum ÷ market'],
  {{log: true, ticks: [1, 2, 5, 10, 20], fmt: v => v + '×', years: [1930, 1950, 1970, 1990, 2010]}});
</script>
'''
    (OUT / 'index.html').write_text(page)
    print('wrote', OUT / 'index.html', 'verdict', verdict, 'R1', r1, 'R2', r2, 'R3', r3, 'continue', cont)


if __name__ == '__main__':
    main()
