# SFCU Mortgage Rate Monitor

Monitors SFCU mortgage rates (30-year fixed and 7/1 ARM) daily via GitHub Actions
and emails you when rates change.

## How It Works

1. A GitHub Actions cron job runs daily in the morning Pacific time
2. Fetches current rates from SFCU's OptimalBlue API
3. Validates the response, then compares it against the newest snapshot in `data/last_rates.json`
4. Emails an alert if the best (lowest-points) rate or APR moved for either product
5. Commits the updated history back to the repo

Rates move roughly once every week or two, so most days send no email. To keep a
quiet inbox meaningful, the job also sends:

- a **check-in email** if nothing has gone out in `HEARTBEAT_DAYS` (default 7), and
- a **failure email** if the run breaks, so a dead monitor doesn't look like steady rates

## Setup

### 1. Gmail App Password

1. Go to [Google Account > Security](https://myaccount.google.com/security)
2. Enable 2-Step Verification if not already enabled
3. Go to [App Passwords](https://myaccount.google.com/apppasswords)
4. Generate a password for "Mail"
5. Save the 16-character password

### 2. GitHub Secrets

Settings > Secrets and variables > Actions > **Secrets**:

| Secret | Value |
|--------|-------|
| `GMAIL_USER` | Gmail address that sends the alerts |
| `GMAIL_APP_PASSWORD` | The 16-character app password from step 1 |

### 3. GitHub Variables

Settings > Secrets and variables > Actions > **Variables**. All four loan
variables are **required** — the job fails fast with a clear message if any is missing.

| Variable | Example | Meaning |
|----------|---------|---------|
| `ALERT_EMAIL` | `you@gmail.com` | Where alerts are delivered |
| `LOAN_AMOUNT` | `2249000` | Loan amount in dollars |
| `ESTIMATED_VALUE` | `2900000` | Estimated property value in dollars |
| `STATE` | `59` | OptimalBlue state code (`59` = California) |
| `ZIPCODE` | `94404` | Property ZIP code |

### 4. Test

Trigger the workflow manually: Actions > Check Mortgage Rates > Run workflow

## Local Testing

```bash
pip install -r requirements.txt

# Required — the script will not start without these
export LOAN_AMOUNT=2249000
export ESTIMATED_VALUE=2900000
export STATE=59
export ZIPCODE=94404

# Optional: set these too if you want to test the email itself
export GMAIL_USER=you@gmail.com
export GMAIL_APP_PASSWORD=xxxx-xxxx-xxxx-xxxx
export ALERT_EMAIL=you@gmail.com

cd src && python check_rates.py
```

Without the Gmail variables the script still fetches, validates, prints, and
records rates — it just skips sending.

Note that a local run rewrites `data/last_rates.json`. Work on a copy of the repo
if you don't want to commit the result.

## Configuration

Loan parameters and the tracked product list live in `src/config.py`. These
optional environment variables tune behavior:

| Variable | Default | Meaning |
|----------|---------|---------|
| `MAX_HISTORY` | `400` | Snapshots kept in `data/last_rates.json` (~13 months). Older ones are dropped so the file stops growing without bound. |
| `HEARTBEAT_DAYS` | `7` | Days of silence before a check-in email. Set to `0` to disable. |

## A Note on Timing

The workflow is scheduled for 13:00 UTC (6 AM PDT / 5 AM PST). GitHub runs
scheduled workflows on a best-effort basis and commonly starts them one to four
hours late, so the actual delivery time drifts through the morning. This is a
platform limitation, not something the repo can fix.
