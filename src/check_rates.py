#!/usr/bin/env python3
"""Fetch SFCU mortgage rates and send email alerts on changes."""

import json
import smtplib
import sys
from datetime import datetime, timezone
from email.mime.text import MIMEText
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

from config import (
    ALERT_EMAIL,
    CLIENT_ID,
    DATA_FILE,
    DISPLAY_TIMEZONE,
    FORM_ID,
    GMAIL_APP_PASSWORD,
    GMAIL_USER,
    HEARTBEAT_DAYS,
    LOAN_PARAMS,
    MAX_HISTORY,
    SEARCH_URL,
    TRACKED_PRODUCTS,
    USER_ID,
)

PACIFIC = ZoneInfo(DISPLAY_TIMEZONE)


def fetch_rates():
    """Fetch rates via OptimalBlue API."""
    payload = {
        "clientId": CLIENT_ID,
        "userId": USER_ID,
        "formId": FORM_ID,
        "inputs": LOAN_PARAMS,
    }

    resp = requests.post(
        SEARCH_URL,
        json=payload,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/plain, */*",
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()

    product_types = data.get("results", {}).get("$values", [])

    rates = []
    for pt in product_types:
        name = pt.get("name", "").strip()
        if not any(tracked.lower() in name.lower() for tracked in TRACKED_PRODUCTS):
            continue
        display_name = name.replace("Non-Conforming", "Jumbo")
        products = pt.get("products", {}).get("$values", [])
        for prod in products:
            rates.append({
                "product": display_name,
                "rate": prod.get("rate"),
                "apr": prod.get("apr"),
                "monthly_payment": prod.get("monthlyPayments"),
                "points": prod.get("discounts", 0),
                "price": prod.get("price"),
            })

    return rates


def validate_rates(rates):
    """Return reasons the fetched data can't be trusted, empty list if it's fine.

    A response that parses but has lost a product or has null rates means the
    API changed shape underneath us. Recording that as if it were real data
    would poison the history and fire a bogus "rates changed" alert.
    """
    problems = []

    missing = [
        tracked for tracked in TRACKED_PRODUCTS
        if not any(tracked.lower() in r["product"].lower() for r in rates)
    ]
    if missing:
        problems.append(f"No rates returned for: {', '.join(missing)}")

    for r in rates:
        if r.get("rate") is None or r.get("apr") is None:
            problems.append(
                f"Missing rate or APR for {r['product']} at {r.get('points')} points"
            )

    return problems


def load_history():
    """Load the full rate history from disk."""
    path = Path(DATA_FILE)
    if not path.exists():
        return []
    with open(path) as f:
        data = json.load(f)
    # Migration: convert old single-snapshot format to list
    if isinstance(data, dict):
        if data.get("rates"):
            return [{"checked_at": data.get("last_checked"), "rates": data["rates"]}]
        return []
    return data


def save_history(history):
    """Save full rate history to disk."""
    path = Path(DATA_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(history, f, indent=2)
    print(f"Saved {len(history)} snapshots to {path}")


def best_by_product(rates):
    """Get the lowest-points rate option for each product."""
    best = {}
    for r in rates:
        p = r["product"]
        if p not in best or r.get("points", 99) < best[p].get("points", 99):
            best[p] = r
    return best


def rates_changed(old_rates, new_rates):
    """Check if the best (lowest-points) rate for each product changed."""
    if not old_rates:
        return True

    old_best = best_by_product(old_rates)
    new_best = best_by_product(new_rates)

    if set(old_best.keys()) != set(new_best.keys()):
        return True
    for product in new_best:
        old = old_best[product]
        new = new_best[product]
        if old.get("rate") != new.get("rate") or old.get("apr") != new.get("apr"):
            return True
    return False


def days_since_last_email(history, now):
    """Days since the last alert, or None if no email is recorded in history."""
    for snap in history:
        sent = snap.get("emailed_at")
        if not sent:
            continue
        try:
            return (now - datetime.fromisoformat(sent)).days
        except ValueError:
            continue
    return None


def fmt_timestamp(dt):
    """Format a UTC datetime in Pacific time, with the right PST/PDT label."""
    return dt.astimezone(PACIFIC).strftime("%Y-%m-%d %I:%M %p %Z")


def fmt_rate(val):
    return f"{val:.3f}%" if val is not None else "N/A"


def fmt_payment(val):
    return f"${val:,.2f}" if val is not None else "N/A"


def fmt_points(val):
    return f"{val:.1f}" if val is not None else "N/A"


def diff_arrow(old_val, new_val):
    """Return an HTML arrow indicator for a change."""
    if old_val is None or new_val is None:
        return ""
    diff = new_val - old_val
    if abs(diff) < 0.0005:
        return ""
    if diff > 0:
        return f' <span style="color:#d32f2f;">&#9650; +{diff:.3f}</span>'
    return f' <span style="color:#2e7d32;">&#9660; {diff:.3f}</span>'


def build_email_html(old_rates, new_rates, checked_at, heartbeat=False, quiet_days=None):
    """Build an HTML email body highlighting changes."""
    new_best = best_by_product(new_rates)
    old_best = best_by_product(old_rates) if old_rates else {}

    if heartbeat:
        title = "SFCU Mortgage Rates &mdash; Still Monitoring"
        if quiet_days is None:
            quiet = "No rate change alert has gone out recently."
        else:
            quiet = f"No rate change in the last {quiet_days} days."
        note = (f'<p style="background:#e8f4fd; border-left:4px solid #1565c0; '
                f'padding:10px 14px; margin:0 0 20px 0;">{quiet} '
                f'This is a periodic check-in, so that a quiet inbox means rates '
                f'held steady rather than the monitor having broken.</p>')
    elif old_rates:
        title = "SFCU Mortgage Rate Change Alert"
        note = ""
    else:
        title = "SFCU Mortgage Rate Initial Alert"
        note = ""

    html = f"""<html><body style="font-family: -apple-system, Arial, sans-serif; color: #222;">
<h2 style="margin-bottom:4px;">{title}</h2>
<p style="color:#666; margin-top:0;">Checked at {checked_at}</p>
{note}
"""

    if old_rates:
        # Summary of changes per product (best rate)
        html += '<h3 style="margin-bottom:8px;">Summary of Changes (best rate per product)</h3>'
        html += '<table style="border-collapse:collapse; margin-bottom:20px;">'
        html += ('<tr style="background:#f5f5f5;">'
                 '<th style="padding:8px 12px; text-align:left; border-bottom:2px solid #ddd;">Product</th>'
                 '<th style="padding:8px 12px; text-align:right; border-bottom:2px solid #ddd;">Previous Rate</th>'
                 '<th style="padding:8px 12px; text-align:right; border-bottom:2px solid #ddd;">Current Rate</th>'
                 '<th style="padding:8px 12px; text-align:right; border-bottom:2px solid #ddd;">Change</th>'
                 '<th style="padding:8px 12px; text-align:right; border-bottom:2px solid #ddd;">Previous APR</th>'
                 '<th style="padding:8px 12px; text-align:right; border-bottom:2px solid #ddd;">Current APR</th>'
                 '<th style="padding:8px 12px; text-align:right; border-bottom:2px solid #ddd;">Change</th>'
                 '</tr>')
        for product in sorted(new_best.keys()):
            new = new_best[product]
            old = old_best.get(product)
            if old:
                rate_diff = (new.get("rate") or 0) - (old.get("rate") or 0)
                apr_diff = (new.get("apr") or 0) - (old.get("apr") or 0)
                if abs(rate_diff) < 0.0005:
                    rate_color = "#666"
                    rate_change = "no change"
                elif rate_diff > 0:
                    rate_color = "#d32f2f"
                    rate_change = f"&#9650; +{rate_diff:.3f}%"
                else:
                    rate_color = "#2e7d32"
                    rate_change = f"&#9660; {rate_diff:.3f}%"

                if abs(apr_diff) < 0.0005:
                    apr_color = "#666"
                    apr_change = "no change"
                elif apr_diff > 0:
                    apr_color = "#d32f2f"
                    apr_change = f"&#9650; +{apr_diff:.3f}%"
                else:
                    apr_color = "#2e7d32"
                    apr_change = f"&#9660; {apr_diff:.3f}%"

                html += (f'<tr>'
                         f'<td style="padding:8px 12px; border-bottom:1px solid #eee;"><b>{product}</b></td>'
                         f'<td style="padding:8px 12px; text-align:right; border-bottom:1px solid #eee;">{fmt_rate(old.get("rate"))}</td>'
                         f'<td style="padding:8px 12px; text-align:right; border-bottom:1px solid #eee;"><b>{fmt_rate(new.get("rate"))}</b></td>'
                         f'<td style="padding:8px 12px; text-align:right; border-bottom:1px solid #eee; color:{rate_color};"><b>{rate_change}</b></td>'
                         f'<td style="padding:8px 12px; text-align:right; border-bottom:1px solid #eee;">{fmt_rate(old.get("apr"))}</td>'
                         f'<td style="padding:8px 12px; text-align:right; border-bottom:1px solid #eee;"><b>{fmt_rate(new.get("apr"))}</b></td>'
                         f'<td style="padding:8px 12px; text-align:right; border-bottom:1px solid #eee; color:{apr_color};"><b>{apr_change}</b></td>'
                         f'</tr>')
            else:
                html += (f'<tr>'
                         f'<td style="padding:8px 12px; border-bottom:1px solid #eee;"><b>{product}</b></td>'
                         f'<td colspan="6" style="padding:8px 12px; border-bottom:1px solid #eee; color:#1565c0;"><b>NEW</b></td>'
                         f'</tr>')
        html += '</table>'

    # Full rate table with inline diffs
    html += '<h3 style="margin-bottom:8px;">All Rate Options</h3>'
    html += '<table style="border-collapse:collapse;">'
    html += ('<tr style="background:#f5f5f5;">'
             '<th style="padding:8px 12px; text-align:left; border-bottom:2px solid #ddd;">Product</th>'
             '<th style="padding:8px 12px; text-align:right; border-bottom:2px solid #ddd;">Rate</th>'
             '<th style="padding:8px 12px; text-align:right; border-bottom:2px solid #ddd;">APR</th>'
             '<th style="padding:8px 12px; text-align:right; border-bottom:2px solid #ddd;">Monthly Payment</th>'
             '<th style="padding:8px 12px; text-align:right; border-bottom:2px solid #ddd;">Points</th>'
             '</tr>')

    # Build old rates lookup by (product, points) for per-row diffs
    old_lookup = {}
    if old_rates:
        for r in old_rates:
            old_lookup[(r["product"], r.get("points"))] = r

    for r in sorted(new_rates, key=lambda x: (x["product"], x.get("points", 0))):
        old = old_lookup.get((r["product"], r.get("points")))
        rate_diff_html = diff_arrow(old.get("rate"), r.get("rate")) if old else ""
        apr_diff_html = diff_arrow(old.get("apr"), r.get("apr")) if old else ""
        pmt_diff_html = ""
        if old and old.get("monthly_payment") is not None and r.get("monthly_payment") is not None:
            pmt_d = r["monthly_payment"] - old["monthly_payment"]
            if abs(pmt_d) >= 0.01:
                color = "#d32f2f" if pmt_d > 0 else "#2e7d32"
                arrow = "&#9650;" if pmt_d > 0 else "&#9660;"
                pmt_diff_html = f' <span style="color:{color};">{arrow} ${abs(pmt_d):,.2f}</span>'

        html += (f'<tr>'
                 f'<td style="padding:6px 12px; border-bottom:1px solid #eee;">{r["product"]}</td>'
                 f'<td style="padding:6px 12px; text-align:right; border-bottom:1px solid #eee;">{fmt_rate(r.get("rate"))}{rate_diff_html}</td>'
                 f'<td style="padding:6px 12px; text-align:right; border-bottom:1px solid #eee;">{fmt_rate(r.get("apr"))}{apr_diff_html}</td>'
                 f'<td style="padding:6px 12px; text-align:right; border-bottom:1px solid #eee;">{fmt_payment(r.get("monthly_payment"))}{pmt_diff_html}</td>'
                 f'<td style="padding:6px 12px; text-align:right; border-bottom:1px solid #eee;">{fmt_points(r.get("points"))}</td>'
                 f'</tr>')

    html += '</table>'
    html += '</body></html>'
    return html


def format_rate_table(rates, label="Current"):
    """Format rates as a readable text table for console output."""
    lines = [f"\n{label} Rates:"]
    lines.append("-" * 75)
    lines.append(f"{'Product':<30} {'Rate':>7} {'APR':>7} {'Payment':>12} {'Points':>7}")
    lines.append("-" * 75)
    for r in sorted(rates, key=lambda x: (x["product"], x.get("points", 0))):
        rate = fmt_rate(r.get("rate"))
        apr = fmt_rate(r.get("apr"))
        payment = fmt_payment(r.get("monthly_payment"))
        points = fmt_points(r.get("points"))
        lines.append(f"{r['product']:<30} {rate:>7} {apr:>7} {payment:>12} {points:>7}")
    lines.append("-" * 75)
    return "\n".join(lines)


def send_email(subject, html):
    """Send one email via Gmail SMTP. Returns True if it actually went out."""
    if not GMAIL_USER or not GMAIL_APP_PASSWORD:
        print("Email credentials not configured, skipping email notification")
        print("Set GMAIL_USER and GMAIL_APP_PASSWORD environment variables")
        return False

    msg = MIMEText(html, "html")
    msg["Subject"] = subject
    msg["From"] = GMAIL_USER
    msg["To"] = ALERT_EMAIL

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        server.send_message(msg)
    print(f"Email sent to {ALERT_EMAIL}")
    return True


def send_change_email(old_rates, new_rates, now):
    """Alert that the best rate moved."""
    stamp = fmt_timestamp(now)
    return send_email(
        f"SFCU Mortgage Rate Change - {stamp}",
        build_email_html(old_rates, new_rates, stamp),
    )


def send_heartbeat_email(new_rates, now, quiet_days):
    """Periodic check-in so a silent inbox is distinguishable from a dead job."""
    stamp = fmt_timestamp(now)
    return send_email(
        f"SFCU Mortgage Rates - No Change ({stamp})",
        build_email_html(None, new_rates, stamp, heartbeat=True, quiet_days=quiet_days),
    )


def main():
    now = datetime.now(timezone.utc)
    print(f"Checking SFCU mortgage rates at {now.isoformat()}")

    rates = fetch_rates()
    if not rates:
        sys.exit("ERROR: Failed to fetch any matching rates")

    problems = validate_rates(rates)
    if problems:
        for problem in problems:
            print(f"ERROR: {problem}")
        sys.exit("ERROR: Fetched data failed validation; not recording or alerting")

    print(f"Fetched {len(rates)} rate options")
    print(format_rate_table(rates))

    history = load_history()
    old_rates = history[0]["rates"] if history else []
    quiet_days = days_since_last_email(history, now)

    emailed = False
    if rates_changed(old_rates, rates):
        print("\nRates have changed! Sending notification...")
        emailed = send_change_email(old_rates, rates, now)
    elif HEARTBEAT_DAYS > 0 and (quiet_days is None or quiet_days >= HEARTBEAT_DAYS):
        print(f"\nRates unchanged, but no email in {HEARTBEAT_DAYS}+ days. Sending check-in...")
        emailed = send_heartbeat_email(rates, now, quiet_days)
    else:
        print("\nRates unchanged, no notification needed")

    # Prepend new snapshot to history
    snapshot = {"checked_at": now.isoformat(), "rates": rates}
    if emailed:
        snapshot["emailed_at"] = now.isoformat()
    history.insert(0, snapshot)

    if MAX_HISTORY > 0 and len(history) > MAX_HISTORY:
        dropped = len(history) - MAX_HISTORY
        del history[MAX_HISTORY:]
        print(f"Dropped {dropped} snapshot(s) past the {MAX_HISTORY}-snapshot cap")

    save_history(history)


if __name__ == "__main__":
    main()
