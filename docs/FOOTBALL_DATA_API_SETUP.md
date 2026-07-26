# football-data.org API key — setup & enabling

The prediction model uses World Cup / international tournament data as a
fatigue-and-form signal (players who went deep into a summer tournament start
the season differently). Without an API key the pipeline falls back to a
Wikipedia squad-list proxy (who was in a squad + how far their nation went).
**With** a free football-data.org key it upgrades to exact per-player minutes.

The pipeline works fine without the key — nothing blocks on this. When you
register the key, one command upgrades the data in place.

## 1. Register (2 minutes, free)

1. Go to https://www.football-data.org/client/register
2. Fill in name + email; the free tier is the default (no payment info).
3. The API token arrives by email / is shown in your account page.

Free tier limits: 10 requests/minute, ~12 competitions including
**World Cup (`WC`)**, **Champions League (`CL`)**, and **Premier League (`PL`)**.

## 2. Enable it in the project

Add one line to `backend/.env` (create the file from `.env.example` if needed):

```
FOOTBALL_DATA_API_KEY=your_token_here
```

The key stays local — `.env` is gitignored, never commit it.

## 3. Load the upgraded data

```bash
cd backend
uv run python -m pipeline.run_pipeline --international
uv run python -m ml.predict --horizon 5      # refresh predictions with the better signal
```

What happens on that run:
- The ingester probes one World Cup match to check whether the free tier
  exposes **lineups/appearances** (football-data.org has moved this between
  tiers before, so we verify instead of assuming).
- If lineups are available → `international_load.minutes` is filled with real
  per-player World Cup 2026 minutes (source = `football-data.org`).
- If not → it logs a clear message and keeps the Wikipedia squad+progress
  proxy (source = `wikipedia-proxy`). Nothing breaks; the model just uses the
  coarser signal.

## 4. Verify

```bash
uv run python - <<'EOF'
from sqlalchemy import text
from app.db import engine
with engine.connect() as c:
    rows = c.execute(text(
        "select source, count(*), count(minutes) as with_minutes "
        "from international_load where tournament='WC' and year=2026 group by source"
    )).all()
    print(rows)
EOF
```

You want to see `('football-data.org', N, N)` — meaning N players, all with
real minutes. `('wikipedia-proxy', N, 0)` means the fallback is still active.

## Things to go over together later

- [ ] Register the account + get the token
- [ ] Put it in `backend/.env` (and in the deployed environment when we host the backend)
- [ ] Run `--international` and the verify snippet above
- [ ] Decide whether to also pull **Champions League fixture dates** with the
      same key (would improve the fatigue features: real European match dates
      per club instead of a per-season flag — noted as a follow-up, not built yet)
- [ ] Retrain (`uv run python -m ml.train`) once real minutes are in, so the
      model weights the upgraded feature properly
