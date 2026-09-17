"""
05_load_to_sql.py

Loads data/processed/player_games_classified.csv (the output of
02_classify_comfort.ipynb) into a normalized SQLite database at
data/processed/lol_analytics.db, following sql/schema.sql.

This is the SQL layer of the project: instead of one flat CSV, the data
lives in a small relational schema (leagues, teams, players, champions,
games, game_teams, player_game_stats). queries_showcase.sql -- and later
a Qlik/Tableau dashboard -- connect to this database, not to the CSV.

Usage (from the repo root):
    python sql/05_load_to_sql.py

Re-running is safe: the database file is rebuilt from scratch each time,
so this script is idempotent.
"""

import os
import sqlite3

import pandas as pd

CLASSIFIED_PATH = "data/processed/player_games_classified.csv"
SCHEMA_PATH = "sql/schema.sql"
DB_PATH = "data/processed/lol_analytics.db"


def build_dimension(df: pd.DataFrame, col: str, id_col: str) -> pd.DataFrame:
    """Unique values of `col` -> a small dimension table with a surrogate integer id."""
    values = df[col].dropna().unique()
    return pd.DataFrame({id_col: range(1, len(values) + 1), col: values})


def main():
    df = pd.read_csv(CLASSIFIED_PATH)
    df["playername"] = df["playername"].astype(str)
    df["side"] = df["side"].astype(str).str.strip().str.capitalize()

    # --- Dimension tables ---
    leagues = build_dimension(df, "league", "league_id").rename(columns={"league": "league_code"})
    teams = build_dimension(df, "teamname", "team_id").rename(columns={"teamname": "team_name"})
    players = build_dimension(df, "playername", "player_id").rename(columns={"playername": "player_name"})
    champions = build_dimension(df, "champion", "champion_id").rename(columns={"champion": "champion_name"})

    df = df.merge(leagues, left_on="league", right_on="league_code")
    df = df.merge(teams, left_on="teamname", right_on="team_name")
    df = df.merge(players, left_on="playername", right_on="player_name")
    df = df.merge(champions, left_on="champion", right_on="champion_name")

    # --- games (one row per gameid) ---
    agg_map = {
        "league_id": ("league_id", "first"),
        "year": ("year", "first"),
        "split": ("split", "first"),
        "game_date": ("date", "first"),
    }
    for src_col in ["patch", "playoffs"]:
        if src_col in df.columns:
            agg_map[src_col] = (src_col, "first")

    games = (
        df.sort_values("date")
        .groupby("gameid", as_index=False)
        .agg(**agg_map)
        .rename(columns={"gameid": "game_id"})
    )
    for col in ["patch", "playoffs"]:
        if col not in games.columns:
            games[col] = None

    # --- game_teams (one row per team per game) ---
    game_teams = (
        df[["gameid", "team_id", "side", "result"]]
        .drop_duplicates(subset=["gameid", "team_id"])
        .rename(columns={"gameid": "game_id"})
    )
    game_teams["result"] = game_teams["result"].astype(int)

    # --- player_game_stats (one row per player per game) ---
    stat_cols = ["kills", "deaths", "assists", "kda", "dpm", "cspm",
                 "damageshare", "earnedgoldshare", "golddiffat15",
                 "xpdiffat15", "csdiffat15"]
    present_stat_cols = [c for c in stat_cols if c in df.columns]

    pgs = df[
        ["gameid", "player_id", "team_id", "champion_id", "position", "side", "result", "is_comfort"]
        + present_stat_cols
    ].copy()
    pgs = pgs.rename(columns={"gameid": "game_id"})
    pgs["is_comfort"] = pgs["is_comfort"].astype(int)
    pgs["result"] = pgs["result"].astype(int)
    pgs.insert(0, "player_game_id", range(1, len(pgs) + 1))

    # --- Build the schema fresh, then load ---
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    conn = sqlite3.connect(DB_PATH)
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        conn.executescript(f.read())

    leagues[["league_id", "league_code"]].to_sql("leagues", conn, if_exists="append", index=False)
    teams[["team_id", "team_name"]].to_sql("teams", conn, if_exists="append", index=False)
    players[["player_id", "player_name"]].to_sql("players", conn, if_exists="append", index=False)
    champions[["champion_id", "champion_name"]].to_sql("champions", conn, if_exists="append", index=False)
    games[["game_id", "league_id", "patch", "year", "split", "playoffs", "game_date"]].to_sql(
        "games", conn, if_exists="append", index=False
    )
    game_teams[["game_id", "team_id", "side", "result"]].to_sql(
        "game_teams", conn, if_exists="append", index=False
    )
    pgs_cols = (
        ["player_game_id", "game_id", "player_id", "team_id", "champion_id",
         "position", "side", "result", "is_comfort"] + present_stat_cols
    )
    pgs[pgs_cols].to_sql("player_game_stats", conn, if_exists="append", index=False)
    conn.commit()

    print(f"Loaded into {DB_PATH}:")
    for table in ["leagues", "teams", "players", "champions", "games", "game_teams", "player_game_stats"]:
        n = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"  {table}: {n} rows")

    conn.close()


if __name__ == "__main__":
    main()
