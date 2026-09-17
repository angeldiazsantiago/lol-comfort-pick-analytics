"""
01_clean_data.py

Loads Oracle's Elixir match CSVs (oracleselixir.com/tools/downloads) and
produces a player-game level dataset structured for the "comfort picks" vs.
"draft-assigned picks" statistical analysis.

Usage:
    1. Place Oracle's Elixir season CSV export(s) in ./data/raw/
       (multiple files are concatenated automatically).
    2. Run: python 01_clean_data.py
    3. Output: data/processed/player_games_clean.csv

Schema Notes (Oracle's Elixir):
    - Each match (gameid) contains 12 rows (10 player rows + 2 team rows).
      Team rows (position == "team") are filtered out.
    - Rows are filtered to 'datacompleteness' == 'complete' to exclude
      partially tracked games.
    - Dynamic column selection: only existing columns are loaded to ensure
      cross-season schema compatibility.

League Scope:
    - LES / SL / Superliga: Spanish Superliga. All historical aliases are
      handled defensively to maintain cross-season stability.
    - LFL: Ligue Française de League of Legends (France).
    - PRM: Prime League (DACH region).
    - NLC: Northern LoL Championship (UK, Ireland, Nordics).
    - EM: EMEA Masters (pan-European tournament, formerly European Masters).
      Included to capture tournament/playoff match volume. Handled with two
      dataset considerations:
        1. 'split' naming alignment with regular ERL seasons for consistent
           grouping by (playername, year, split).
        2. Team entity naming alignment across domestic and EM events to
           preserve continuous Elo rating tracking in 03_stats_analysis.ipynb.
"""
import glob
import os

import pandas as pd

RAW_DIR = "data/raw"
OUT_DIR = "data/processed"
OUT_PATH = os.path.join(OUT_DIR, "player_games_clean.csv")

# Columns we care about.
# Run `df.columns.tolist()` on your real download -- the printout further
# down tells you exactly which of these it found.
WANTED_COLUMNS = [
    "gameid", "datacompleteness", "league", "split", "year", "patch",
    "playoffs", "date", "game", "side", "position", "playername", "playerid",
    "teamname", "teamid", "champion", "gamelength", "result",
    "kills", "deaths", "assists",
    "dpm", "cspm", "wpm",
    "damageshare", "earnedgoldshare",
    "golddiffat15", "xpdiffat15", "csdiffat15",
]

RENAME_MAP = {
    "player": "playername",
    "pos": "position",
    "team": "teamname",
}

# Leagues in scope for this project. See the module docstring above for the
# rationale behind each code, including why "EM" (EMEA Masters) is included
# and why there is no separate "EUW Masters" code to add.
TARGET_LEAGUES = ["LES", "SL", "Superliga", "LFL", "NLC", "PRM", "EM"]

# Year(s) of interest.
TARGET_YEARS = [2024, 2025, 2026]

# Columns that come out of Oracle's Elixir as 0-1 fractions but that we
# want as percentage points (0-100) everywhere downstream, so that every
# notebook in the pipeline (02, 03, 04) sees the same units and we never
# again have to silently re-scale mid-pipeline.
PERCENT_COLUMNS = ["damageshare", "earnedgoldshare"]


def load_raw(raw_dir: str) -> pd.DataFrame:
    paths = sorted(glob.glob(os.path.join(raw_dir, "*.csv")))
    if not paths:
        raise FileNotFoundError(
            f"No .csv files found in {raw_dir}/. "
            "Download data from oracleselixir.com/tools/downloads first."
        )
    frames = []
    for p in paths:
        print(f"Loading {p} ...")
        frames.append(pd.read_csv(p, low_memory=False))
    df = pd.concat(frames, ignore_index=True)
    print(f"Total rows loaded: {len(df)}")
    return df


def clean(df: pd.DataFrame) -> pd.DataFrame:
    # 1. Standardize column names
    df = df.rename(columns=RENAME_MAP)

    # 2. Drop team rows (each game has 2 team-level rows we don't need here)
    if "position" in df.columns:
        before = len(df)
        df = df[df["position"].fillna("").str.lower() != "team"].copy()
        print(f"Dropped team rows: {before} -> {len(df)} rows")

    # 3. Filter by league
    if "league" in df.columns:
        before = len(df)
        print(f"Leagues present before filtering: {sorted(df['league'].dropna().unique().tolist())}")
        df = df[df["league"].isin(TARGET_LEAGUES)].copy()
        print(f"Filtered by league ({TARGET_LEAGUES}): {before} -> {len(df)} rows")
        if "split" in df.columns and "EM" in TARGET_LEAGUES:
            em_splits = sorted(df.loc[df["league"] == "EM", "split"].dropna().unique().tolist())
            print(f"⚠️ Check this: unique 'split' values for EM (EMEA Masters) rows: {em_splits}")
            print("   Make sure these line up sensibly with the regular-season splits for the")
            print("   same players before trusting the (playername, year, split) groupings in 02/03.")

    # 4. Filter by year(s) of interest
    if "year" in df.columns:
        before = len(df)
        df = df[df["year"].isin(TARGET_YEARS)].copy()
        print(f"Filtered by year ({TARGET_YEARS}): {before} -> {len(df)} rows")

    # 5. Keep only complete records
    if "datacompleteness" in df.columns:
        before = len(df)
        df = df[df["datacompleteness"] == "complete"].copy()
        print(f"Filtered by datacompleteness: {before} -> {len(df)} rows")

    # 6. Keep only the columns that actually exist
    present = [c for c in WANTED_COLUMNS if c in df.columns]
    missing = [c for c in WANTED_COLUMNS if c not in df.columns]
    if missing:
        print(f"\nNote: these columns are not in your CSV and will be ignored: {missing}")
    df = df[present].copy()

    # 7. Rescale 0-1 fraction columns to percentage points, once, here.
    #    This used to be duplicated (inconsistently) inside 03_stats_analysis.ipynb,
    #    which caused player_comfort_means_wide.csv (fraction) and lmm_summary.csv
    #    (percentage) to disagree on DMG%'s units. Doing it here means every
    #    downstream notebook sees the same units by construction.
    for col in PERCENT_COLUMNS:
        if col in df.columns and df[col].max() <= 1.0:
            df[col] = df[col] * 100.0
            print(f"Rescaled '{col}' from a 0-1 fraction to percentage points (0-100).")

    # 8. Basic KDA, useful even if dpm/cspm are missing from your download.
    #    Deaths of 0 are treated as 1 to avoid division by zero -- this means
    #    a 0-death game is NOT reported as an infinite KDA, it's reported as
    #    exactly (kills + assists). Document this if you cite KDA numbers.
    if {"kills", "deaths", "assists"}.issubset(df.columns):
        df["kda"] = (df["kills"] + df["assists"]) / df["deaths"].replace(0, 1)

    # 9. Drop rows with no identified player or champion, and de-duplicate
    #    on (gameid, playername) in case of accidental double-counting.
    key_cols = [c for c in ["playername", "champion"] if c in df.columns]
    df = df.dropna(subset=key_cols)
    df = df.drop_duplicates(subset=["gameid", "playername"])
    return df


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    df = load_raw(RAW_DIR)
    df_clean = clean(df)
    df_clean.to_csv(OUT_PATH, index=False)
    print(f"\nDone. {len(df_clean)} player-game rows saved to {OUT_PATH}")


if __name__ == "__main__":
    main()
