"""SQL used by the API routers."""

CURRENT_SEASON = "select id, name from seasons where is_current limit 1"

NEXT_GAMEWEEK = """
select min(gameweek) from fixtures
where season_id = :season_id and not finished and gameweek is not null
"""

PLAYERS_LIST = """
with recent as (
  select player_code,
         avg(total_points) filter (where rn <= 5) as form,
         sum(expected_goal_involvements) filter (where rn <= 5) as xgi5,
         sum(minutes) filter (where rn <= 5) as mins5,
         array_agg(total_points order by rn desc) as recent_points
  from (
    select player_code, total_points, minutes, expected_goal_involvements,
           row_number() over (partition by player_code
                              order by season_id desc, gameweek desc, fpl_fixture_id desc) as rn
    from player_gameweeks
  ) x
  where rn <= 10
  group by player_code
),
last_season as (
  select g.player_code, sum(g.total_points) as pts
  from player_gameweeks g
  where g.season_id = (
    select id from seasons where not is_current order by start_year desc limit 1
  )
  group by g.player_code
)
select ps.player_code as code, p.web_name,
       p.first_name || ' ' || p.second_name as full_name,
       ps.position, ps.team_code, t.short_name as team_short,
       ps.now_cost / 10.0 as price, ps.status, ps.chance_of_playing,
       pr.predicted_points, pr.rating, pr.p_start,
       round(r.form::numeric, 2) as form,
       round((r.xgi5 / greatest(r.mins5, 1) * 90)::numeric, 2) as xgi90,
       ls.pts as total_points_last_season,
       coalesce(r.recent_points, '{}') as recent_points
from player_seasons ps
join players p on p.code = ps.player_code
left join teams t on t.code = ps.team_code
left join recent r on r.player_code = ps.player_code
left join last_season ls on ls.player_code = ps.player_code
left join predictions pr on pr.season_id = ps.season_id
       and pr.player_code = ps.player_code and pr.gameweek = :gameweek
       and pr.model_version = :model_version
where ps.season_id = :season_id and ps.position between 1 and 4
"""

PLAYER_HISTORY = """
select s.name as season, g.gameweek, g.total_points, g.minutes,
       g.expected_goal_involvements, g.value / 10.0 as value
from player_gameweeks g
join seasons s on s.id = g.season_id
where g.player_code = :code
order by s.start_year, g.gameweek, g.fpl_fixture_id
"""

PLAYER_UPCOMING = """
select f.gameweek, f.kickoff_time,
       case when f.home_team_code = :team_code then ta.short_name else th.short_name end as opponent_short,
       f.home_team_code = :team_code as was_home,
       case when f.home_team_code = :team_code then f.home_difficulty else f.away_difficulty end as difficulty
from fixtures f
left join teams th on th.code = f.home_team_code
left join teams ta on ta.code = f.away_team_code
where f.season_id = :season_id and not f.finished
  and (f.home_team_code = :team_code or f.away_team_code = :team_code)
order by f.gameweek nulls last, f.kickoff_time
limit 6
"""

PLAYER_PREDICTIONS = """
select gameweek, predicted_points, rating, p_start, drivers,
       p_blank, p_return, p_haul, p10, p50, p90, upside, components
from predictions
where season_id = :season_id and player_code = :code
  and model_version = :model_version
order by gameweek
"""

# One wide row per current-pool player, enough to drive the captaincy, attack,
# defence, price-movement and full player tables from a single fetch.
#
# The "season" columns come from the most recent season that player actually has
# rows for. Before a season kicks off that is automatically last season, which is
# the fallback the dashboard needs without hard-coding a prior.
#
# Every per-90 rate is null below a minimum sample — one full match for the
# 5-appearance form window, three for the season. Without that a player with a
# single minute and one defensive action reads as 90 DefCon/90 and sorts to the
# top of the table. Null rather than zero, so these rows sort last instead of
# masquerading as genuinely poor returns.
PLAYER_STATS = """
with ranked as (
  select player_code, season_id, total_points, minutes, starts,
         expected_goals, expected_assists, expected_goals_conceded,
         defensive_contribution,
         row_number() over (partition by player_code
                            order by season_id desc, gameweek desc, fpl_fixture_id desc) as rn
  from player_gameweeks
),
form as (
  select player_code,
         sum(total_points) as f_points,
         sum(minutes) as f_minutes,
         sum(expected_goals) as f_xg,
         sum(expected_assists) as f_xa,
         sum(expected_goals_conceded) as f_xgc,
         sum(defensive_contribution) as f_dc
  from ranked where rn <= 5 group by player_code
),
recent as (
  select player_code, array_agg(total_points order by rn desc) as recent_points
  from ranked where rn <= 10 group by player_code
),
season_pick as (
  select player_code, max(season_id) as sid from player_gameweeks group by player_code
),
season_agg as (
  select g.player_code, s.name as stat_season,
         sum(g.total_points) as s_points,
         sum(g.minutes) as s_minutes,
         sum(g.starts) as s_starts,
         count(*) as s_games,
         count(*) filter (where g.minutes > 0) as s_apps,
         sum(g.expected_goals) as s_xg,
         sum(g.expected_assists) as s_xa,
         sum(g.expected_goals_conceded) as s_xgc,
         sum(g.defensive_contribution) as s_dc
  from player_gameweeks g
  join season_pick sp on sp.player_code = g.player_code and sp.sid = g.season_id
  join seasons s on s.id = g.season_id
  group by g.player_code, s.name
),
-- A club's expected goals conceded per match, taken from its most-used keeper:
-- he is on the pitch for 90 minutes, so his xGC/90 is the team's xGC per match.
first_choice_gk as (
  select distinct on (ps.team_code) ps.team_code, ps.player_code
  from player_seasons ps
  join season_agg sa on sa.player_code = ps.player_code
  where ps.season_id = :season_id and ps.position = 1
  order by ps.team_code, sa.s_minutes desc nulls last
),
team_xgc as (
  select gk.team_code,
         case when sa.s_minutes >= 270
              then round((sa.s_xgc / sa.s_minutes * 90)::numeric, 3) end as xgc90_season,
         case when f.f_minutes >= 90
              then round((f.f_xgc / f.f_minutes * 90)::numeric, 3) end as xgc90_form
  from first_choice_gk gk
  join season_agg sa on sa.player_code = gk.player_code
  left join form f on f.player_code = gk.player_code
),
next_fix as (
  select tc.code as team_code,
         string_agg(case when f.home_team_code = tc.code
                         then ta.short_name || ' (H)' else th.short_name || ' (A)' end,
                    ', ' order by f.kickoff_time) as next_opponent,
         round(avg(case when f.home_team_code = tc.code
                        then f.home_difficulty else f.away_difficulty end))::int as next_fdr
  from teams tc
  join fixtures f on f.season_id = :season_id and f.gameweek = :gameweek
                 and (f.home_team_code = tc.code or f.away_team_code = tc.code)
  left join teams th on th.code = f.home_team_code
  left join teams ta on ta.code = f.away_team_code
  group by tc.code
)
select ps.player_code as code, p.web_name,
       p.first_name || ' ' || p.second_name as full_name,
       ps.position, ps.team_code, t.short_name as team_short,
       ps.now_cost / 10.0 as price, ps.status, ps.chance_of_playing, ps.news,
       pr.predicted_points, pr.rating, pr.p_start,
       -- v3 distributional outputs; null for rows written by v1/v2
       pr.p_blank, pr.p_return, pr.p_haul, pr.p10, pr.p50, pr.p90, pr.upside,
       sa.stat_season,
       coalesce(sa.s_points, 0) as total_points,
       coalesce(sa.s_minutes, 0) as minutes,
       sa.s_starts as starts,
       coalesce(sa.s_apps, 0) as appearances,
       case when sa.s_apps > 0
            then round((sa.s_points::numeric / sa.s_apps), 2) end as ppg,
       case when ps.now_cost > 0
            then round((coalesce(sa.s_points, 0) / (ps.now_cost / 10.0))::numeric, 1) end
            as points_per_million,
       case when sa.s_games > 0
            then round((sa.s_starts::numeric / sa.s_games), 3) end as starts_share,
       f.f_points as form_points,
       f.f_minutes as form_minutes,
       case when f.f_minutes >= 90
            then round((f.f_xg / f.f_minutes * 90)::numeric, 3) end as xg90_form,
       case when f.f_minutes >= 90
            then round((f.f_xa / f.f_minutes * 90)::numeric, 3) end as xa90_form,
       case when f.f_minutes >= 90
            then round(((f.f_xg + f.f_xa) / f.f_minutes * 90)::numeric, 3) end as xgi90_form,
       -- defensive_contribution is a smallint, so its sum is a bigint: cast
       -- before dividing or integer division floors every rate to zero.
       case when f.f_minutes >= 90
            then round((f.f_dc::numeric / f.f_minutes * 90), 2) end as dc90_form,
       case when sa.s_minutes >= 270
            then round((sa.s_xg / sa.s_minutes * 90)::numeric, 3) end as xg90_season,
       case when sa.s_minutes >= 270
            then round((sa.s_xa / sa.s_minutes * 90)::numeric, 3) end as xa90_season,
       case when sa.s_minutes >= 270
            then round(((sa.s_xg + sa.s_xa) / sa.s_minutes * 90)::numeric, 3) end as xgi90_season,
       case when sa.s_minutes >= 270
            then round((sa.s_dc::numeric / sa.s_minutes * 90), 2) end as dc90_season,
       tx.xgc90_form as team_xgc90_form,
       tx.xgc90_season as team_xgc90_season,
       ps.selected_by_percent,
       ps.transfers_in_event, ps.transfers_out_event,
       coalesce(ps.transfers_in_event, 0) - coalesce(ps.transfers_out_event, 0)
            as net_transfers,
       nf.next_opponent, nf.next_fdr,
       coalesce(r.recent_points, '{}') as recent_points
from player_seasons ps
join players p on p.code = ps.player_code
left join teams t on t.code = ps.team_code
left join form f on f.player_code = ps.player_code
left join recent r on r.player_code = ps.player_code
left join season_agg sa on sa.player_code = ps.player_code
left join team_xgc tx on tx.team_code = ps.team_code
left join next_fix nf on nf.team_code = ps.team_code
left join predictions pr on pr.season_id = ps.season_id
       and pr.player_code = ps.player_code and pr.gameweek = :gameweek
       and pr.model_version = :model_version
where ps.season_id = :season_id and ps.position between 1 and 4
"""

TEAMS_LIST = """
select t.code, t.name, t.short_name,
       ts.strength_overall_home, ts.strength_overall_away,
       ts.strength_attack_home, ts.strength_attack_away,
       ts.strength_defence_home, ts.strength_defence_away,
       nf.next_opponent, nf.next_fdr
from team_seasons ts
join teams t on t.code = ts.team_code
left join lateral (
  select string_agg(case when f.home_team_code = ts.team_code
                         then ta.short_name || ' (H)' else th.short_name || ' (A)' end,
                    ', ' order by f.kickoff_time) as next_opponent,
         round(avg(case when f.home_team_code = ts.team_code
                        then f.home_difficulty else f.away_difficulty end))::int as next_fdr
  from fixtures f
  left join teams th on th.code = f.home_team_code
  left join teams ta on ta.code = f.away_team_code
  where f.season_id = ts.season_id and f.gameweek = :gameweek
    and (f.home_team_code = ts.team_code or f.away_team_code = ts.team_code)
) nf on true
where ts.season_id = :season_id
order by t.name
"""

OPTIMIZER_CANDIDATES = """
select ps.player_code, ps.position, ps.team_code, ps.now_cost as cost,
       p.web_name, t.short_name as team_short,
       coalesce(sum(pr.predicted_points), 0) as predicted_points
from player_seasons ps
join players p on p.code = ps.player_code
left join teams t on t.code = ps.team_code
join predictions pr on pr.season_id = ps.season_id and pr.player_code = ps.player_code
where ps.season_id = :season_id and pr.gameweek = any(:gameweeks)
  and pr.model_version = :model_version
  and ps.status = 'a' and ps.team_code is not null
group by ps.player_code, ps.position, ps.team_code, ps.now_cost, p.web_name, t.short_name
"""
