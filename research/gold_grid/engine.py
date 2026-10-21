"""Research-only long gold grid. No broker connection or trading API."""
from dataclasses import dataclass, asdict

import numpy as np
from numba import njit


@dataclass(frozen=True)
class Settings:
    capital: float = 10000.0
    initial_ounces: float = 1.0
    grid_dollars: float = 10.0
    target_dollars: float = 1.0
    multiplier: float = 2.0
    leverage: float = 20.0
    stopout_fraction: float = 0.5
    commission_per_ounce: float = 0.035
    slippage_per_ounce: float = 0.05
    annual_financing: float = 0.05
    path: int = 0  # 0: open-low-high-close; 1: open-high-low-close.
    max_entries: int = 0
    max_notional_multiple: float = 0.0
    batch_loss_fraction: float = 0.0
    cooldown_hours: float = 0.0
    account_drawdown_fraction: float = 0.0
    drawdown_activation_multiple: float = 1.0


@njit(cache=True)
def core(times, bars, capital, base, gap, target, multiplier, leverage,
         stopout, commission, slippage, financing, path, record,
         max_entries, max_notional, batch_loss, cooldown, account_drawdown, activation_multiple):
    n = len(times)
    equity = np.full(n, capital, dtype=np.float64)
    balances = np.full(n, capital, dtype=np.float64)
    quantities = np.zeros(n)
    cash, qty, basis = capital, 0.0, 0.0
    last_entry, next_size = 0.0, base
    start_cash, start_i, max_qty = capital, 0, 0.0
    peak, max_dd, peak_exposure = capital, 0.0, 0.0
    funding, commissions, rejected = 0.0, 0.0, 0
    stopped, stop_i = False, -1
    cycles = []
    ledger = []
    previous_bid = bars[0, 0]
    entries, next_entry_time, limited_adds = 0, times[0], 0
    account_halts = 0

    for i in range(n):
        if stopped:
            equity[i], balances[i] = cash, cash
            continue
        if qty > 0 and i > 0:
            charge = qty * previous_bid * financing * (times[i]-times[i-1]) / (365.25*86400)
            cash -= charge
            funding += charge
        closed_this_bar = False
        if qty == 0:
            if account_drawdown > 0 and peak >= capital*activation_multiple and cash <= peak*(1-account_drawdown):
                stopped, stop_i = True, i
                account_halts += 1
                equity[i], balances[i] = cash, cash
                continue
            if times[i] < next_entry_time:
                equity[i], balances[i] = cash, cash
                continue
            price = bars[i, 4] + slippage
            if cash - base * (price-bars[i, 0]+commission) < base * price / leverage:
                stopped, stop_i = True, i
                equity[i], balances[i] = cash, cash
                continue
            if max_notional > 0 and base*bars[i, 4] > cash*max_notional:
                stopped, stop_i = True, i
                equity[i], balances[i] = cash, cash
                continue
            start_cash, start_i = cash, i
            cash -= base * commission
            commissions += base * commission
            qty, basis = base, base * price
            last_entry, next_size, max_qty = bars[i, 4], base*multiplier, base
            entries = 1
            if record:
                ledger.append((i, 1, base, price, cash, cash+qty*bars[i,0]-basis))

        order = (0, 2, 1, 3) if path == 0 else (0, 1, 2, 3)
        prior_bid, prior_ask = bars[i, 0], bars[i, 4]
        for node in range(4):
            j = order[node]
            dest_bid, dest_ask = bars[i, j], bars[i, j+4]
            bid, ask = prior_bid, prior_ask
            for iteration in range(100):
                if closed_this_bar or stopped:
                    break
                if iteration == 99:
                    raise RuntimeError('Too many grid events in one path segment')
                # Quote gaps are filled at the first available quote; within bars use linear paths.
                tp = (basis + start_cash-cash) / qty + target + commission + slippage
                margin_bid = (basis-cash) / (qty*(1.0-stopout/leverage))
                risk_floor, risk_kind = -np.inf, 0
                if batch_loss > 0:
                    risk_floor, risk_kind = start_cash*(1-batch_loss), 5
                if account_drawdown > 0 and peak >= capital*activation_multiple and peak*(1-account_drawdown) > risk_floor:
                    risk_floor, risk_kind = peak*(1-account_drawdown), 6
                risk_bid = (basis+risk_floor-cash)/qty + slippage+commission
                add_ask = last_entry-gap
                immediate_margin = cash + qty*bid-basis <= stopout*qty*bid/leverage
                immediate_tp = bid >= tp
                entries_available = max_entries == 0 or entries < max_entries
                immediate_add = entries_available and ask <= add_ask + 1e-9
                kind, f = 0, 2.0
                if immediate_margin:
                    kind, f = 3, 0.0
                elif risk_kind > 0 and bid <= risk_bid:
                    kind, f = risk_kind, 0.0
                elif immediate_tp:
                    kind, f = 2, 0.0
                elif immediate_add:
                    kind, f = 1, 0.0
                if kind == 0:
                    if dest_bid < bid and dest_bid <= margin_bid:
                        kind, f = 3, (margin_bid-bid)/(dest_bid-bid)
                    if risk_kind > 0 and dest_bid < bid and dest_bid <= risk_bid:
                        rf = (risk_bid-bid)/(dest_bid-bid)
                        if rf < f:
                            kind, f = risk_kind, rf
                    if dest_bid > bid and dest_bid >= tp:
                        tf = (tp-bid)/(dest_bid-bid)
                        if tf < f:
                            kind, f = 2, tf
                    if entries_available and dest_ask < ask and dest_ask <= add_ask:
                        af = (add_ask-ask)/(dest_ask-ask)
                        if af < f:
                            kind, f = 1, af
                if kind == 0 or f > 1:
                    bid, ask = dest_bid, dest_ask
                    nav = cash+qty*(bid-slippage-commission)-basis
                    peak = max(peak, nav)
                    max_dd = max(max_dd, 1-nav/peak)
                    peak_exposure = max(peak_exposure, qty*ask)
                    break
                bid += f*(dest_bid-bid)
                ask += f*(dest_ask-ask)
                nav = cash+qty*(bid-slippage-commission)-basis
                peak = max(peak, nav)
                max_dd = max(max_dd, 1-nav/peak)
                if kind == 1:
                    price = ask+slippage
                    new_equity = cash + qty*bid-basis + next_size*(bid-price-commission)
                    within_budget = max_notional == 0 or (qty+next_size)*ask <= start_cash*max_notional
                    if within_budget and new_equity >= (qty+next_size)*ask/leverage:
                        cash -= next_size*commission
                        commissions += next_size*commission
                        basis += next_size*price
                        qty += next_size
                        if record:
                            ledger.append((i, 1, next_size, price, cash, cash+qty*bid-basis))
                        next_size *= multiplier
                        last_entry = ask
                        max_qty = max(max_qty, qty)
                        entries += 1
                        peak_exposure = max(peak_exposure, qty*ask)
                    else:
                        rejected += 1
                        if not within_budget:
                            limited_adds += 1
                        # A rejected order stays pending. Advance through this segment without adding.
                        exit_bid, exit_kind = margin_bid, 3
                        if risk_kind > 0 and risk_bid > exit_bid:
                            exit_bid, exit_kind = risk_bid, risk_kind
                        if dest_bid <= exit_bid:
                            if dest_bid < bid and exit_bid < bid:
                                mf = (exit_bid-bid)/(dest_bid-bid)
                                bid += mf*(dest_bid-bid)
                                ask += mf*(dest_ask-ask)
                            else:
                                bid, ask = dest_bid, dest_ask
                            kind = exit_kind
                        elif dest_bid >= tp:
                            bid = max(bid, tp)
                            kind = 2
                        else:
                            bid, ask = dest_bid, dest_ask
                            nav = cash+qty*(bid-slippage-commission)-basis
                            peak = max(peak, nav)
                            max_dd = max(max_dd, 1-nav/peak)
                            break
                if kind == 2 or kind == 3 or kind == 5 or kind == 6:
                    price = bid-slippage
                    cash += qty*price-basis-qty*commission
                    commissions += qty*commission
                    if record:
                        ledger.append((i, kind, -qty, price, cash, cash))
                    cycles.append((start_i, i, cash-start_cash, max_qty, kind,
                                   times[i]-times[start_i]))
                    peak = max(peak, cash)
                    max_dd = max(max_dd, 1-cash/peak)
                    qty, basis = 0.0, 0.0
                    closed_this_bar = True
                    if kind == 3 or kind == 6:
                        stopped, stop_i = True, i
                        if kind == 6:
                            account_halts += 1
                    if kind == 5:
                        next_entry_time = times[i]+int(cooldown*3600)
                    break
            prior_bid, prior_ask = dest_bid, dest_ask
        previous_bid = bars[i, 3]
        equity[i] = cash + qty*(previous_bid-slippage-commission)-basis
        balances[i], quantities[i] = cash, qty
        peak = max(peak, equity[i])
        max_dd = max(max_dd, 1-equity[i]/peak)
    open_pnl = 0.0
    if qty > 0:
        open_pnl = equity[-1]-start_cash
        cycles.append((start_i, n-1, open_pnl, max_qty, 4, times[-1]-times[start_i]))
    stats = np.array([max_dd, peak_exposure, funding, commissions, rejected,
                      1.0 if stopped else 0.0, stop_i, qty, open_pnl, limited_adds, account_halts])
    return equity, balances, quantities, cycles, ledger, stats


def simulate(frame, settings=Settings(), record=False):
    assert len(frame) > 0 and frame.index.is_monotonic_increasing and frame.index.is_unique
    assert settings.initial_ounces > 0 and settings.grid_dollars > 0 and settings.target_dollars > 0
    assert settings.multiplier >= 1 and settings.leverage > 0
    assert 0 <= settings.stopout_fraction <= 1
    assert settings.max_entries >= 0 and settings.max_notional_multiple >= 0
    assert 0 <= settings.batch_loss_fraction < 1 and 0 <= settings.account_drawdown_fraction < 1
    assert settings.cooldown_hours >= 0
    assert settings.drawdown_activation_multiple >= 1
    columns = ['bid_'+x for x in ['open','high','low','close']] + ['ask_'+x for x in ['open','high','low','close']]
    values = frame[columns].to_numpy(dtype=np.float64)
    assert np.isfinite(values).all() and (values > 0).all()
    seconds = frame.index.as_unit('s').asi8
    s = settings
    result = core(seconds, values, s.capital, s.initial_ounces, s.grid_dollars,
                  s.target_dollars, s.multiplier, s.leverage, s.stopout_fraction,
                  s.commission_per_ounce, s.slippage_per_ounce, s.annual_financing, s.path, record,
                  s.max_entries, s.max_notional_multiple, s.batch_loss_fraction,
                  s.cooldown_hours, s.account_drawdown_fraction, s.drawdown_activation_multiple)
    eq, balance, qty, cycles, ledger, stats = result
    closed = [c for c in cycles if c[4] != 4]
    wins = sum(c[2] > 0 for c in closed)
    years = (seconds[-1]-seconds[0])/(365.25*86400)
    summary = {'settings': asdict(s), 'start': str(frame.index[0]), 'end': str(frame.index[-1]),
               'ending_equity': float(eq[-1]), 'ending_balance': float(balance[-1]),
               'total_return': float(eq[-1]/s.capital-1),
               'cagr': float((eq[-1]/s.capital)**(1/years)-1) if eq[-1]>0 and years>=1/365.25 else None,
               'max_drawdown': float(stats[0]), 'peak_notional': float(stats[1]),
               'financing': float(stats[2]), 'commission': float(stats[3]),
               'rejected_add_checks': int(stats[4]), 'stopped': bool(stats[5]),
               'stopped_at': str(frame.index[int(stats[6])]) if stats[6]>=0 else None,
               'stop_reason': ('margin exit' if any(c[4]==3 for c in closed) else
                               'account drawdown limit' if stats[10]>0 else
                               'initial order exceeds funding or exposure limits') if stats[5] else None,
               'open_ounces': float(stats[7]), 'open_cycle_pnl': float(stats[8]),
               'closed_cycles': len(closed), 'winning_cycles': wins,
               'win_rate': wins/len(closed) if closed else None,
               'forced_liquidations': sum(c[4]==3 for c in closed),
               'batch_loss_exits': sum(c[4]==5 for c in closed),
               'account_drawdown_halts': int(stats[10]),
               'exposure_limit_checks': int(stats[9]),
               'gross_wins': float(sum(max(0,c[2]) for c in closed)),
               'gross_losses': float(-sum(min(0,c[2]) for c in closed)),
               'largest_cycle_loss': float(min([0.0]+[c[2] for c in cycles])),
               'longest_cycle_days': float(max([0.0]+[c[5]/86400 for c in cycles]))}
    return {'summary': summary, 'equity': eq, 'balance': balance, 'quantity': qty,
            'cycles': cycles, 'ledger': ledger}
