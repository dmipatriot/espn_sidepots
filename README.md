# ESPN Sidepots

Automation for ESPN fantasy football side competitions including Price Is Right, season-long efficiency, and survivor pool reporting.

## Local Development

1. Create and activate a Python 3.11 virtual environment.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Export your ESPN authentication cookies:
   ```bash
   export ESPN_S2="<espn_s2_cookie>"
   export SWID="{<swid_guid>}"
   ```
4. Run the collector locally:
   ```bash
   python -m app.main --mode all --weeks auto
   ```
   The command prints compact summaries for each sidepot. Add `--dry-run` to avoid posting to Discord during local testing.

## Configuration

### Required environment variables

| Variable | Description |
| --- | --- |
| `LEAGUE_ID` | ESPN league identifier (integer). |
| `SEASON` | Season year (integer). |
| `ESPN_S2` | ESPN authentication cookie. |
| `SWID` | ESPN SWID cookie (must include surrounding braces `{}`). |
| `WEBHOOK_PIR` | Discord webhook for Price Is Right summaries. |
| `WEBHOOK_EFFICIENCY` | Discord webhook for efficiency summaries. |
| `WEBHOOK_SURVIVOR` | Discord webhook for survivor summaries. |
| `TIMEZONE` | Olson timezone used when scheduling cron runs. |

Environment variables always take precedence over values defined in `config/league.yaml`, making it safe to override credentials in deployment environments without editing the repo.

### Cookie notes

- The `SWID` value **must** include braces (example: `{A1B2C3...}`) and should not be quoted when stored in Render or your shell.
- The `ESPN_S2` cookie should be copied without quotes or trailing spaces.
- ESPN rotates these cookies periodically; refresh and redeploy if requests begin returning 401/403 responses.

### Cron-friendly commands

Run everything for the latest completed week(s):

```bash
python -m app.main --mode all --weeks auto
```

Backfill a survivor report for a specific range:

```bash
python -m app.main --mode survivor --weeks 1-8
```

### Lock file behavior

To prevent overlapping runs, the job writes `/tmp/espn_sidepots.lock` on startup. If a lock file newer than five minutes exists, the job logs `lock present, skipping` and exits cleanly. Delete the file or wait for five minutes to bypass the guard when re-running manually.

## Testing

```bash
pytest
```

## Render Deployment

1. Build the container image used by Render jobs:
   ```bash
   docker build -t espn-sidepots .
   ```
2. Configure a Render cron job (recommended daily during the season) with a command from the [cron-friendly commands](#cron-friendly-commands) section.
3. Set the [required environment variables](#required-environment-variables) in Render.

The cron schedule should run after weekly scoring finalizes (for example, early Tuesday morning in the configured league timezone).
