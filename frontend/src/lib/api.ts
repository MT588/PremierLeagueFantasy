const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface Meta {
  season: string;
  next_gameweek: number | null;
  model_version: string;
  players_in_pool: number;
  predictions: number;
}

export interface PlayerRow {
  code: number;
  web_name: string;
  full_name: string;
  position: number;
  team_code: number | null;
  team_short: string | null;
  price: number;
  status: string | null;
  chance_of_playing: number | null;
  predicted_points: number | null;
  rating: string | null;
  p_start: number | null;
  form: number | null;
  xgi90: number | null;
  total_points_last_season: number | null;
  recent_points: number[];
}

export interface FixtureOut {
  gameweek: number | null;
  kickoff_time: string | null;
  opponent_short: string | null;
  was_home: boolean;
  difficulty: number | null;
}

export interface GameweekPoint {
  season: string;
  gameweek: number;
  total_points: number;
  minutes: number;
  expected_goal_involvements: number | null;
  value: number | null;
}

export interface PredictionDriver {
  feature: string;
  label: string;
  value: number | null;
  contribution: number;
}

export interface PredictionDrivers {
  p_start: number;
  p_cameo: number;
  expected_if_start: number;
  gated?: boolean;
  top: PredictionDriver[];
}

export interface PlayerPrediction {
  gameweek: number;
  predicted_points: number;
  rating: string | null;
  p_start: number | null;
  drivers: PredictionDrivers | null;
}

export interface PlayerDetail {
  code: number;
  web_name: string;
  full_name: string;
  position: number;
  team_short: string | null;
  price: number;
  status: string | null;
  chance_of_playing: number | null;
  history: GameweekPoint[];
  upcoming: FixtureOut[];
  predictions: PlayerPrediction[];
}

export interface SquadPlayer {
  code: number;
  web_name: string;
  position: number;
  team_short: string | null;
  price: number;
  predicted_points: number;
  is_captain: boolean;
}

export interface OptimalTeam {
  starting_xi: SquadPlayer[];
  bench: SquadPlayer[];
  total_cost: number;
  expected_points: number;
  budget: number;
  horizon: number;
  gameweeks: number[];
  infeasible: boolean;
}

export interface TeamOut {
  code: number;
  name: string;
  short_name: string;
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${API}${path}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`${path} -> ${res.status}`);
  return res.json();
}

export const api = {
  meta: () => get<Meta>("/api/meta"),
  teams: () => get<TeamOut[]>("/api/teams"),
  players: (params: Record<string, string> = {}) =>
    get<PlayerRow[]>(`/api/players?${new URLSearchParams(params)}`),
  player: (code: number) => get<PlayerDetail>(`/api/players/${code}`),
  predictions: (params: Record<string, string> = {}) =>
    get<Record<string, unknown>[]>(`/api/predictions?${new URLSearchParams(params)}`),
  optimalTeam: (budget: number, horizon: number) =>
    get<OptimalTeam>(`/api/optimal-team?budget=${budget}&horizon=${horizon}`),
};
