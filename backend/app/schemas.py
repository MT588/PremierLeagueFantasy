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


class PlayerRow(BaseModel):
    code: int
    web_name: str
    full_name: str
    position: int
    team_code: int | None
    team_short: str | None
    price: float
    status: str | None
    predicted_points: float | None
    rating: str | None
    form: float | None                 # avg points, last 5 appearances
    xgi90: float | None
    total_points_last_season: int | None
    recent_points: list[int]           # last 10 appearances, chronological


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


class PlayerDetail(BaseModel):
    code: int
    web_name: str
    full_name: str
    position: int
    team_short: str | None
    price: float
    status: str | None
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
