-- queries_showcase.sql
--
-- A tour of SQL techniques applied to the same "comfort picks" question
-- explored statistically in 03_stats_analysis.ipynb -- but answered here
-- in pure SQL against the normalized schema, not pandas.
--
-- Run against data/processed/lol_analytics.db (built by 05_load_to_sql.py):
--     sqlite3 data/processed/lol_analytics.db
--     .read sql/queries_showcase.sql


-- ============================================================
-- 1. JOIN — a readable box score
-- ============================================================
-- Four dimension tables joined onto the fact table to turn surrogate IDs
-- back into names.
SELECT
    g.game_id, g.game_date, l.league_code,
    p.player_name, pgs.position, c.champion_name,
    pgs.kills, pgs.deaths, pgs.assists, pgs.kda
FROM player_game_stats pgs
JOIN games g     ON g.game_id = pgs.game_id
JOIN leagues l   ON l.league_id = g.league_id
JOIN players p   ON p.player_id = pgs.player_id
JOIN champions c ON c.champion_id = pgs.champion_id
ORDER BY g.game_date DESC
LIMIT 20;


-- ============================================================
-- 2. GROUP BY — average early-game gold lead by role
-- ============================================================
SELECT
    position,
    ROUND(AVG(golddiffat15), 1) AS avg_gd15,
    COUNT(*)                    AS n_games
FROM player_game_stats
GROUP BY position
ORDER BY avg_gd15 DESC;


-- ============================================================
-- 3. WINDOW FUNCTION — rolling 5-game KDA per player
-- ============================================================
-- A moving average over each player's own game history, ordered by date.
-- This is the kind of "form" metric a coach actually wants to see evolve
-- over a split, not just a single split-long average.
SELECT
    p.player_name,
    g.game_date,
    pgs.kda,
    ROUND(AVG(pgs.kda) OVER (
        PARTITION BY pgs.player_id
        ORDER BY g.game_date
        ROWS BETWEEN 4 PRECEDING AND CURRENT ROW
    ), 2) AS kda_rolling_5g
FROM player_game_stats pgs
JOIN games g   ON g.game_id = pgs.game_id
JOIN players p ON p.player_id = pgs.player_id
ORDER BY p.player_name, g.game_date;


-- ============================================================
-- 4. LAG() — game-over-game swing in early-game performance
-- ============================================================
-- Flags players whose GD@15 changed sharply from their immediately
-- previous game -- a cheap way to spot volatility or a tilt/momentum effect.
SELECT
    p.player_name,
    g.game_date,
    pgs.golddiffat15,
    pgs.golddiffat15 - LAG(pgs.golddiffat15) OVER (
        PARTITION BY pgs.player_id ORDER BY g.game_date
    ) AS gd15_change_vs_prev_game
FROM player_game_stats pgs
JOIN games g   ON g.game_id = pgs.game_id
JOIN players p ON p.player_id = pgs.player_id
ORDER BY p.player_name, g.game_date;


-- ============================================================
-- 5. CTE — comfort vs. no-comfort win rate per player, in pure SQL
-- ============================================================
-- The SQL-native counterpart to the paired comparison in Part 1 of
-- 03_stats_analysis.ipynb. Note this is a plain win-rate difference with
-- no FDR correction or significance test -- useful for a quick scan, but
-- the notebook's statistical version is the one to actually cite.
WITH player_split AS (
    SELECT
        p.player_name,
        pgs.is_comfort,
        COUNT(*)                AS n_games,
        AVG(pgs.result) * 100.0 AS win_rate_pct,
        AVG(pgs.golddiffat15)   AS avg_gd15
    FROM player_game_stats pgs
    JOIN players p ON p.player_id = pgs.player_id
    GROUP BY p.player_name, pgs.is_comfort
    HAVING COUNT(*) >= 2
)
SELECT
    comfort.player_name,
    comfort.n_games         AS n_comfort_games,
    comfort.win_rate_pct    AS comfort_win_rate,
    nocomfort.n_games       AS n_nocomfort_games,
    nocomfort.win_rate_pct  AS nocomfort_win_rate,
    ROUND(comfort.win_rate_pct - nocomfort.win_rate_pct, 1) AS win_rate_diff_pct
FROM player_split comfort
JOIN player_split nocomfort
    ON comfort.player_name = nocomfort.player_name
   AND comfort.is_comfort = 1
   AND nocomfort.is_comfort = 0
ORDER BY win_rate_diff_pct DESC;


-- ============================================================
-- 6. RANK() — top 5 players per role by average GD@15
-- ============================================================
SELECT *
FROM (
    SELECT
        pgs.position,
        p.player_name,
        ROUND(AVG(pgs.golddiffat15), 1) AS avg_gd15,
        COUNT(*)                        AS n_games,
        RANK() OVER (
            PARTITION BY pgs.position ORDER BY AVG(pgs.golddiffat15) DESC
        ) AS role_rank
    FROM player_game_stats pgs
    JOIN players p ON p.player_id = pgs.player_id
    GROUP BY pgs.position, p.player_name
    HAVING COUNT(*) >= 5
)
WHERE role_rank <= 5
ORDER BY position, role_rank;


-- ============================================================
-- 7. Indexing — does idx_pgs_player actually get used?
-- ============================================================
-- schema.sql creates two indexes covering player_id: idx_pgs_player and
-- the composite idx_pgs_player_comfort (whose leftmost column is also
-- player_id). This should report a "SEARCH player_game_stats USING
-- INDEX ..." line naming whichever of the two SQLite's planner prefers,
-- rather than "SCAN player_game_stats" (a full table scan) -- which one
-- it picks isn't the point, the SEARCH-vs-SCAN distinction is.
--
-- To see the difference for yourself: run `DROP INDEX idx_pgs_player;
-- DROP INDEX idx_pgs_player_comfort;`, re-run this EXPLAIN, confirm it
-- now says SCAN, then re-run `python sql/05_load_to_sql.py` to rebuild
-- the schema (and both indexes) from scratch.
EXPLAIN QUERY PLAN
SELECT * FROM player_game_stats WHERE player_id = 1;


-- ============================================================
-- 8. View — what a BI tool would connect to
-- ============================================================
-- player_comfort_summary is defined once in schema.sql, not recomputed
-- here. This is the kind of pre-aggregated object worth pointing
-- Qlik/Tableau at directly.
SELECT *
FROM player_comfort_summary
ORDER BY player_name, is_comfort;
