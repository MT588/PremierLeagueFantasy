/** Where the FastAPI service lives. On Vercel the API is served from the same
 *  domain as the frontend, so the browser can use relative URLs and no CORS is
 *  involved; api.client.ts and api.server.ts each pass what they need. */

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
  strength_overall_home: number | null;
  strength_overall_away: number | null;
  strength_attack_home: number | null;
  strength_attack_away: number | null;
  strength_defence_home: number | null;
  strength_defence_away: number | null;
  next_opponent: string | null;
  next_fdr: number | null;
}

/** Wide per-player row backing the captaincy, attack, defence, price and full
 *  player tables. Fetched once, filtered client-side per view. */
export interface PlayerStats {
  code: number;
  web_name: string;
  full_name: string;
  position: number;
  team_code: number | null;
  team_short: string | null;
  price: number;
  status: string | null;
  chance_of_playing: number | null;
  news: string | null;

  predicted_points: number | null;
  rating: string | null;
  p_start: number | null;

  /** Which season the season-scoped columns below come from. Before a season
   *  kicks off this is last season. */
  stat_season: string | null;
  total_points: number;
  minutes: number;
  starts: number | null;
  appearances: number;
  ppg: number | null;
  points_per_million: number | null;
  starts_share: number | null;

  form_points: number | null;
  form_minutes: number | null;
  xg90_form: number | null;
  xa90_form: number | null;
  xgi90_form: number | null;
  dc90_form: number | null;

  xg90_season: number | null;
  xa90_season: number | null;
  xgi90_season: number | null;
  dc90_season: number | null;

  team_xgc90_form: number | null;
  team_xgc90_season: number | null;

  selected_by_percent: number | null;
  transfers_in_event: number | null;
  transfers_out_event: number | null;
  net_transfers: number;

  next_opponent: string | null;
  next_fdr: number | null;

  recent_points: number[];
}

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly path: string,
  ) {
    super(`${path} -> ${status}`);
    this.name = "ApiError";
  }
}

/** Resolves the caller's Supabase access token. `forceRefresh` is set on the
 *  retry after a 401, to distinguish an expired token from a real rejection. */
type GetToken = (opts: { forceRefresh: boolean }) => Promise<string | null>;

/** The API requires a Supabase JWT on every route, and the token is reachable
 *  in different ways on the server (cookies) than in the browser (session
 *  storage). Both entry points build a client from this factory: see
 *  api.server.ts and api.client.ts. */
export function createApi(
  getToken: GetToken,
  onUnauthorized: () => void,
  baseUrl: string,
) {
  async function get<T>(path: string, retried = false): Promise<T> {
    const token = await getToken({ forceRefresh: retried });
    const res = await fetch(`${baseUrl}${path}`, {
      cache: "no-store",
      headers: token ? { Authorization: `Bearer ${token}` } : undefined,
    });

    if (res.status === 401) {
      // A token that expired mid-session refreshes and succeeds on retry;
      // anything else means the session is genuinely gone.
      if (!retried) return get<T>(path, true);
      onUnauthorized();
      throw new ApiError(401, path);
    }
    if (!res.ok) throw new ApiError(res.status, path);

    // A 200 that isn't JSON means the request never reached FastAPI — an
    // interstitial redirected us somewhere and fetch followed it. Say so,
    // rather than letting res.json() fail with "Unexpected token '<'".
    const type = res.headers.get("content-type") ?? "";
    if (!type.includes("json")) {
      throw new Error(
        `${path} returned ${type || "no content-type"} from ${res.url} ` +
          `instead of JSON — check the API base URL is publicly reachable`,
      );
    }
    return res.json();
  }

  return {
    meta: () => get<Meta>("/api/meta"),
    teams: () => get<TeamOut[]>("/api/teams"),
    players: (params: Record<string, string> = {}) =>
      get<PlayerRow[]>(`/api/players?${new URLSearchParams(params)}`),
    player: (code: number) => get<PlayerDetail>(`/api/players/${code}`),
    playerStats: () => get<PlayerStats[]>("/api/player-stats"),
    predictions: (params: Record<string, string> = {}) =>
      get<Record<string, unknown>[]>(`/api/predictions?${new URLSearchParams(params)}`),
    optimalTeam: (budget: number, horizon: number) =>
      get<OptimalTeam>(`/api/optimal-team?budget=${budget}&horizon=${horizon}`),
  };
}

export type Api = ReturnType<typeof createApi>;
