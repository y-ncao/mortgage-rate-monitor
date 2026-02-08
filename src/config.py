import os

# OptimalBlue widget IDs (SFCU)
CLIENT_ID = "363137353031"
USER_ID = "38363530393031"
FORM_ID = "36323431"

# API endpoints
API_BASE = "https://quickquote-consumer.optimalblue.com"
SEARCH_URL = f"{API_BASE}/api/search/GetResults"

# Loan parameters (select fields as strings, currency fields as ints)
LOAN_PARAMS = {
    "occupancy": "2",          # Primary Residence
    "propertyType": "115",     # Single Family
    "loanPurpose": "112",      # Refinance
    "loanAmount": 2249000,
    "estimatedValue": 2900000,
    "state": "59",             # California
    "zipcode": "94404",
    "creditScore": "780",
}

# Products to track (substring match against product type names)
TRACKED_PRODUCTS = ["30 Yr Fixed", "7 Year ARM"]

# Email settings
GMAIL_USER = os.environ.get("GMAIL_USER", "")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "")
ALERT_EMAIL = os.environ.get("ALERT_EMAIL", "yancao.eng@gmail.com")

# Data file path
DATA_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "last_rates.json")
