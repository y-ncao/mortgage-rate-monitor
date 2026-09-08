#!/usr/bin/env python3
"""Email a warning when the rate check fails.

Deliberately standard-library only: this has to keep working when the thing
that broke is dependency installation or an import in check_rates.py.
"""

import os
import smtplib
from email.mime.text import MIMEText

GMAIL_USER = os.environ.get("GMAIL_USER", "")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "")
ALERT_EMAIL = os.environ.get("ALERT_EMAIL", "")


def run_url():
    """Link to the failing Actions run, when running inside Actions."""
    server = os.environ.get("GITHUB_SERVER_URL")
    repo = os.environ.get("GITHUB_REPOSITORY")
    run_id = os.environ.get("GITHUB_RUN_ID")
    if server and repo and run_id:
        return f"{server}/{repo}/actions/runs/{run_id}"
    return None


def main():
    if not GMAIL_USER or not GMAIL_APP_PASSWORD or not ALERT_EMAIL:
        print("Email credentials not configured, cannot send failure notification")
        return

    repo = os.environ.get("GITHUB_REPOSITORY", "mortgage-rate-monitor")
    url = run_url()
    link = f'<p><a href="{url}">View the failed run</a></p>' if url else ""

    html = f"""<html><body style="font-family: -apple-system, Arial, sans-serif; color: #222;">
<h2 style="color:#d32f2f; margin-bottom:4px;">Mortgage Rate Monitor Failed</h2>
<p style="color:#666; margin-top:0;">{repo}</p>
<p>Today's rate check did not complete. Nothing was recorded and no change alert
was sent, so today's rates are unknown rather than unchanged.</p>
<p>Usual causes: the OptimalBlue API changed shape or stopped responding, SFCU
retired the quote widget, or the Gmail app password was revoked.</p>
{link}
</body></html>"""

    msg = MIMEText(html, "html")
    msg["Subject"] = "[ALERT] SFCU Mortgage Rate Monitor failed"
    msg["From"] = GMAIL_USER
    msg["To"] = ALERT_EMAIL

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        server.send_message(msg)
    print(f"Failure notification sent to {ALERT_EMAIL}")


if __name__ == "__main__":
    main()
