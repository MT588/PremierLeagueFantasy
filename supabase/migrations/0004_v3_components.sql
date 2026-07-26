-- v3: per-component expected points and distributional predictions.
--
-- The three defensive counts behind the 2025-26 defensive-contribution rule are
-- served per gameweek by the official API (bootstrap-static.element_stats) and
-- by vaastav's merged_gw.csv from 2025-26 onward. Earlier seasons do not have
-- them at all -- the stat did not exist -- so they stay NULL there.
--
-- defensive_contribution itself is a RAW COUNT, not points: for defenders it is
-- tackles + clearances_blocks_interceptions, for midfielders and forwards it
-- also includes recoveries, and for keepers it is always 0. The points come
-- from crossing a positional threshold (see ml/scoring.py).

alter table player_gameweeks add column if not exists tackles smallint;
alter table player_gameweeks add column if not exists clearances_blocks_interceptions smallint;
alter table player_gameweeks add column if not exists recoveries smallint;

-- Tournament load beyond squad membership. minutes/starts/goals come from
-- Wikipedia match line-ups; last_match_date drives "how late did this player's
-- summer end" independently of how deep the run was. assists stay NULL: no free
-- source publishes tournament assists (see pipeline/ingest_international.py).
alter table international_load add column if not exists goals smallint;
alter table international_load add column if not exists assists smallint;
alter table international_load add column if not exists starts smallint;
alter table international_load add column if not exists last_match_date date;

-- Distributional predictions. predicted_points keeps its meaning and is now the
-- mean of the simulated distribution; the rest describe its shape.
alter table predictions add column if not exists p_blank numeric;   -- P(points <= 2)
alter table predictions add column if not exists p_return numeric;  -- P(points >= 5)
alter table predictions add column if not exists p_haul numeric;    -- P(points >= 10)
alter table predictions add column if not exists p10 numeric;
alter table predictions add column if not exists p50 numeric;
alter table predictions add column if not exists p90 numeric;
alter table predictions add column if not exists upside numeric;    -- EV + lambda * p_haul
alter table predictions add column if not exists components jsonb;  -- per-component EV split
