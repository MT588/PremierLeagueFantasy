"""Static name mappings from FPL team codes to external-source club names.

Keys are the stable FPL team `code` (every code present in team_seasons
2021-22 onward). A pytest asserts full coverage, so a newly promoted club
fails loudly here instead of silently losing its Elo/odds data.

ClubElo names are the display names from the daily-CSV `Club` column; the
per-club history URL is that name with spaces stripped (handled by the
ingester). football-data.co.uk names match the HomeTeam/AwayTeam CSV columns.
"""

# FPL code -> (FPL name, ClubElo name, football-data.co.uk name)
TEAM_NAMES: dict[int, tuple[str, str, str]] = {
    1: ("Man Utd", "Man United", "Man United"),
    2: ("Leeds", "Leeds", "Leeds"),
    3: ("Arsenal", "Arsenal", "Arsenal"),
    4: ("Newcastle", "Newcastle", "Newcastle"),
    6: ("Spurs", "Tottenham", "Tottenham"),
    7: ("Aston Villa", "Aston Villa", "Aston Villa"),
    8: ("Chelsea", "Chelsea", "Chelsea"),
    9: ("Coventry City", "Coventry", "Coventry"),
    11: ("Everton", "Everton", "Everton"),
    13: ("Leicester", "Leicester", "Leicester"),
    14: ("Liverpool", "Liverpool", "Liverpool"),
    17: ("Nott'm Forest", "Forest", "Nott'm Forest"),
    20: ("Southampton", "Southampton", "Southampton"),
    21: ("West Ham", "West Ham", "West Ham"),
    31: ("Crystal Palace", "Crystal Palace", "Crystal Palace"),
    36: ("Brighton", "Brighton", "Brighton"),
    39: ("Wolves", "Wolves", "Wolves"),
    40: ("Ipswich Town", "Ipswich", "Ipswich"),
    43: ("Man City", "Man City", "Man City"),
    45: ("Norwich", "Norwich", "Norwich"),
    49: ("Sheffield Utd", "Sheffield United", "Sheffield United"),
    54: ("Fulham", "Fulham", "Fulham"),
    56: ("Sunderland", "Sunderland", "Sunderland"),
    57: ("Watford", "Watford", "Watford"),
    88: ("Hull City", "Hull", "Hull"),
    90: ("Burnley", "Burnley", "Burnley"),
    91: ("Bournemouth", "Bournemouth", "Bournemouth"),
    94: ("Brentford", "Brentford", "Brentford"),
    102: ("Luton", "Luton", "Luton"),
}


def clubelo_name(team_code: int) -> str:
    return TEAM_NAMES[team_code][1]


def footballdata_name(team_code: int) -> str:
    return TEAM_NAMES[team_code][2]


# Understat team_title values (differ from all of the above for several clubs)
UNDERSTAT_NAMES: dict[int, str] = {
    1: "Manchester United",
    2: "Leeds",
    3: "Arsenal",
    4: "Newcastle United",
    6: "Tottenham",
    7: "Aston Villa",
    8: "Chelsea",
    9: "Coventry",
    11: "Everton",
    13: "Leicester",
    14: "Liverpool",
    17: "Nottingham Forest",
    20: "Southampton",
    21: "West Ham",
    31: "Crystal Palace",
    36: "Brighton",
    39: "Wolverhampton Wanderers",
    40: "Ipswich",
    43: "Manchester City",
    45: "Norwich",
    49: "Sheffield United",
    54: "Fulham",
    56: "Sunderland",
    57: "Watford",
    88: "Hull",
    90: "Burnley",
    91: "Bournemouth",
    94: "Brentford",
    102: "Luton",
}
