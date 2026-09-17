-- schema.sql
--
-- Normalized schema for the "Comfort vs. Draft-Assigned" project's SQL
-- layer. Built with SQLite in mind (zero setup, portable single-file .db,
-- designed for reproducible local analysis). To port to PostgreSQL
-- later (e.g. to connect external BI tools via Supabase/Neon), the only
-- changes needed are:
--   - `INTEGER PRIMARY KEY`      -> `SERIAL PRIMARY KEY` (or `IDENTITY`)
--   - `PRAGMA foreign_keys = ON` -> not needed (enforced by default)
--   - `CHECK (side IN (...))`    -> supported as-is
-- All joins, window functions, and CTEs run unchanged on standard SQL.
PRAGMA foreign_keys = ON;

DROP VIEW IF EXISTS player_comfort_summary;
DROP TABLE IF EXISTS player_game_stats;
DROP TABLE IF EXISTS game_teams;
DROP TABLE IF EXISTS games;
DROP TABLE IF EXISTS champions;
DROP TABLE IF EXISTS players;
DROP TABLE IF EXISTS teams;
DROP TABLE IF EXISTS leagues;

-- ============================================================
-- Dimension tables
-- ============================================================

CREATE TABLE leagues (
    league_id   INTEGER PRIMARY KEY,
    league_code TEXT NOT NULL UNIQUE          -- e.g. 'LES', 'LFL', 'EM'
);

CREATE TABLE teams (
    team_id   INTEGER PRIMARY KEY,
    team_name TEXT NOT NULL UNIQUE
);

CREATE TABLE players (
    player_id   INTEGER PRIMARY KEY,
    player_name TEXT NOT NULL UNIQUE
);

CREATE TABLE champions (
    champion_id   INTEGER PRIMARY KEY,
    champion_name TEXT NOT NULL UNIQUE
);

-- ============================================================
-- Fact tables
-- ============================================================

-- One row per game. Oracle's Elixir's own gameid is already a natural
-- unique key, so it's used directly as the primary key rather than
-- inventing a surrogate one.
CREATE TABLE games (
    game_id    TEXT PRIMARY KEY,
    league_id  INTEGER NOT NULL REFERENCES leagues(league_id),
    patch      TEXT,
    year       INTEGER,
    split      TEXT,
    playoffs   INTEGER,                        -- 0/1
    game_date  TEXT                             -- ISO date string
);
CREATE INDEX idx_games_league ON games(league_id);
CREATE INDEX idx_games_date   ON games(game_date);

-- Bridge table: which two teams played in a game, on which side, with
-- what result. (game_id, team_id) is the natural composite key.
CREATE TABLE game_teams (
    game_id TEXT    NOT NULL REFERENCES games(game_id),
    team_id INTEGER NOT NULL REFERENCES teams(team_id),
    side    TEXT    NOT NULL CHECK (side IN ('Blue', 'Red')),
    result  INTEGER NOT NULL CHECK (result IN (0, 1)),
    PRIMARY KEY (game_id, team_id)
);
CREATE INDEX idx_game_teams_team ON game_teams(team_id);

-- One row per player per game -- the fact table everything else joins to.
CREATE TABLE player_game_stats (
    player_game_id  INTEGER PRIMARY KEY,
    game_id         TEXT    NOT NULL REFERENCES games(game_id),
    player_id       INTEGER NOT NULL REFERENCES players(player_id),
    team_id         INTEGER NOT NULL REFERENCES teams(team_id),
    champion_id     INTEGER NOT NULL REFERENCES champions(champion_id),
    position        TEXT,
    side            TEXT,
    result          INTEGER,                    -- 1 = win, 0 = loss
    kills           INTEGER,
    deaths          INTEGER,
    assists         INTEGER,
    kda             REAL,
    dpm             REAL,
    cspm            REAL,
    damageshare     REAL,
    earnedgoldshare REAL,
    golddiffat15    REAL,
    xpdiffat15      REAL,
    csdiffat15      REAL,
    is_comfort      INTEGER                      -- 0/1, from 02_classify_comfort.ipynb
);
CREATE INDEX idx_pgs_player          ON player_game_stats(player_id);
CREATE INDEX idx_pgs_game            ON player_game_stats(game_id);
CREATE INDEX idx_pgs_champion        ON player_game_stats(champion_id);
CREATE INDEX idx_pgs_player_comfort  ON player_game_stats(player_id, is_comfort);

-- ============================================================
-- A view for BI tools
-- ============================================================
-- Mirrors the comfort-vs-no-comfort comparison from 03_stats_analysis.ipynb
-- (Part 1), expressed in SQL instead of pandas. This is exactly the kind
-- of pre-aggregated object worth pointing Qlik/Tableau at directly,
-- instead of making the BI tool re-aggregate raw rows on every filter change.
CREATE VIEW player_comfort_summary AS
SELECT
    p.player_name,
    pgs.is_comfort,
    COUNT(*)                  AS n_games,
    AVG(pgs.golddiffat15)     AS avg_gd15,
    AVG(pgs.csdiffat15)       AS avg_csd15,
    AVG(pgs.xpdiffat15)       AS avg_xpd15,
    AVG(pgs.dpm)              AS avg_dpm,
    AVG(pgs.damageshare)      AS avg_dmg_pct,
    AVG(pgs.kda)              AS avg_kda,
    AVG(pgs.result) * 100.0   AS win_rate_pct
FROM player_game_stats pgs
JOIN players p ON p.player_id = pgs.player_id
GROUP BY p.player_name, pgs.is_comfort;
