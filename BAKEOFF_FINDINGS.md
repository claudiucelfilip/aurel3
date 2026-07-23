# Interpreter Bake-off Findings

Date: 2026-07-23. Harness: `scripts/interpreter_bakeoff.py` (+ `scripts/build_bakeoff_catalysts.py`).

## Question

Is Thinking Machines' Inkling (token-billed, calibration-trained) worth adopting for
Aurel3's judgment step over the flat-rate subscription models (Fable 5 via `claude -p`,
gpt-5.6-sol via `codex exec`)? Bar set by Claudiu: Inkling must be **decisively** better
to justify per-token billing.

## Method

- 64 historical cases (`data/historical_replay_cases.json`) with known forward outcomes.
- Each case gets an authored catalyst description (`build_bakeoff_catalysts.py`) —
  written **blind to outcome**, with varied confirmation strength (confirmed / reported /
  early / mixed) assigned by stable hash so difficulty is outcome-independent.
- All models get identical prompts (the real `OPENCLAW_WORKER.md` system instruction),
  emit worker-schema JSON; `confidence` is scored against real forward returns
  (yfinance, engine's own `build_recommendation_review` grading).
- Two conditions: **thin** (catalyst text only) and **enriched** (`--enrich`: plus the
  ticker's real at-date market state — trend vs 20/50d EMA, day change, volume vs 60d
  average — computed with no lookahead).

## Results

Brier score (lower = better calibrated); high-conf hit rate = fraction of the model's
`high`-confidence calls that resolved positively.

| Model | Brier thin | Brier enriched | High-conf hit thin → enriched |
|---|---|---|---|
| Inkling | 0.370 | **0.329** | 0.43 → **0.62** |
| Fable 5 | 0.384 | 0.354 | 0.39 → 0.54 |
| gpt-5.6-sol | 0.406 | 0.386 | 0.14 → 0.43 |

Raw rows: `data/interpreter_bakeoff_results_thin_gpt56.json` and
`data/interpreter_bakeoff_results_enriched.json` (gitignored, local).

## Findings

1. **On catalyst text alone, every model is anti-calibrated.** `low`-confidence calls
   resolved positively 68–77% of the time; `high`-confidence calls only 14–43%. The
   forward move isn't predictable from the catalyst description — was-it-priced-in,
   crowding, and tape reaction live outside the text.
2. **Adding at-date market context fixed calibration for every model.** All Briers
   dropped; high-confidence hit rates rose across the board. The input, not the model,
   was the bottleneck.
3. **Inkling is consistently the best-calibrated and exploits market context best**
   (largest Brier drop, 0.62 high-conf hit rate). But its edge over flat-rate Fable is
   ~7% — real, repeatable, and **not decisive**.
4. gpt-5.6-sol calibrated worst in both conditions despite being the newest model —
   more evidence that model quality is not the constraint here.

## Decisions

- **Do not adopt Inkling.** Best of the three, but not by the decisive margin required
  to move the judgment layer onto per-token billing. Stay flat-rate.
- **Do feed the interpreter market-confirmation context.** This is the high-leverage,
  free change: the interpreter prompt should always include the candidate's at-date
  trend / volume / relative-strength, not just the news text. Aurel3 already computes
  this in `market.py` / `confirmation.py` — the fix is making sure it reaches the LLM
  prompt, not building new data.
- **Fine-tuning (Tinker LoRA) parked.** 64 cases would overfit; the enriched result
  shows the win is in inputs, not weights. Revisit only with hundreds of resolved live
  cases and enriched inputs — and the paid-deployment bar still applies.

## Caveats

- Catalysts are authored, not archived headlines — fair across models, but a decisive
  winner should be confirmed on real news before acting on model choice.
- Inkling dropped some cases per run (45–56/64 completed vs 63 for the CLI models) —
  operational fragility of the hosted endpoint is itself a mark against paid adoption.
- Single horizon-grading pass per case; no error bars. Treat ~7% Brier gaps as
  directional, not precise.

## Reuse

The harness is model-agnostic: add a backend to `BACKENDS` in
`scripts/interpreter_bakeoff.py` (flat-rate CLIs preferred; token-billed backends must
be gated like `inkling` behind `--allow-tinker-billing`). Regenerate catalysts with
`build_bakeoff_catalysts.py`; run thin + `--enrich` and compare the delta.
