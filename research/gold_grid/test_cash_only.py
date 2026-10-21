import json

import numpy as np
import pytest

import cash_only
from redesign import Assumptions, simulate
from test_redesign import fixture


def evidence():
    _, curve, ledger = simulate(fixture(), {'name':'mix_1x', 'family':'mix', 'cap':1},
                                2020, Assumptions(annual_gold_holding_cost=0))
    return curve, ledger


def test_cash_only_rejects_hidden_rebalance_loan():
    curve, ledger = evidence()
    ledger.loc[0, 'cash_before'] = -10
    with pytest.raises(ValueError, match='Borrowed cash during rebalance'):
        cash_only.check_cash_only(curve, ledger)


@pytest.mark.parametrize('column,value,message', [
    ('cash', -1, 'Borrowed cash'),
    ('gold_units', -.01, 'Short position'),
    ('exposure', 1.01, 'Exposure exceeds'),
    ('funding_cumulative', .01, 'Financing charge'),
    ('equity', np.nan, 'nonfinite'),
])
def test_cash_only_rejects_account_violation(column, value, message):
    curve, ledger = evidence()
    curve.iloc[4, curve.columns.get_loc(column)] = value
    with pytest.raises(ValueError, match=message):
        cash_only.check_cash_only(curve, ledger)


def test_roundoff_is_not_reported_as_economic_borrowing():
    curve, ledger = evidence()
    result = cash_only.check_cash_only(curve, ledger)
    assert result['maximum_exposure'] <= 1+1e-12
    assert result['maximum_funding'] < 1e-7


def test_changed_evidence_stops_audit(tmp_path, monkeypatch):
    frozen = tmp_path/'input.csv'
    frozen.write_text('original')
    protocol = tmp_path/'protocol.json'
    protocol.write_text(json.dumps({'frozen_files':{str(frozen):cash_only.digest(frozen)},
                                    'eligible_specs':[]}))
    monkeypatch.setattr(cash_only, 'PROTOCOL', protocol)
    frozen.write_text('different prices')
    with pytest.raises(ValueError, match='Frozen evidence changed'):
        cash_only.load_frozen()
