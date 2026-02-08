#!/usr/bin/env python3
"""Fetch SFCU mortgage rates and send email alerts on changes."""

import json
import smtplib
import sys
from datetime import datetime, timezone
from email.mime.text import MIMEText
from pathlib import Path

import requests

from config import (
    ALERT_EMAIL,
    CLIENT_ID,
    DATA_FILE,
    FORM_ID,
    GMAIL_APP_PASSWORD,
    GMAIL_USER,
    LOAN_PARAMS,
    SEARCH_URL,
    TRACKED_PRODUCTS,
    USER_ID,
)


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
        products = pt.get("products", {}).get("$values", [])
        for prod in products:
            rates.append({
                "product": name,
                "rate": prod.get("rate"),
                "apr": prod.get("apr"),
                "monthly_payment": prod.get("monthlyPayments"),
                "points": prod.get("discounts", 0),
                "price": prod.get("price"),
            })

    return rates


def load_last_rates():
    """Load the last known rates from disk."""
    path = Path(DATA_FILE)
    if not path.exists():
        return {"rates": [], "last_checked": None}
    with open(path) as f:
        return json.load(f)


def save_rates(rates_data):
    """Save rates to disk."""
    path = Path(DATA_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(rates_data, f, indent=2)
    print(f"Saved rates to {path}")


def rates_changed(old_rates, new_rates):
    """Check if the best (lowest-points) rate for each product changed."""
    if not old_rates:
        return True

    def best_by_product(rates):
        best = {}
        for r in rates:
            p = r["product"]
            if p not in best or r.get("points", 99) < best[p].get("points", 99):
                best[p] = r
        return best

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


def format_rate_table(rates, label="Current"):
    """Format rates as a readable text table."""
    lines = [f"\n{label} Rates:"]
    lines.append("-" * 75)
    lines.append(f"{'Product':<30} {'Rate':>7} {'APR':>7} {'Payment':>12} {'Points':>7}")
    lines.append("-" * 75)
    for r in sorted(rates, key=lambda x: (x["product"], x.get("points", 0))):
        rate = f"{r['rate']:.3f}%" if r.get("rate") is not None else "N/A"
        apr = f"{r['apr']:.3f}%" if r.get("apr") is not None else "N/A"
        payment = f"${r['monthly_payment']:,.2f}" if r.get("monthly_payment") is not None else "N/A"
        points = f"{r['points']:.1f}" if r.get("points") is not None else "N/A"
        lines.append(f"{r['product']:<30} {rate:>7} {apr:>7} {payment:>12} {points:>7}")
    lines.append("-" * 75)
    return "\n".join(lines)


def send_email(old_rates, new_rates):
    """Send rate change alert via Gmail SMTP."""
    if not GMAIL_USER or not GMAIL_APP_PASSWORD:
        print("Email credentials not configured, skipping email notification")
        print("Set GMAIL_USER and GMAIL_APP_PASSWORD environment variables")
        return

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    subject = f"SFCU Mortgage Rate Change - {now}"

    body = "SFCU Mortgage Rate Change Detected!\n"
    body += f"Checked at: {now}\n"

    if old_rates:
        body += format_rate_table(old_rates, "Previous")
    body += format_rate_table(new_rates, "Current")

    if old_rates:
        def best_by_product(rates):
            best = {}
            for r in rates:
                p = r["product"]
                if p not in best or r.get("points", 99) < best[p].get("points", 99):
                    best[p] = r
            return best

        old_best = best_by_product(old_rates)
        new_best = best_by_product(new_rates)
        body += "\n\nChanges (best rate per product):"
        for product in sorted(new_best.keys()):
            new = new_best[product]
            old = old_best.get(product)
            if old:
                rate_diff = (new.get("rate") or 0) - (old.get("rate") or 0)
                direction = "UP" if rate_diff > 0 else "DOWN"
                body += f"\n  {product}: {old.get('rate')}% -> {new.get('rate')}% ({direction} {abs(rate_diff):.3f}%)"
            else:
                body += f"\n  {product}: NEW"

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = GMAIL_USER
    msg["To"] = ALERT_EMAIL

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        server.send_message(msg)
    print(f"Email sent to {ALERT_EMAIL}")


def main():
    print(f"Checking SFCU mortgage rates at {datetime.now(timezone.utc).isoformat()}")

    rates = fetch_rates()
    if not rates:
        print("ERROR: Failed to fetch any matching rates")
        sys.exit(1)

    print(f"Fetched {len(rates)} rate options")
    print(format_rate_table(rates))

    last_data = load_last_rates()
    old_rates = last_data.get("rates", [])

    if rates_changed(old_rates, rates):
        print("\nRates have changed! Sending notification...")
        send_email(old_rates, rates)
    else:
        print("\nRates unchanged, no notification needed")

    save_rates({
        "rates": rates,
        "last_checked": datetime.now(timezone.utc).isoformat(),
    })


if __name__ == "__main__":
    main()
