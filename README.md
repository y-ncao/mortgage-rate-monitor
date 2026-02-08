# Mortgage Rate Monitor

Monitors SFCU mortgage rates (30-year fixed and 7/1 ARM) daily via GitHub Actions and sends email alerts when rates change.

## How It Works

1. A GitHub Actions cron job runs daily at 6 AM PST
2. Fetches current rates from SFCU's OptimalBlue API
3. Compares with the last known rates in `data/last_rates.json`
4. Sends an email alert if rates changed
5. Commits the updated rates back to the repo

## Setup

### 1. Gmail App Password

1. Go to [Google Account > Security](https://myaccount.google.com/security)
2. Enable 2-Step Verification if not already enabled
3. Go to [App Passwords](https://myaccount.google.com/apppasswords)
4. Generate a password for "Mail"
5. Save the 16-character password

### 2. GitHub Secrets

Add these secrets in your repo under Settings > Secrets and variables > Actions:

| Secret | Value |
|--------|-------|
| `GMAIL_USER` | Your Gmail address |
| `GMAIL_APP_PASSWORD` | The app password from step 1 |
| `ALERT_EMAIL` | Email to receive alerts (default: yancao.eng@gmail.com) |

### 3. Test

Trigger the workflow manually: Actions > Check Mortgage Rates > Run workflow

## Local Testing

```bash
pip install -r requirements.txt

# Optional: set email env vars to test notifications
export GMAIL_USER=you@gmail.com
export GMAIL_APP_PASSWORD=xxxx-xxxx-xxxx-xxxx
export ALERT_EMAIL=you@gmail.com

cd src && python check_rates.py
```

## Configuration

Edit `src/config.py` to change loan parameters, tracked products, or API settings.
