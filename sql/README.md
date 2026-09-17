# SQL layer

The statistical analysis in `03_stats_analysis.ipynb` works from a single flat CSV. This layer takes the same underlying data and models it as a small relational database instead — the way it would actually live in an analytics team's stack, and the thing a BI tool (Qlik/Tableau) would connect to rather than a notebook.

## Schema

```
leagues            (league_id, league_code)
teams              (team_id, team_name)
players            (player_id, player_name)
champions          (champion_id, champion_name)
games              (game_id, league_id, patch, year, split, playoffs, game_date)
game_teams         (game_id, team_id, side, result)
player_game_stats  (player_game_id, game_id, player_id, team_id, champion_id,
                     position, side, result, kills, deaths, assists, kda, dpm,
                     cspm, damageshare, earnedgoldshare, golddiffat15,
                     xpdiffat15, csdiffat15, is_comfort)
```

Four dimension tables (`leagues`, `teams`, `players`, `champions`) plus three fact/bridge tables (`games`, `game_teams`, `player_game_stats`), with foreign keys and indexes — see `schema.sql` for the full DDL, including a `player_comfort_summary` view meant to be queried directly by a BI tool.

Built for SQLite (zero setup, single portable `.db` file). `schema.sql` notes the handful of changes needed to port it to PostgreSQL later, if you want a live server for Qlik/Tableau to connect to (e.g. a free Supabase or Neon.tech instance) instead of a static file.

## How to run it

```bash
# 1. Run the existing pipeline first (01 -> 02), if you haven't already,
#    so data/processed/player_games_classified.csv exists.

# 2. Build the database from it:
python sql/05_load_to_sql.py
# -> writes data/processed/lol_analytics.db

# 3. Explore it:
sqlite3 data/processed/lol_analytics.db
sqlite> .read sql/queries_showcase.sql
```

No `sqlite3` CLI? Any SQLite GUI (DB Browser for SQLite, DBeaver, the SQLite extension in VS Code) opens the same `.db` file directly — or just run the queries through Python's built-in `sqlite3` module.

## What `queries_showcase.sql` demonstrates

| # | Query | Technique |
|---|---|---|
| 1 | Box score for recent games | Multi-table `JOIN` |
| 2 | Average GD@15 by role | `GROUP BY` + aggregate |
| 3 | Rolling 5-game KDA per player | Window function (`AVG() OVER`, `ROWS BETWEEN`) |
| 4 | Game-over-game GD@15 swing | Window function (`LAG()`) |
| 5 | Comfort vs. no-comfort win rate per player | `CTE` (`WITH`) + self-join |
| 6 | Top 5 players per role by GD@15 | Window function (`RANK()`) + subquery |
| 7 | Does the index actually get used? | `EXPLAIN QUERY PLAN`, `SEARCH` vs. `SCAN` |
| 8 | Pre-aggregated comfort summary | `VIEW` (the thing a BI tool would query) |

Query 5 provides an uncorrected baseline comparison for rapid SQL-only exploration.
This reflects a core design separation: SQL is used to model, aggregate, and serve
data efficiently, while rigorous hypothesis testing, mixed-effects models, and FDR
corrections remain in the Python statistical pipeline (`03_stats_analysis.ipynb`).

## Next: Qlik / Tableau

`player_comfort_summary` (defined in `schema.sql`) and the fact table `player_game_stats` are the two objects meant to be pointed at directly from a BI tool for an interactive comfort-picks dashboard — the next layer on top of this one.
