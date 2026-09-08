import os

# OptimalBlue widget IDs (SFCU)
CLIENT_ID = "363137353031"
USER_ID = "38363530393031"
FORM_ID = "36323431"

# API endpoints
API_BASE = "https://quickquote-consumer.optimalblue.com"
SEARCH_URL = f"{API_BASE}/api/search/GetResults"


def _required(name):
    """Read a required env var, failing with a message that says how to set it."""
    try:
        return os.environ[name]
    except KeyError:
        raise SystemExit(
            f"Missing required environment variable {name}.\n"
            f"In CI, set it under Settings > Secrets and variables > Actions > Variables.\n"
            f"Locally, export it before running. See README.md > Configuration."
        ) from None


# Loan parameters (select fields as strings, currency fields as ints)
# Loan amount, estimated value, state, and zipcode are read from env vars
# so they can be configured via GitHub Actions variables.
LOAN_PARAMS = {
    "occupancy": "2",          # Primary Residence
    "propertyType": "115",     # Single Family
    "loanPurpose": "112",      # Refinance
    "loanAmount": int(_required("LOAN_AMOUNT")),
    "estimatedValue": int(_required("ESTIMATED_VALUE")),
    "state": _required("STATE"),
    "zipcode": _required("ZIPCODE"),
    "creditScore": "780",
}

# Products to track (substring match against product type names)
TRACKED_PRODUCTS = ["30 Yr Fixed", "7 Year ARM"]

# Email settings
GMAIL_USER = os.environ.get("GMAIL_USER", "")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "")
ALERT_EMAIL = os.environ.get("ALERT_EMAIL", "")

# Timezone used for timestamps in emails. Named rather than a fixed offset so
# the PST/PDT switch is handled automatically.
DISPLAY_TIMEZONE = "America/Los_Angeles"

# Cap on stored daily snapshots, so the history file stops growing forever.
# 400 is a little over a year of daily checks.
MAX_HISTORY = int(os.environ.get("MAX_HISTORY", "400"))

# Send a check-in email if no email has gone out in this many days, so that
# silence means "rates held steady" rather than "the monitor died".
# Set to 0 to disable.
HEARTBEAT_DAYS = int(os.environ.get("HEARTBEAT_DAYS", "7"))

# Data file path
DATA_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "last_rates.json")
