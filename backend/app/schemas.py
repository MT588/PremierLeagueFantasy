from pydantic import BaseModel


class Meta(BaseModel):
    season: str
    next_gameweek: int | None
    model_version: str
    players_in_pool: int
    predictions: int


class TeamOut(BaseModel):
    code: int
    name: str
    short_name: str
    strength_overall_home: int | None = None
    strength_overall_away: int | None = None
    strength_attack_home: int | None = None
    strength_attack_away: int | None = None
    strength_defence_home: int | None = None
    strength_defence_away: int | None = None
    next_opponent: str | None = None
    next_fdr: int | None = None


class PlayerStats(BaseModel):
    """Wide per-player row backing the captaincy, attack, defence, price and
    full player tables. One fetch feeds all five."""

    code: int
    web_name: str
    full_name: str
    position: int
    team_code: int | None
    team_short: str | None
    price: float
    status: str | None
    chance_of_playing: int | None
    news: str | None

    predicted_points: float | None
    rating: str | None
    p_start: float | None

    # v3 distributional outputs. Null on rows a pre-v3 model_version wrote, so
    # the tables have to tolerate a missing column rather than assume zero.
    p_blank: float | None = None
    p_return: float | None = None
    p_haul: float | None = None
    p10: float | None = None
    p50: float | None = None
    p90: float | None = None
    upside: float | None = None

    # Season columns come from `stat_season` — the latest season with real rows,
    # which pre-season is last season.
    stat_season: str | None
    total_points: int
    minutes: int
    starts: int | None
    appearances: int
    ppg: float | None
    points_per_million: float | None
    starts_share: float | None

    form_points: int | None
    form_minutes: int | None
    xg90_form: float | None
    xa90_form: float | None
    xgi90_form: float | None
    dc90_form: float | None

    xg90_season: float | None
    xa90_season: float | None
    xgi90_season: float | None
    dc90_season: float | None

    team_xgc90_form: float | None
    team_xgc90_season: float | None

    selected_by_percent: float | None
    transfers_in_event: int | None
    transfers_out_event: int | None
    net_transfers: int

    next_opponent: str | None
    next_fdr: int | None

    recent_points: list[int]


class PlayerRow(BaseModel):
    code: int
    web_name: str
    full_name: str
    position: int
    team_code: int | None
    team_short: str | None
    price: float
    status: str | None
    chance_of_playing: int | None
    predicted_points: float | None
    rating: str | None
    p_start: float | None
    form: float | None  # avg points, last 5 appearances
    xgi90: float | None
    total_points_last_season: int | None
    recent_points: list[int]  # last 10 appearances, chronological


class FixtureOut(BaseModel):
    gameweek: int | None
    kickoff_time: str | None
    opponent_short: str | None
    was_home: bool
    difficulty: int | None


class GameweekPoint(BaseModel):
    season: str
    gameweek: int
    total_points: int
    minutes: int
    expected_goal_involvements: float | None
    value: float | None


class PredictionOut(BaseModel):
    gameweek: int
    predicted_points: float
    rating: str | None
    p_start: float | None = None
    drivers: dict | None = None

    # v3: the shape of the week, not just its mean. `components` is the
    # per-component points breakdown that replaced v2's SHAP attributions.
    p_blank: float | None = None
    p_return: float | None = None
    p_haul: float | None = None
    p10: float | None = None
    p50: float | None = None
    p90: float | None = None
    upside: float | None = None
    components: list[dict] | dict | None = None


class PlayerDetail(BaseModel):
    code: int
    web_name: str
    full_name: str
    position: int
    team_short: str | None
    price: float
    status: str | None
    chance_of_playing: int | None
    history: list[GameweekPoint]
    upcoming: list[FixtureOut]
    predictions: list[PredictionOut]


class SquadPlayer(BaseModel):
    code: int
    web_name: str
    position: int
    team_short: str | None
    price: float
    predicted_points: float
    is_captain: bool


class OptimalTeamOut(BaseModel):
    starting_xi: list[SquadPlayer]
    bench: list[SquadPlayer]
    total_cost: float
    expected_points: float
    budget: float
    horizon: int
    gameweeks: list[int]
    infeasible: bool
