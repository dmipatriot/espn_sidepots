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

## Testing

```bash
pytest
```

## Render Deployment

1. Build the container image used by Render jobs:
   ```bash
   docker build -t espn-sidepots .
   ```
2. Configure a Render cron job (recommended daily during the season) with the command:
   ```bash
   python -m app.main --mode all --weeks auto
   ```
3. Set the following environment variables in Render:
   - `ESPN_S2` – ESPN authentication cookie.
   - `SWID` – ESPN SWID cookie (including braces).
   - `WEBHOOK_PIR` – Discord webhook for Price Is Right summaries.
   - `WEBHOOK_EFFICIENCY` – Discord webhook for efficiency summaries.
   - `WEBHOOK_SURVIVOR` – Discord webhook for survivor summaries.

The cron schedule should run after weekly scoring finalizes (for example, early Tuesday morning in the configured league timezone).
