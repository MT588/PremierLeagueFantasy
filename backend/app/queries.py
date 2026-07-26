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
select gameweek, predicted_points, rating, p_start, drivers from predictions
where season_id = :season_id and player_code = :code
  and model_version = :model_version
order by gameweek
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
