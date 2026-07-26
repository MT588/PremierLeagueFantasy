-- Fields the dashboard needs that were never ingested.
--
-- defensive_contribution / starts are per-gameweek stats: they live in
-- vaastav's merged_gw.csv (2022-23 onward) and in element-summary history.
-- The rest are live season-level snapshots from bootstrap-static.elements
-- and are only as fresh as the last `--live` pipeline run.

alter table player_gameweeks add column if not exists defensive_contribution smallint;
alter table player_gameweeks add column if not exists starts smallint;

alter table player_seasons add column if not exists selected_by_percent numeric;
alter table player_seasons add column if not exists transfers_in_event int;
alter table player_seasons add column if not exists transfers_out_event int;
alter table player_seasons add column if not exists news text;
