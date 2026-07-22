#!/usr/bin/env python3
"""Generate outcome-neutral catalyst descriptions for the interpreter bake-off.

Why this exists: the historical_replay_cases.json file has NO real headlines,
and real archived headlines for 2024-2025 dates aren't reachable through our
tools. To compare model CALIBRATION fairly we need each case to carry a
specific, realistic catalyst that all models read identically.

Fairness discipline:
- Catalysts are authored from THEME + TICKER ARCHETYPE only, deliberately NOT
  from the case's known outcome label (action) or its notes. The generator
  never reads case['action'] or case['notes'].
- Each theme has a spread of confirmation strengths (confirmed / reported /
  early / mixed) assigned by a stable hash of the case id — so difficulty
  varies independently of whether the trade actually worked. This gives the
  models room to DIFFER in confidence; a benchmark where all inputs are
  slam-dunks measures nothing.
- This is authored text, not quoted news. It tests "given a fair, specific
  catalyst of this type, how well-calibrated is each model?" — the same input
  class Aurel3's own historical_replay.py already uses, just richer.

Output: data/bakeoff_catalysts.json  { case_id: {catalyst, strength} }
"""
from __future__ import annotations
import json
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CASES = json.loads((REPO / "data" / "historical_replay_cases.json").read_text())
OUT = REPO / "data" / "bakeoff_catalysts.json"

# Four confirmation strengths per theme. Order matters: index via stable hash so
# each case gets a fixed but outcome-independent difficulty.
#   confirmed  -> hard, named, official (should map to high/actionable)
#   reported   -> credible source, not yet official (medium-ish)
#   early      -> real driver but no specific catalyst yet (interesting_but_early)
#   mixed      -> genuine catalyst with an offsetting negative (tests nuance)
THEME_CATALYSTS = {
    "AI / compute infrastructure": {
        "confirmed": "{t} reported quarterly datacenter/AI revenue well above consensus and raised forward guidance, citing confirmed hyperscaler orders and a named next-gen product ramp.",
        "reported": "Multiple outlets report {t} is seeing accelerating AI-related demand; a supply-chain check suggests order growth, but the company has not confirmed figures.",
        "early": "Analysts argue {t} is positioned to benefit from the AI compute buildout, but there is no specific order, contract, or earnings catalyst yet — a thematic call.",
        "mixed": "{t} beat on AI-segment revenue but guided gross margins lower and flagged supply constraints, leaving the near-term setup ambiguous.",
    },
    "EU defense / rearmament": {
        "confirmed": "A named EU government approved a large special defense budget and {t} confirmed a specific multi-billion framework contract with a national ministry.",
        "reported": "Reports indicate {t} is a frontrunner for upcoming European procurement tied to higher defense budgets, but no contract has been signed.",
        "early": "Rising European defense-spending rhetoric favors {t} thematically, but no specific award or order has been announced.",
        "mixed": "{t} won a defense award, but the contract is smaller than expected and delivery is back-end-loaded, muting the near-term impact.",
    },
    "Energy / geopolitical supply risk": {
        "confirmed": "Crude spiked on a confirmed, observable supply disruption (shipping blockage / sanctions enforcement); {t} has direct upstream exposure to the affected barrels.",
        "reported": "Geopolitical tension is raising supply-risk premia and {t} would benefit, but the disruption is threatened rather than confirmed.",
        "early": "Elevated geopolitical risk is supportive for {t} in theory, but there is no active supply disruption — sentiment, not event.",
        "mixed": "Oil rose on supply fears, but demand-side data softened the same week, leaving {t}'s setup two-sided.",
    },
    "Healthcare / commercialization": {
        "confirmed": "{t} announced a positive, company-specific regulatory or commercial milestone (approval, pivotal trial readout, or guidance raise) with clear revenue implications.",
        "reported": "{t} released clinical or launch data that looks encouraging, but the commercial magnitude and reimbursement path remain unconfirmed.",
        "early": "The therapeutic area is drawing optimism and {t} is a plausible beneficiary, but no company-specific catalyst has landed.",
        "mixed": "{t} reported a trial success on the primary endpoint but flagged a safety signal, creating a genuinely mixed readout.",
    },
    "Battery / storage commercialization": {
        "confirmed": "{t} announced funded production capacity or a named customer order for its battery/EV technology, moving beyond the lab stage.",
        "reported": "{t} reported progress on its battery/EV roadmap; encouraging but not yet backed by orders or a production timeline.",
        "early": "{t} disclosed a technology milestone with no commercialization timeline, customers, or revenue — pre-commercial and speculative.",
        "mixed": "{t} showed a technical milestone but simultaneously guided deliveries lower and flagged cash burn, a two-sided setup.",
    },
    "Banking / rates / credit": {
        "confirmed": "{t} reported earnings with net interest income and credit metrics clearly beating expectations, with direct rate sensitivity confirmed in the print.",
        "reported": "The rates backdrop looks favorable for {t} and early data points are positive, but the quarter has not been reported.",
        "early": "Macro rate expectations favor lenders like {t}, but there is no company-specific catalyst — a top-down call.",
        "mixed": "{t} beat on net interest income but raised credit-loss provisions, leaving the quarter's read ambiguous.",
    },
    "Commodities / resource supply shock": {
        "confirmed": "The underlying commodity moved sharply on a confirmed supply constraint; {t} has primary extraction exposure to that commodity.",
        "reported": "Reports point to a tightening supply picture that would benefit {t}, but the constraint is not yet confirmed or observable in inventories.",
        "early": "A structural demand narrative supports {t}'s commodity, but there is no acute supply catalyst — thematic positioning.",
        "mixed": "The commodity rose on supply fears while broad risk-off pressured miners, leaving {t}'s near-term setup conflicted.",
    },
    "Critical materials / battery inputs": {
        "confirmed": "A confirmed supply bottleneck or policy action on a critical material directly benefits {t}, which has primary exposure to that input.",
        "reported": "Supply-chain reports suggest tightening for a critical material {t} produces, but the bottleneck is not confirmed.",
        "early": "Long-term critical-materials scarcity favors {t}, but there is no acute catalyst or price shock underway.",
        "mixed": "The material's price rose, but {t} also flagged higher production costs and a project delay, muddying the setup.",
    },
    "Agriculture / food supply": {
        "confirmed": "A confirmed agricultural-input supply disruption is repricing the sector; {t} is a direct beneficiary with primary exposure.",
        "reported": "Reports point to tightening ag-input supply that would help {t}, but the disruption is not yet confirmed.",
        "early": "A food-supply narrative favors {t} thematically, but there is no specific catalyst or price move yet.",
        "mixed": "Ag prices rose on supply worries, but {t} guided margins lower on input costs, a two-sided read.",
    },
    "Infrastructure / industrial capex": {
        "confirmed": "{t} confirmed a specific, named order or backlog tied to an infrastructure/electrification capex cycle, with clear revenue visibility.",
        "reported": "{t} is reported to be winning share in an industrial-capex upcycle, but no specific order has been confirmed.",
        "early": "Broad industrial/electrification capex optimism favors {t}, but the linkage is macro rather than a specific award.",
        "mixed": "{t} reported strong bookings but flagged supply-chain and margin pressure, leaving the setup ambiguous.",
    },
    "IPO / listing momentum": {
        "confirmed": "{t} priced its IPO strongly with heavy oversubscription and traded up on debut, confirming demand for the listing.",
        "reported": "{t}'s listing is drawing reported strong interest, but pricing and aftermarket demand are not yet confirmed.",
        "early": "{t} is a recent listing riding sector momentum, but there is no specific catalyst beyond IPO-window enthusiasm.",
        "mixed": "{t} listed with strong initial demand but faces a looming lockup expiry and rich valuation, a two-sided setup.",
    },
    "Earnings / guidance momentum": {
        "confirmed": "{t} beat on both revenue and EPS AND raised full-year guidance, a clean company-specific earnings reset.",
        "reported": "{t} is expected to report strong results and buy-side positioning is bullish, but the print has not landed.",
        "early": "Read-through from peers is positive for {t}, but {t} itself has not reported and there is no direct catalyst.",
        "mixed": "{t} beat on earnings but left guidance unchanged and flagged a softening outlook, a mixed reaction setup.",
    },
    "M&A / corporate action": {
        "confirmed": "A credible financial outlet reported, with named parties, that {t} is the target of an acquisition; deal terms are specific.",
        "reported": "{t} is the subject of acquisition speculation from a credible source citing unnamed people; no official confirmation.",
        "early": "{t} is floated as a possible consolidation candidate in sector commentary, but there is no specific deal report.",
        "mixed": "A deal involving {t} was reported, but regulatory or financing hurdles were flagged, leaving completion uncertain.",
    },
}

STRENGTH_ORDER = ["confirmed", "reported", "early", "mixed"]


def _stable_strength(case_id: str) -> str:
    # Deterministic, outcome-independent difficulty from the id alone.
    h = sum(ord(c) for c in case_id)
    return STRENGTH_ORDER[h % len(STRENGTH_ORDER)]


def main() -> None:
    out = {}
    missing_theme = set()
    for case in CASES:
        theme = case["theme_driver"]
        if theme not in THEME_CATALYSTS:
            missing_theme.add(theme)
            continue
        strength = _stable_strength(case["id"])
        template = THEME_CATALYSTS[theme][strength]
        out[case["id"]] = {
            "strength": strength,
            "catalyst": template.format(t=case["ticker"]),
        }
    OUT.write_text(json.dumps(out, indent=2))
    # Report the difficulty distribution so we can confirm it's spread.
    from collections import Counter
    dist = Counter(v["strength"] for v in out.values())
    print(f"Wrote {len(out)} catalysts to {OUT}")
    print(f"Strength distribution: {dict(dist)}")
    if missing_theme:
        print(f"WARNING missing theme templates: {missing_theme}")


if __name__ == "__main__":
    main()
