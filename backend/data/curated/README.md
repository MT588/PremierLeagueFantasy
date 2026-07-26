# Curated data

Small hand-maintained datasets with no reliable free API. Loaded by
`python -m pipeline.run_pipeline --curated`.

## manager_changes.csv

One row per manager stint (`end_date` empty = current manager). Seeded from
the "Managerial changes" tables of the Wikipedia per-season Premier League
articles (2021-22 → 2026-27), July 2026.

**Update workflow**: when a PL club changes manager, add an `end_date` to the
old stint and a new row (caretakers get `is_caretaker=true`), then re-run
`--curated`. Rows only need to be accurate for periods when the club is in
the Premier League.

## european_competitions.csv

Which PL clubs play European football each season (UCL/UEL/UECL); one row per
(season, club). Update each June when qualification settles.

## understat_overrides.csv

Manual FPL↔Understat identity fixes for players the fuzzy matcher misses.
Add `understat_id,player_code,note` rows based on the unmatched report printed
by `--understat`, then re-run it.
