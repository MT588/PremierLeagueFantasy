-- v2 external data sources: Elo ratings, Understat xG, betting odds,
-- manager stints, international tournament load, European competition flags,
-- set-piece duties, and prediction explainability.

create table if not exists club_elo (
  team_code int not null references teams(code),
  elo numeric not null,
  valid_from date not null,
  valid_to date not null,
  primary key (team_code, valid_from)
);
create index if not exists idx_club_elo_lookup on club_elo (team_code, valid_from, valid_to);

create table if not exists understat_players (
  understat_id int primary key,
  player_code int references players(code),   -- null = known-unmatched
  understat_name text not null,
  match_method text not null,                 -- exact / exact-anyteam / fuzzy / override / unmatched
  confidence numeric,
  season_first_seen text,
  updated_at timestamptz not null default now()
);

create table if not exists understat_matches (
  understat_id int not null references understat_players(understat_id),
  understat_match_id int not null,
  match_date date not null,
  league text not null,                       -- EPL / La_liga / Bundesliga / Serie_A / Ligue_1 / RFPL
  season smallint not null,                   -- understat season start year
  home_team text,
  away_team text,
  is_home boolean,
  minutes smallint,
  goals smallint,
  assists smallint,
  shots smallint,
  key_passes smallint,
  xg numeric,
  xa numeric,
  npxg numeric,
  npg smallint,
  position text,
  primary key (understat_id, understat_match_id)
);
create index if not exists idx_ust_matches_date on understat_matches (understat_id, match_date);

create table if not exists match_odds (
  season_id smallint not null,
  fpl_fixture_id int not null,
  b365_home numeric,
  b365_draw numeric,
  b365_away numeric,
  avg_home numeric,
  avg_draw numeric,
  avg_away numeric,
  over25 numeric,
  under25 numeric,
  matched_via text not null,
  primary key (season_id, fpl_fixture_id),
  foreign key (season_id, fpl_fixture_id) references fixtures (season_id, fpl_fixture_id)
);

create table if not exists manager_stints (
  team_code int not null references teams(code),
  manager_name text not null,
  start_date date not null,
  end_date date,                              -- null = current
  is_caretaker boolean not null default false,
  source text,
  primary key (team_code, start_date)
);

create table if not exists international_load (
  player_code int not null references players(code),
  tournament text not null,                   -- WC / EURO / COPA
  year smallint not null,
  squad_flag boolean not null default true,
  minutes smallint,                           -- null when only squad-list proxy available
  matches smallint,
  team_progress smallint,                     -- 1=group .. 7=won the final
  source text not null,                       -- football-data.org / wikipedia-proxy
  primary key (player_code, tournament, year)
);

create table if not exists european_competitions (
  season_id smallint not null references seasons(id),
  team_code int not null references teams(code),
  competition text not null,                  -- UCL / UEL / UECL
  primary key (season_id, team_code)
);

alter table player_seasons add column if not exists penalties_order smallint;
alter table player_seasons add column if not exists corners_order smallint;
alter table player_seasons add column if not exists freekicks_order smallint;

alter table players add column if not exists birth_date date;

alter table predictions add column if not exists p_start numeric;
alter table predictions add column if not exists p_cameo numeric;
alter table predictions add column if not exists drivers jsonb;

alter table club_elo enable row level security;
alter table understat_players enable row level security;
alter table understat_matches enable row level security;
alter table match_odds enable row level security;
alter table manager_stints enable row level security;
alter table international_load enable row level security;
alter table european_competitions enable row level security;
