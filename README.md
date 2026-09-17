# lol-comfort-pick-analytics

# Comfort vs. Draft-Assigned: Evaluating Pick Priority in ERLs

**Question:** do professional League of Legends players perform measurably better on "comfort picks" (champions they play often) than on champions assigned to them by the draft/composition, once you control for role, side, and relative opponent strength?

Built as a portfolio project to demonstrate rigorous applied statistics for esports analytics — not just a mean comparison, but paired designs, mixed-effects models, multiple-comparison correction, and an explicit accounting of the design's causal limitations.

## Data

[Oracle's Elixir](https://oracleselixir.com/tools/downloads) professional match data, at player-game level.

**League scope:** Spanish Superliga (`LES` / `SL` / `Superliga` — Oracle's Elixir has used more than one label for this league across seasons), `LFL` (France), `PRM` (Prime League — Germany/Austria/Switzerland/Liechtenstein), `NLC` (Northern LoL Championship — UK/Ireland/Nordics), and `EM` (EMEA Masters, the cross-regional playoff tournament for the ERLs above; formerly branded "EU Masters"/"European Masters"). There is no separate "EUW Masters" code in Oracle's Elixir — `EM` is the correct current one. See `01_clean_data.py` for the exact filter and for two caveats worth checking after each fresh download: whether EMEA Masters rows populate `split` consistently with regular-season rows for the same players, and whether team names match exactly between a club's regular-season and EM rows (the Elo proxy in `03` keys off exact team-name strings).

## Pipeline

```
data/raw/*.csv                         (Oracle's Elixir exports)
  -> 01_clean_data.py                  -> data/processed/player_games_clean.csv
  -> 02_classify_comfort.ipynb         -> data/processed/player_games_classified.csv
  -> 03_stats_analysis.ipynb           -> data/processed/{paired_test_results, player_comfort_means_wide,
                                           lmm_summary, ols_robustness_check, comfort_effect_by_player,
                                           model_df_with_elo, selection_bias_logit_summary}.csv
  -> 04_visuals.ipynb                  -> assets/figures/*.{png,svg}
```

Each notebook exports its CSV output **immediately after computing it**, not all at once at the end — so a failure partway through a notebook still leaves behind whatever it already finished, instead of silently blocking everything downstream.

### 01. Cleaning (`01_clean_data.py`)

Loads raw CSVs, drops team-level rows, filters to the target leagues/years/completeness, rescales `damageshare`/`earnedgoldshare` from a 0-1 fraction to percentage points (once, here, so every downstream notebook sees the same units), and computes a basic KDA (`deaths = 0` treated as `deaths = 1`, so a 0-death game reports `kills + assists`, not an undefined ratio — worth knowing if you cite KDA numbers).

### 02. Comfort classification (`02_classify_comfort.ipynb`)

Operational definition, applied per `(playername, year, split)`:
- Minimum 8 games in the split to be included at all.
- `is_comfort = True` if the champion was played ≥ 4 times in the split.
- `is_comfort = False` if played ≤ 2 times.
- Exactly 3 games on a champion is treated as an ambiguous middle zone and dropped.

**This definition is retrospective, not prospective** — it looks at the whole split, not just games played "before" the one being labeled. A player's very first game on a champion they go on to play 4+ times is already labeled comfort. This is documented explicitly (rather than assumed away) inside the notebook, along with an optional, off-by-default prospective variant for comparison.

### 03. Statistical analysis (`03_stats_analysis.ipynb`)

- **Part 0:** a sequential team-level Elo rating built from the data itself, used as a relative-opponent-strength covariate (`elo_diff_z`) — Oracle's Elixir doesn't ship one directly.
- **Part 1:** player-level paired tests (Wilcoxon signed-rank, paired t-test, rank-biserial and Cohen's *dz* effect sizes) with Benjamini-Hochberg FDR correction across metrics.
- **Part 2:** Linear Mixed Models (random intercept by player) for GD@15, CSD@15, XPD@15, DPM, DMG% and KDA, controlling for role, side, and `elo_diff_z`; a random-slope extension quantifies how much the comfort effect varies by player (BLUP ranking); an OLS-with-player-clustered-SEs model runs alongside as a robustness check whenever the LMM's random-intercept variance looks unstable.
- **Part 3:** selection-bias / endogeneity discussion — comfort picks aren't randomly assigned, they're chosen *because* the staff expects them to work in that specific context — plus a logistic regression that empirically tests whether comfort assignment correlates with relative opponent strength.

### 04. Visualization (`04_visuals.ipynb`)

Five report-quality figures from the CSVs above: a forest plot of the (standardized) LMM comfort effect per metric, per-player paired comparisons, comfort-effect heterogeneity by role, a top/bottom player ranking, and a check of whether comfort-pick rate varies with opponent strength.

## Known limitations

- **Comfort picks are not randomly assigned** (Part 3 of `03`). The LMM's `is_comfort` coefficient should be read as an *adjusted association*, not a causal effect, until champion power on the current patch, draft order, and series stakes are also controlled for.
- **Comfort classification is retrospective** (see `02` above).
- **No matching / propensity weighting yet.** Listed as roadmap in Part 3.3 of `03`, not implemented.
- **LMM convergence can be data-dependent.** `check_lmm_health()` in `03` flags degenerate/boundary fits (`Group Var ≈ 0`) per metric; when that happens, the OLS-with-clustered-SEs companion table is the more trustworthy number for that metric. Always check the `converged` column in `lmm_summary.csv` before quoting a coefficient.
- **Sample size** depends entirely on how many leagues/seasons you download — the 5-ERL scope above is a starting point, not a hard ceiling.

## Reproducibility

- `requirements.txt` pins dependency ranges. Notably, this pipeline uses `statsmodels.MixedLM` with `groups=` set to a player-name column; a pyarrow-backed pandas string dtype passed into that argument is a known source of numerically unstable ("degenerate") fits, which is why every notebook casts `playername` to a plain Python `str` immediately after loading. If you hit `Group Var ≈ 0` across every metric simultaneously after modifying this pipeline, check that cast first.
- Every notebook is written to run cleanly with **Kernel → Restart & Run All** — there are no out-of-order or duplicated cells.

## Visual identity

Comfort picks: `#1B998B` (teal). No-comfort / assigned picks: `#E9724C` (burnt orange). Figures saved as PNG (300 dpi) and SVG to `assets/figures/`.

## Roadmap (not yet implemented)

- Control for champion strength on the current patch (global win rate/pick rate, or a crossed random effect by champion).
- Propensity-score matching or a difference-in-differences design exploiting patch nerfs/buffs, to move closer to a causal estimate.
- A Win Rate (binary outcome) model via GEE or a Bayesian mixed GLM.
- Draft-order data (blind pick vs. counter-pick) via Oracle's Elixir's pick columns or the Leaguepedia Cargo API.
- Solo queue mastery / historical win-rate features, if a suitable data source is added.

## Stack

Python, pandas, numpy, scipy, statsmodels (`MixedLM`, `OLS`, `Logit`), matplotlib, seaborn, Jupyter.
