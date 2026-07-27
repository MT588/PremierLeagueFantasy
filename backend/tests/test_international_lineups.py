"""The Wikipedia line-up parser, pinned against a committed wikitext fixture.

No network: `tests/fixtures/wc2026_r16_canada_morocco.wikitext` is the real
round-of-16 match block, saved verbatim from the 2026 knockout-stage page. The
loader's whole value is that minutes come out of the substitution markup exactly,
so the numbers below are checked against the page rather than against the parser.

Two of these tests exist because the parser shipped with the bug they now
forbid: `|goals1=` used to run straight through `|goals2=` (double-counting the
away scorers and adding penalty-shootout goals), and own goals used to be
credited to the player who put through his own net.
"""

import datetime as dt
from pathlib import Path

import pytest

from pipeline.ingest_international import (
    LineupParse,
    _count_goals,
    _parse_goals,
    parse_lineups,
)

FIXTURE = Path(__file__).parent / "fixtures" / "wc2026_r16_canada_morocco.wikitext"


@pytest.fixture(scope="module")
def parsed() -> LineupParse:
    parse = LineupParse()
    parse_lineups(FIXTURE.read_text(encoding="utf-8"), parse)
    return parse


def test_block_parses_as_one_match(parsed):
    assert parsed.matches_parsed == 1
    # 11 starters plus used substitutes, both teams
    assert parsed.lineup_slots == 32
    assert len(parsed.minutes) == 32


def test_starter_substituted_off_gets_exact_minutes(parsed):
    """Richie Laryea started and came off on 78'."""
    assert parsed.minutes["Richie Laryea"] == 78
    assert parsed.starts["Richie Laryea"] == 1
    assert parsed.appearances["Richie Laryea"] == 1


def test_substitute_gets_minutes_from_his_introduction(parsed):
    """Cyle Larin came on at 63', so 90 - 63 = 27 minutes and no start."""
    assert parsed.minutes["Cyle Larin"] == 27
    assert parsed.starts["Cyle Larin"] == 0
    assert parsed.appearances["Cyle Larin"] == 1


def test_unused_substitutes_are_absent(parsed):
    """A bench player with no {{subon}} never appeared and must not be recorded
    with zero minutes — that would make him look rested rather than unused."""
    assert all(minutes > 0 for minutes in parsed.minutes.values())


def test_both_countries_carry_the_match_date(parsed):
    assert parsed.country_last_match == {
        "Canada": dt.date(2026, 7, 4),
        "Morocco": dt.date(2026, 7, 4),
    }
    assert parsed.last_match["Richie Laryea"] == dt.date(2026, 7, 4)


def test_scorers_are_read_from_both_teams(parsed):
    """The regression guard for `|goals1=` swallowing `|goals2=`: a scorer from
    each side has to survive, and a brace has to count as two."""
    assert parsed.goals == {"Ounahi": 2, "Rahimi": 1}
    assert parsed.total_goals == 3


def test_goals_stop_at_the_next_parameter():
    """`|goals1=` must terminate on a parameter name containing digits."""
    block = (
        "|goals1=\n"
        "* [[Alpha Player]] {{goal|12}}\n"
        "|goals2=\n"
        "* [[Beta Player]] {{goal|34}}\n"
        "|penalties1=\n"
        "* [[Alpha Player]] {{pen|1}}\n"
        "}}"
    )
    assert _parse_goals(block) == {"Alpha Player": 1, "Beta Player": 1}


def test_own_goals_are_not_credited_to_the_scorer():
    assert _count_goals("* [[Alpha Player]] {{goal|23}}") == 1
    assert _count_goals("* [[Alpha Player]] {{goal|23|67}}") == 2
    assert _count_goals("* [[Alpha Player]] 50', 82'") == 2
    assert _count_goals("* [[Alpha Player]] {{goal|23|own goal}}") == 0
    assert _count_goals("* [[Alpha Player]] 23' (o.g.)") == 0


def test_health_probe_rejects_a_partial_parse(parsed):
    """One match out of an expected 104 must not pass as healthy — that is the
    check that keeps a drifted markup from half-filling the table."""
    assert not parsed.healthy(expected_matches=104)
    # against its own single match it is internally consistent
    assert parsed.healthy(expected_matches=1)
