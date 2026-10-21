"""Build a local, self-contained review page from the saved simulation outputs."""
import json
from pathlib import Path
import shutil
import sys
import zipfile

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from research.multiasset.engine import DATA, HERE, PROTOCOL


def main():
    output = DATA / "results"
    summary = json.loads((output / "summary.json").read_text())
    if any(summary["metrics"][name]["screen_verdict"] != "REJECT_THIS_SPECIFICATION" for name in PROTOCOL["candidates"]):
        raise ValueError("Results changed: review the report narrative before publishing")
    names = {"spy": "SPY buy-and-hold", "static": "Diversified allocation", "spy_btc": "90% SPY + 10% Bitcoin",
             "price": "Price trends", "economic": "Price + economic trends", "ml": "Model-assisted trends"}
    curves = {}
    for name in names:
        df = pd.read_csv(output / f"{name}-daily.csv", parse_dates=["date"]).set_index("date")
        curves[name] = {}
        for period, start in PROTOCOL["periods"].items():
            monthly = (1+df.loc[start:, "return"]).resample("ME").prod()-1
            curves[name][period] = [[str(date.date()), float(value)] for date, value in monthly.items()]
    payload = json.dumps({"summary": summary, "curves": curves, "names": names}, allow_nan=False)
    template = '''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Aurel3 · Multi-asset validation</title><style>
:root{--ink:#18312f;--muted:#536560;--line:#cbd7d1;--paper:#f3f6f2;--card:#fff;--accent:#176c78;--fail:#a22e32;--pass:#23734b}
*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font:16px/1.55 Charter,Georgia,serif}
header{padding:28px 40px;border-bottom:1px solid var(--line);background:#e5ece5;display:flex;align-items:center;justify-content:space-between;gap:20px}
h1{font:600 30px/1.2 Charter,Georgia,serif;margin:6px 0}h2{font-size:23px;margin:0 0 16px}h3{font-size:18px;margin:0 0 8px}
.eyebrow,.pill,th,label,aside,.small,button,select{font-family:ui-sans-serif,system-ui,sans-serif}.eyebrow{font-size:12px;letter-spacing:2px;text-transform:uppercase;color:var(--muted)}
.pill{font-size:12px;font-weight:700;white-space:nowrap;border:1px solid var(--fail);color:var(--fail);padding:7px 12px;border-radius:20px}
main{display:grid;grid-template-columns:250px minmax(0,1fr);gap:28px;max-width:1500px;margin:28px auto;padding:0 32px 50px}aside{font-size:14px}aside section{padding:20px 0;border-bottom:1px solid var(--line)}
.number{font:600 34px/1.2 Charter,Georgia,serif;display:block}.muted{color:var(--muted)}.small{font-size:13px}.fail{color:var(--fail)}.pass{color:var(--pass)}
article>section{padding:26px;background:var(--card);border:1px solid var(--line);border-radius:8px;margin-bottom:22px}p{margin:0 0 14px}p:last-child{margin-bottom:0}
a{color:var(--accent);text-underline-offset:3px}a:hover{color:var(--ink)}.toolbar{display:flex;justify-content:space-between;gap:14px;align-items:center;margin-bottom:18px}
select{padding:8px;border:1px solid var(--line);border-radius:5px;background:white;color:var(--ink);font-size:14px}table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}td,th{text-align:right;border-bottom:1px solid var(--line);padding:11px 8px;font-size:14px}th{font-size:12px;color:var(--muted)}td:first-child,th:first-child{text-align:left}.scroll{overflow:auto}svg{width:100%;height:auto;display:block}.legend{display:flex;flex-wrap:wrap;gap:16px;font:12px ui-sans-serif,system-ui}.dot{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:6px}
ul,ol{padding-left:22px;margin:10px 0}li{margin:7px 0}.cards{display:grid;grid-template-columns:repeat(3,1fr);gap:20px}.cards>div{border-top:3px solid var(--line);padding-top:12px}.path{overflow-wrap:anywhere;font:12px ui-monospace,monospace}
details{border-top:1px solid var(--line);padding:14px 0}summary{cursor:pointer;font-weight:bold}.badge{font:11px ui-sans-serif,system-ui;color:var(--fail)}
@media(max-width:850px){header{padding:22px;align-items:flex-start;flex-direction:column}main{grid-template-columns:1fr;padding:0 16px;gap:12px}aside{display:grid;grid-template-columns:repeat(2,1fr);gap:16px}aside section{padding:10px}.cards{grid-template-columns:1fr}.toolbar{align-items:flex-start;flex-direction:column}article>section{padding:20px}h1{font-size:27px}}
</style></head><body>
<header><div><div class="eyebrow">Aurel3 / Research decision 01</div><h1>Broader markets. Still no qualifying edge.</h1><div class="small muted">Historical rejection screen · Through <span id="lastDate"></span> · Research only</div></div><span class="pill">0 OF 3 CANDIDATES QUALIFY</span></header>
<main><aside>
<section><span class="number">3</span>Frozen candidate rules<br><span class="muted">Price · Economics · Model</span></section>
<section><span class="number" id="variants"></span>Recorded simulations<br><span class="muted">Controls and stress tests included</span></section>
<section><h3>Decision gates</h3><p class="fail">✕ SPY + 3 points after costs</p><p class="pass">✓ Lower observed drawdowns</p><p class="fail">✕ Return hurdle under cost stress</p><p class="muted">Pending: actual instruments, taxes, FX and release timestamps</p></section>
<section><h3>Assumptions</h3>USD25,000 illustration<br>Weekly decisions<br>No leverage / no shorts<br>25bps per ETF trade<br>75bps per crypto trade<br>USD1 minimum fee</section>
<section><h3>Review files</h3><p><a href="summary.json">All results</a><br><a href="../protocol.json">Frozen protocol</a><br><a href="../manifest.json">Input fingerprints</a><br><a href="annual-returns.csv">Annual returns</a><br><a href="model-training-audit.csv">Model chronology</a><br><a href="research-bundle.zip">Download research bundle</a></p></section>
</aside><article>
<section><h2>The verdict</h2><p>The tested weekly, long/cash portfolios reduce losses, but give up too much return to replace SPY. Adding economic data or the fixed learning model does not clear the agreed return hurdle. These exact specifications are rejected.</p><p>A passive SPY/Bitcoin control leads over the longer sample, but its recent advantage is small and its recent drawdown is worse. That is exposure to a winning asset, not evidence that the models predict better.</p><p class="small muted">This does not reject all global-macro, futures, options or crypto strategies. They were not all tested. Nothing has been connected to live recommendations.</p></section>
<section><div class="toolbar"><h2 style="margin:0">Comparable results</h2><label>Period <select id="period"><option value="walk_forward_comparison">2013–latest</option><option value="recent">2022–latest</option><option value="full">2008–latest</option></select></label></div>
<p class="small muted">Annualized USD total-return proxies after modeled trading costs. Before tax, FX conversion and subscriptions. Drawdowns use daily closing marks.</p>
<div class="scroll"><table><thead><tr><th>Portfolio</th><th>Return / year</th><th>Worst drawdown</th><th>Volatility</th><th>Orders / month</th></tr></thead><tbody id="results"></tbody></table></div>
<div style="margin-top:24px"><svg id="chart" viewBox="0 0 900 300" role="img" aria-label="Growth of 100 across the selected period"></svg><div id="legend" class="legend"></div></div></section>
<section><h2>What changed when stressed</h2><div class="scroll"><table><thead><tr><th>Annualized return, 2013–latest</th><th>Price</th><th>Economic</th><th>Model</th></tr></thead><tbody id="stress"></tbody></table></div><p class="small muted" style="margin-top:14px">Removing an asset group leaves its budget in cash. Nearby lookbacks and alternate lags are sensitivity checks, not a search for a new winner.</p></section>
<section><h2>Risk comparison and uncertainty</h2><div id="risk"></div><p class="small muted">The risk-matched SPY/cash comparison uses full-period realized volatility and is only a diagnostic. It is not a tradable forecast. Bootstrap intervals use six-month blocks and do not correct for strategy selection. No statistical confidence claim is used to promote a candidate.</p></section>
<section><h2>What was actually tested</h2><div class="cards"><div><h3>Price trends</h3><p>Three- to twelve-month trends across 13 instruments. Fixed group budgets; volatility determines sizes within each group. Unused capital goes to short Treasury bills.</p></div><div><h3>Economic trends</h3><p>The same portfolio, adjusted using first-release payroll and inflation changes. A deliberately simple US macro hypothesis, not a replication of an institutional model.</p></div><div><h3>Model-assisted</h3><p>A fixed nonlinear ridge model refitted annually on earlier data only. Forecast labels must finish before training. No language-model hindsight or synthetic headlines.</p></div></div>
<details><summary>Markets and the proxy limitation</summary><p>Equities: SPY, EFA, EEM, IWM. Bonds: IEF, TLT. Commodities: GLD, DBC. Currencies: UUP, FXE, FXY. Crypto: BTC and ETH spot. Cash proxy: BIL. Fund proxies carry their own fees and exposure mechanics; these are not tests of direct FX, commodity futures or options. Availability in your actual accounts is unverified. The surviving universe was selected today.</p></details>
<details><summary>Manual execution and accounting</summary><p>Signals are generated after the last US session of each week. ETF fills use the next US open; crypto uses the next UTC opening after that date. At the US signal time, only the previous UTC crypto close is available. Simulations track cash, holdings, individual fills, fees, missed decisions and a third-session delay. Orders below max(USD100, 1% NAV) are suppressed. Fractional adjusted-price units are research units, not literal shares or certified executable orders.</p></details>
<details><summary>Verified / assumed / out of scope</summary><p><strong>Verified:</strong> input hashes, first-release columns, training chronology, delayed fills, fees, cash conservation and reproducible results. <strong>Assumed:</strong> macro values become usable 90 days after the observation month; 120 days is a stress case. Generic costs, capital and fractional fills are scenarios. One cash pool is assumed; broker transfer delays are not modeled. <strong>Out of scope:</strong> original release timestamps, broker-specific tax/FX/lot feasibility, options/futures/margin, live profitability and a globally optimal strategy.</p><p>The first-release files avoid revised-value leakage, but lack original release dates. The macro replay is therefore not fully certified point-in-time. BTC/ETH selection benefits from hindsight; the no-crypto tests expose that dependency. Recent history is not an untouched holdout.</p></details>
</section>
<section><h2>Aurel3 integration decision</h2><p>The existing manual desk already proposes orders and records confirmed fills. This research adds no live orders or alerts. A future qualifying strategy can use that workflow after account-specific cash, currency conversion, instrument identifiers and derivative accounting are implemented and validated.</p><p><strong>Next research question:</strong> can long/short, capital-efficient market exposure deliver a large enough net advantage while remaining practical for manual execution? That needs separate financing, margin and instrument data. Adding complexity to these failed rules is not a validated improvement.</p></section>
<section><h2>Reproduce and inspect</h2><p class="path">research/multiasset/fetch.py → run.py → test_engine.py → report.py</p><p><a href="annual-returns.csv">Annual returns</a>, <a href="rolling-three-years.csv">rolling three-year windows</a>, <a href="price-fills.csv">price-strategy fills</a>, <a href="economic-fills.csv">economic-strategy fills</a> and <a href="ml-fills.csv">model-strategy fills</a> are available for inspection.</p><p class="small">Sources: <a href="https://www.philadelphiafed.org/surveys-and-data/real-time-data-research/first-second-third">Philadelphia Fed original-release data</a> · <a href="https://www.aqr.com/Insights/Research/White-Papers/Economic-Trend">Economic Trend</a> · <a href="https://www.aqr.com/Insights/Research/Journal-Article/A-Century-of-Evidence-on-Trend-Following-Investing">Historical trend research</a> · <a href="https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf">Selection-bias research</a>. Price files were downloaded through yfinance; see the input manifest for versions and hashes.</p></section>
</article></main><script>
const data=__PAYLOAD__, metrics=data.summary.metrics;
const colors={spy:'#203d43',static:'#879c8b',spy_btc:'#af7927',price:'#237b83',economic:'#72944d',ml:'#9b5276'};
const percent=x=>(100*x).toFixed(2)+'%';
document.getElementById('lastDate').textContent=data.summary.last_price_date;
document.getElementById('variants').textContent=data.summary.variant_count;
function render(){const period=document.getElementById('period').value;
 document.getElementById('results').innerHTML=Object.entries(data.names).map(([k,label])=>{const m=metrics[k][period];return `<tr><td><a href="${k}-daily.csv">${label}</a></td><td>${percent(m.cagr)}</td><td>${percent(m.max_drawdown)}</td><td>${percent(m.volatility)}</td><td>${m.orders_per_month.toFixed(1)}</td></tr>`}).join('');
 const start={full:'2008-01-01',walk_forward_comparison:'2013-01-01',recent:'2022-01-01'}[period];
 const series=Object.entries(data.curves).map(([k,periods])=>{let value=100;return [k,[100,...periods[period].map(r=>value*=1+r[1])]]});
 const max=Math.max(...series.flatMap(s=>s[1])), n=Math.max(...series.map(s=>s[1].length));
 const y=v=>260-v/max*225, xx=i=>55+i/(n-1)*815;let svg='';
 for(let j=0;j<=4;j++){const v=max*j/4;svg+=`<line x1="55" y1="${y(v)}" x2="870" y2="${y(v)}" stroke="#dce4df"/><text x="47" y="${y(v)+4}" text-anchor="end" fill="#536560" font-size="12">${Math.round(v)}</text>`}
 for(const [k,vs]of series)svg+=`<polyline fill="none" stroke="${colors[k]}" stroke-width="2" points="${vs.map((v,i)=>xx(i)+','+y(v)).join(' ')}"/>`;
 svg+=`<text x="55" y="290" fill="#536560" font-size="12">${start.slice(0,4)} · start 100</text><text x="870" y="290" text-anchor="end" fill="#536560" font-size="12">${data.summary.last_price_date}</text>`;
 document.getElementById('chart').innerHTML=svg;
 document.getElementById('legend').innerHTML=Object.entries(data.names).map(([k,n])=>`<span><i class="dot" style="background:${colors[k]}"></i>${n}</span>`).join('');
}
const stresses=[['Base',''],['Double trading costs','__double_cost'],['Third-session execution','__delay3'],['Skip roughly 20% of decisions','__skip20'],['Remove crypto','__without_crypto'],['Remove equities','__without_equity'],['Remove bonds','__without_bond'],['Remove commodities','__without_commodity'],['Remove currencies','__without_currency'],['Macro lag 120 days','__lag120'],['Shorter lookbacks','__shorter'],['Longer lookbacks','__longer']];
document.getElementById('stress').innerHTML=stresses.map(([name,suffix])=>`<tr><td>${name}</td>${['price','economic','ml'].map(k=>`<td>${metrics[k+suffix]?percent(metrics[k+suffix].walk_forward_comparison.cagr):'—'}</td>`).join('')}</tr>`).join('');
document.getElementById('risk').innerHTML=['price','economic','ml'].map(k=>{const m=metrics[k],r=data.summary.risk_matched_diagnostic[k];return `<p><strong>${data.names[k]}:</strong> ${percent(m.walk_forward_comparison.cagr)} versus ${percent(r.benchmark_cagr)} for the lower-risk SPY/cash diagnostic. Descriptive 95% interval for excess annual return versus full SPY: ${percent(m.excess_uncertainty.lower_95)} to ${percent(m.excess_uncertainty.upper_95)}.</p>`}).join('');
document.getElementById('period').addEventListener('change',render);render();
</script></body></html>'''
    (output / "index.html").write_text(template.replace("__PAYLOAD__", payload))
    shutil.copy2(HERE / "protocol.json", DATA / "protocol.json")
    shutil.copy2(HERE / "README.txt", output / "README.txt")
    with zipfile.ZipFile(output / "research-bundle.zip", "w", zipfile.ZIP_DEFLATED) as bundle:
        for p in HERE.glob("*"):
            if p.is_file():
                bundle.write(p, "code/" + p.name)
        for p in DATA.glob("*"):
            if p.is_file():
                bundle.write(p, "inputs/" + p.name)
        for p in output.glob("*"):
            if p.is_file() and p.suffix != ".zip":
                bundle.write(p, "results/" + p.name)
    print(output / "index.html")


if __name__ == "__main__":
    main()
