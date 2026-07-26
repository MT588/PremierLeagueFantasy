"""FPL <-> Understat identity resolution.

Strategy per EPL season (team context makes the join reliable):
  1. exact normalized full-name + same team          -> confidence 1.0
  2. exact normalized full-name, unique across pool  -> 0.95
  3. fuzzy full-name (token_sort >= 90) + same team  -> 0.90
  4. fuzzy web_name  (token_sort >= 85) + same team  -> 0.85
Position sanity: a GK on one side must be a GK on the other.
Manual overrides (data/curated/understat_overrides.csv) win over everything.
New signings with no EPL history match by name against foreign league pools
(threshold 93 + position sanity), else land in the unmatched report.
"""

import csv
import html
import logging
import unicodedata
from pathlib import Path

import pandas as pd
from rapidfuzz import fuzz
from sqlalchemy import Engine, text

log = logging.getLogger(__name__)

CURATED = Path(__file__).resolve().parent.parent / "data" / "curated"

FPL_POOL_SQL = """
select ps.player_code, ps.position, ps.team_code,
       p.first_name || ' ' || p.second_name as full_name, p.web_name,
       s.start_year
from player_seasons ps
join players p on p.code = ps.player_code
join seasons s on s.id = ps.season_id
"""


def norm(name: str) -> str:
    s = html.unescape(name)
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower().replace("-", " ").replace("'", "").replace(".", " ")
    return " ".join(s.split())


def name_score(uname: str, cand_full: str, cand_web: str) -> float:
    """Similarity that tolerates subset names ('Alisson' vs 'Alisson Becker',
    'Bruno Fernandes' vs 'Bruno Miguel Borges Fernandes') via token_set_ratio,
    lightly discounted so a full token_sort agreement still wins ties."""
    return max(
        fuzz.token_sort_ratio(uname, cand_full),
        fuzz.token_set_ratio(uname, cand_full) - 2,
        fuzz.token_sort_ratio(uname, cand_web),
        fuzz.token_set_ratio(uname, cand_web) - 2,
    )


def is_gk(understat_position: str | None) -> bool:
    return bool(understat_position) and "GK" in understat_position


def position_sane(fpl_position: int, understat_position: str | None) -> bool:
    if understat_position is None or understat_position in ("Sub",):
        return True
    return (fpl_position == 1) == is_gk(understat_position)


def load_overrides() -> dict[int, int]:
    path = CURATED / "understat_overrides.csv"
    out = {}
    with open(path) as f:
        for row in csv.DictReader(f):
            if row.get("understat_id"):
                out[int(row["understat_id"])] = int(row["player_code"])
    return out


def match_epl_players(engine: Engine, epl_pools: dict[int, list[dict]]) -> list[dict]:
    from pipeline.team_names import UNDERSTAT_NAMES

    with engine.connect() as conn:
        fpl = pd.read_sql(text(FPL_POOL_SQL), conn)
    fpl["norm_full"] = fpl["full_name"].map(norm)
    fpl["norm_web"] = fpl["web_name"].map(norm)
    understat_title_to_code = {v: k for k, v in UNDERSTAT_NAMES.items()}
    overrides = load_overrides()

    results: dict[int, dict] = {}
    report_rows = []

    for season, players in sorted(epl_pools.items()):
        pool = fpl[fpl["start_year"] == season]
        by_name = pool.groupby("norm_full")
        season_matched_minutes = 0
        season_total_minutes = 0
        for u in players:
            uid = int(u["id"])
            minutes = int(u["time"])
            season_total_minutes += minutes
            if uid in results:
                if results[uid]["player_code"] is not None:
                    season_matched_minutes += minutes
                continue

            entry = {
                "understat_id": uid,
                "player_code": None,
                "understat_name": u["player_name"],
                "match_method": "unmatched",
                "confidence": None,
                "season_first_seen": str(season),
            }
            if uid in overrides:
                entry.update(
                    player_code=overrides[uid], match_method="override", confidence=1.0
                )
                results[uid] = entry
                season_matched_minutes += minutes
                continue

            uname = norm(u["player_name"])
            uteams = {
                understat_title_to_code.get(t.strip())
                for t in u["team_title"].split(",")
            } - {None}
            upos = u.get("position")

            cand = (
                by_name.get_group(uname) if uname in by_name.groups else pool.iloc[0:0]
            )
            if len(cand):
                cand = cand.loc[[position_sane(p, upos) for p in cand["position"]]]
            same_team = cand[cand["team_code"].isin(uteams)]
            if len(same_team) >= 1:
                entry.update(
                    player_code=int(same_team.iloc[0]["player_code"]),
                    match_method="exact",
                    confidence=1.0,
                )
            elif len(cand) == 1:
                entry.update(
                    player_code=int(cand.iloc[0]["player_code"]),
                    match_method="exact-anyteam",
                    confidence=0.95,
                )
            else:
                team_pool = pool[pool["team_code"].isin(uteams)]
                if len(team_pool):
                    team_pool = team_pool.loc[
                        [position_sane(p, upos) for p in team_pool["position"]]
                    ]
                scored = sorted(
                    (
                        (name_score(uname, r.norm_full, r.norm_web), r.player_code)
                        for r in team_pool.itertuples()
                    ),
                    reverse=True,
                )
                if scored and scored[0][0] >= 88:
                    # ambiguity guard: runner-up within 3 points -> skip to report
                    if len(scored) > 1 and scored[0][0] - scored[1][0] < 3:
                        log.warning(
                            "ambiguous fuzzy match for %r (%.0f vs %.0f) — skipping",
                            u["player_name"],
                            scored[0][0],
                            scored[1][0],
                        )
                    else:
                        entry.update(
                            player_code=int(scored[0][1]),
                            match_method="fuzzy",
                            confidence=round(scored[0][0] / 100 - 0.05, 2),
                        )
            results[uid] = entry
            if entry["player_code"] is not None:
                season_matched_minutes += minutes
            else:
                report_rows.append((season, u["player_name"], minutes))

        rate = season_matched_minutes / max(season_total_minutes, 1)
        log.info("understat match %d: minutes-weighted %.2f%%", season, 100 * rate)

    report_rows.sort(key=lambda r: -r[2])
    if report_rows:
        log.warning("top unmatched EPL players (season, name, minutes):")
        for season, name, minutes in report_rows[:20]:
            log.warning("  %d  %-30s %5d min", season, name, minutes)
    return list(results.values())


def match_foreign_players(
    engine: Engine,
    foreign_pools: dict[tuple[str, int], list[dict]],
    existing: list[dict],
) -> list[dict]:
    """Name-match current-pool FPL players with no EPL Understat history
    against recent foreign-league pools (new signings)."""
    matched_codes = {r["player_code"] for r in existing if r["player_code"] is not None}
    known_uids = {r["understat_id"] for r in existing}

    with engine.connect() as conn:
        pool = pd.read_sql(
            text(
                FPL_POOL_SQL
                + " where ps.season_id = (select id from seasons where is_current)"
            ),
            conn,
        )
    pool = pool[~pool["player_code"].isin(matched_codes)]
    pool["norm_full"] = pool["full_name"].map(norm)
    pool["norm_web"] = pool["web_name"].map(norm)

    candidates: dict[int, dict] = {}
    for players in foreign_pools.values():
        for u in players:
            uid = int(u["id"])
            if uid in known_uids or uid in candidates:
                continue
            candidates[uid] = u

    out = []
    for u in candidates.values():
        uid = int(u["id"])
        uname = norm(u["player_name"])
        upos = u.get("position")
        best = None
        second = 0.0
        for r in pool.itertuples():
            if not position_sane(r.position, upos):
                continue
            score = name_score(uname, r.norm_full, r.norm_web)
            if best is None or score > best[1]:
                second = best[1] if best else 0.0
                best = (r.player_code, score)
            elif score > second:
                second = score
        if best is None or best[1] < 93 or best[1] - second < 3:
            best = None
        if best is not None:
            out.append(
                {
                    "understat_id": uid,
                    "player_code": int(best[0]),
                    "understat_name": u["player_name"],
                    "match_method": "foreign-fuzzy",
                    "confidence": round(best[1] / 100, 2) - 0.05,
                    "season_first_seen": None,
                }
            )
    # two foreign profiles must never claim the same FPL player: keep the best
    out.sort(key=lambda r: -r["confidence"])
    seen_codes: set[int] = set()
    deduped = []
    for r in out:
        if r["player_code"] in seen_codes:
            continue
        seen_codes.add(r["player_code"])
        deduped.append(r)
    log.info("foreign matching: %d new signings matched", len(deduped))
    return deduped
