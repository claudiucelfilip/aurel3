"""F4: copy Berkshire Hathaway's top 10 stock holdings after each 13F-HR becomes public. See protocol.json track_F_wild_batch.F4."""
import json
import sys
import pandas as pd
import wild_common as W

sys.path.insert(0, str(W.C.ROOT / 'research' / 'spmo_diagnostic'))
from holdings import figi_map  # noqa: E402  (OpenFIGI CUSIP -> ticker, cached in data/spmo_diagnostic/cusip_figi.json)
from yahoo_chart import adj_close  # noqa: E402

TOP = 10
MANUAL = {'H1467J104': 'CB', '46625H100': 'JPM', '30231G102': 'XOM', '00507V109': 'None', '25490A309': 'None'}  # delisted names Yahoo lacks are skipped


def holdings():
    raw = json.loads((W.WILD / 'berkshire_13f.json').read_text())
    out = {}
    for dt, rows in raw.items():
        df = pd.DataFrame(rows).groupby('cusip', as_index=False).agg({'value': 'sum', 'issuer': 'first'})
        out[dt] = df.sort_values('value', ascending=False).head(TOP)
    cusips = sorted({c for df in out.values() for c in df['cusip']})
    fm = figi_map(cusips)
    tick = {c: MANUAL.get(c, fm.get(c, {}).get('ticker')) for c in cusips}
    return out, tick


def main():
    adj, close = W.load_stocks()
    hold, tick = holdings()
    need = sorted({tick[c] for df in hold.values() for c in df['cusip'] if tick[c] and tick[c] != 'None'})
    missing = [t for t in need if t not in adj.columns]
    extra = {}
    for t in missing:
        s = adj_close(t, '2013-01-01', pause=1.0)
        if len(s):
            extra[t] = s
    if extra:
        adj = adj.join(pd.DataFrame(extra).reindex(adj.index))
    adj, _, _ = W.clean_stocks(adj, close.reindex(columns=adj.columns))
    unmapped = sorted({f"{df.loc[df.cusip == c, 'issuer'].iloc[0]} ({c})" for df in hold.values() for c in df['cusip']
                       if not tick[c] or tick[c] == 'None' or tick[c] not in adj.columns})
    configs = {}
    for mode in ('value', 'equal'):
        w = pd.DataFrame(0.0, index=pd.to_datetime(sorted(hold)), columns=adj.columns)
        for dt, df in hold.items():
            df = df[[tick[c] in adj.columns for c in df['cusip']]]
            tot = df['value'].sum()
            for c, v in zip(df['cusip'], df['value']):
                w.loc[pd.Timestamp(dt), tick[c]] = v / tot if mode == 'value' else 1 / len(df)
        w.index = W.next_close(adj.index, w.index)
        configs[f'top10_{mode}'] = w
    W.evaluate('track_f4_berkshire', configs, adj, dev_start='2013-08-16',
               extra={'unmapped_or_unpriced_holdings': unmapped, 'ticker_map': {c: tick[c] for c in tick}})


if __name__ == '__main__':
    main()
