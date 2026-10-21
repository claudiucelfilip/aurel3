"""Audit the frozen cash-only subset without searching for new parameters."""
from dataclasses import asdict
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from allocation import audit
from redesign import Assumptions, OUT

HERE = Path(__file__).parent
PROTOCOL = HERE / 'cash_only_protocol.json'
MONEY_TOLERANCE = 1e-7
EXPOSURE_TOLERANCE = 1e-12


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_frozen():
    protocol = json.loads(PROTOCOL.read_text())
    for path, expected in protocol['frozen_files'].items():
        if digest(path) != expected:
            raise ValueError(f'Frozen evidence changed: {path}; record a new research round.')
    for spec in protocol['eligible_specs']:
        if not np.isfinite(spec['cap']) or not 0 <= spec['cap'] <= 1:
            raise ValueError(f'Ineligible exposure: {spec}')
    return protocol


def check_cash_only(curve, ledger):
    columns = ['equity', 'gross_equity', 'cash', 'spy_units', 'gold_units',
               'exposure', 'funding_cumulative']
    if curve.empty or not np.isfinite(curve[columns]).all().all():
        raise ValueError('Missing or nonfinite portfolio evidence')
    if (curve[['spy_units', 'gold_units']] < -EXPOSURE_TOLERANCE).any().any():
        raise ValueError('Short position')
    if (curve[['equity', 'gross_equity']] <= 0).any().any():
        raise ValueError('Nonpositive equity')
    if curve.cash.min() < -MONEY_TOLERANCE:
        raise ValueError('Borrowed cash')
    if curve.exposure.max() > 1 + EXPOSURE_TOLERANCE:
        raise ValueError('Exposure exceeds owned capital')
    if curve.funding_cumulative.abs().max() > MONEY_TOLERANCE:
        raise ValueError('Financing charge')
    if not ledger.empty:
        if not np.isfinite(ledger.select_dtypes('number')).all().all():
            raise ValueError('Nonfinite trade evidence')
        if ledger[['cash_before', 'cash_after']].min().min() < -MONEY_TOLERANCE:
            raise ValueError('Borrowed cash during rebalance')
        flow = ledger.cash_before - ledger.spy_units*ledger.spy_price
        flow -= ledger.gold_units*ledger.gold_price + ledger.fee + ledger.cash_after
        if flow.abs().max() > MONEY_TOLERANCE:
            raise ValueError('Unexplained trade cashflow')
    return {'sessions':len(curve), 'trade_days':len(ledger),
            'minimum_cash':float(curve.cash.min()),
            'maximum_exposure':float(curve.exposure.max()),
            'maximum_funding':float(curve.funding_cumulative.abs().max())}


def trial_inventory():
    groups = {
        'result_snapshot.json':['baseline', 'sensitivity', 'stress', 'fresh_starts'],
        'loss_control_snapshot.json':['main', 'sensitivity', 'cost_stress'],
        'profit_lock_snapshot.json':['main'],
    }
    rows = []
    for file, keys in groups.items():
        data = json.loads((HERE/file).read_text())
        rows.append({'file':file, 'groups':{k:len(data[k]) for k in keys}})
    data = json.loads((HERE/'redesign_snapshot.json').read_text())
    for stage, keys in {
        'redesign':['main', 'neighbors', 'stress', 'fresh_starts'],
        'allocation':['main', 'old_period', 'stress', 'neighbors'],
        'audit':['additional_2019_results', 'funding_diagnostic'],
    }.items():
        rows.append({'file':'redesign_snapshot.json', 'stage':stage,
                     'groups':{k:len(data[stage][k]) for k in keys}})
    return rows


def main():
    p = load_frozen()
    r = json.loads((OUT/'redesign_results.json').read_text())
    a = json.loads((OUT/'allocation_results.json').read_text())
    v = json.loads((OUT/'redesign_audit.json').read_text())
    frame = pd.read_csv(OUT/'allocation_etf_inputs.csv', index_col=0, parse_dates=True)
    assumptions = Assumptions(annual_gold_holding_cost=0)
    if asdict(assumptions) != p['assumptions']:
        raise ValueError('Frozen assumptions changed')
    checks, summaries = {}, {}
    for year in p['evaluation_starts']:
        for spec in p['eligible_specs']:
            name = spec['name']
            key = f'etf_{year}_{name}'
            curve = pd.read_csv(OUT/f'allocation_{key}_daily.csv', index_col=0, parse_dates=True)
            ledger = pd.read_csv(OUT/f'allocation_{key}_trades.csv')
            checks[key] = check_cash_only(curve, ledger)
            checks[key]['accounting'] = audit(frame, curve, ledger, assumptions)
            s = v['additional_2019_results'][name] if year==2019 else a['main'][key]
            if abs(s['ending_equity']-curve.equity.iloc[-1]) > MONEY_TOLERANCE:
                raise ValueError(f'Summary does not match curve: {key}')
            summaries[key] = s
    names = {s['name'] for s in p['eligible_specs']}
    all_specs = r['protocol']['strategies']+r['protocol']['controls']+a['protocol']['variants']
    excluded = [s for s in all_specs if s['name'] not in names]
    beats = [n for n in names-{'SPY','gold'} if all(
        summaries[f'etf_{y}_{n}']['ending_equity'] > max(
            summaries[f'etf_{y}_{b}']['ending_equity'] for b in ['SPY','gold'])
        for y in [2020,2022])]
    result = {'status':'Retrospective audit; no independently validated winner',
              'protocol_sha256':digest(PROTOCOL), 'eligible_specs':p['eligible_specs'],
              'checks':checks, 'summaries':summaries, 'excluded_specs':excluded,
              'beat_both_2020_and_2022':beats, 'trial_inventory':trial_inventory(),
              'trial_count_warning':'Saved simulation rows are overlapping, correlated and include controls. Not an independent trial count. Earlier related studies and informal choices are incompletely inventoried; no DSR/PBO confidence number is justified.',
              'rolling':{m:{n:x for n,x in values.items() if n in names}
                         for m,values in a['rolling'].items()}}
    encoded = json.dumps(result, indent=2, allow_nan=False)
    (OUT/'cash_only_results.json').write_text(encoded)
    (HERE/'cash_only_snapshot.json').write_text(encoded)
    print(f'Audited {len(checks)} frozen curves; {len(beats)} beat both benchmarks in both recent starts.')


if __name__=='__main__':
    main()
