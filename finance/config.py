"""All the knobs for classification live here — edit without touching code.

Rules are simple case-insensitive substring matches against the UPPERCASED
transaction narration (e.g. "UPI/SWIGGY/.../DR/249").
"""
import os
from pathlib import Path

# Load .env file into environment
_env_path = Path(__file__).resolve().parent.parent / ".env"
if _env_path.exists():
    for _line in _env_path.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ[_k.strip()] = _v.strip().strip("'\"")

from . import profile

# --------------------------------------------------------------------------
# Your accounts loaded from profile. 'keywords' are how a narration that refers to one of your
# other own-accounts gets recognised (used for internal-transfer detection).
# --------------------------------------------------------------------------
ACCOUNTS = profile.get_account_configs()

# Display order of accounts in dropdowns / charts.
ACCOUNT_ORDER = list(ACCOUNTS.keys())

# --------------------------------------------------------------------------
# Income: salary keywords loaded dynamically from user profile.
# --------------------------------------------------------------------------
SALARY_KEYWORDS = profile.get_salary_keywords()

# --------------------------------------------------------------------------
# Pass-through friend/partner counterparties loaded dynamically from user profile.
# --------------------------------------------------------------------------
FRIEND_KEYWORDS = profile.get_pass_through_keywords()
FRIEND_NAME = profile.get_pass_through_name()
FRIEND_UPI = profile.get_pass_through_upi()

# --------------------------------------------------------------------------
# Credit-card bill payments (debited from your account). These are the bills
# you pay for Ashwin (or any card you don't want itemised).
# --------------------------------------------------------------------------
CC_PAYMENT_KEYWORDS = [
    "CREDIT CA",    # 'CREDIT CARD' + truncated 811:BBPS '…CREDIT CA' narrations
    "CC PAYMENT",
    "CARD PAYMENT",
    "CREDITCARD",
    "CARD BILL",
    "KOTAK CARD",
    "AXIS CARD",
    "SBI CARD",
    "AMERICAN",     # Amex bills the user owns but Ashwin uses & reimburses
    "AMEX",
    "CRED CLUB",    # CRED buy-now-pay-later the user settles for Ashwin
    "CRED/",        # Cred-app bill payments appear as CRED/… or UPI/CRED/…
    "UPI/CREDIT",
]

# --------------------------------------------------------------------------
# Investments (SIPs, fund purchases) — money that stays the user's, so it's
# classified separately and EXCLUDED from spend everywhere.
# --------------------------------------------------------------------------
INVESTMENT_KEYWORDS = [
    "CAMS",         # registrar narration prefix (CAMS-79530…)
    "INDIANESIGN",  # monthly ₹1,000 mutual-fund SIP (ACH-DR-TP ACH INDIANESIGN)
    "DSP",          # DSP Mutual Fund / DSP Finance
    "MUTUAL FUND",
    "SIP",
    "NPS",
    "LIC",
    "POLICY",
    "ZERODHA", "GROWW", "INDMONEY", "UPSTOX", "ANGEL ONE",
    "FIXED DEPOSIT",
    "PAYMENTFORFIXED",   # UPI 'PaymentForFixed…' FD bookings via IDFC First
    "PLOT",              # land/plot purchase — capital asset, not consumption
    "SWP",
]

# --------------------------------------------------------------------------
# Your name(s) as they appear in your own UPI/transfer narrations. When the
# narration names YOU as the payee/beneficiary it's a self-transfer (money
# moved between your own accounts). Loaded dynamically from user profile.
# --------------------------------------------------------------------------
OWN_NAME_KEYWORDS = profile.get_own_name_keywords()

# --------------------------------------------------------------------------
# Internal-transfer hints: a narration referencing another own-account name
# (ACCOUNTS[*].keywords) OR these generic bank-transfer words is a candidate
# internal transfer. Final pairing is by amount + time window in match.py.
# --------------------------------------------------------------------------
TRANSFER_KEYWORDS = [
    "NEFT",
    "RTGS",
    "IMPS",
    "FT ",
    "TRANSFER",
    "OWN ACCOUNT",
    "SELF",
    "BETWEEN ACCOUNTS",
]

# --------------------------------------------------------------------------
# Recurring P2P detection: same counterparty + similar amount + same-ish day
# of month, repeated, is probably a fixed payment (rent, subscription…). Such
# transactions get flagged "recurring" for review and one manual tag saves an
# override that auto-fills every future occurrence.
# --------------------------------------------------------------------------
P2P_MIN_OCCURRENCES = 3        # occurrences needed before flagging as recurring
P2P_AMOUNT_TOLERANCE = 0.05    # ±5% amount drift allowed
P2P_DAY_TOLERANCE = 7          # day-of-month must be within ±7 days

# --------------------------------------------------------------------------
# Merchant keyword → category. First category whose keyword matches wins, so
# order matters (put more-specific categories earlier).
# --------------------------------------------------------------------------
CATEGORY_KEYWORDS = {
    "Food & Dining": [
        "SWIGGY", "ZOMATO", "ZEPTO", "DOMINOS", "PIZZAHUT", "PIZZA",
        "MCDONALD", "BURGER KING", "KFC", "SUBWAY", "STARBUCKS",
        "FOOD", "RESTAURANT", "DHABA", "CHAAT", "BIRYANI", "HOTEL",
        "SWEETS", "ICE CREAM", "BASKIN", "TASTY", "CAFE",
    ],
    "Groceries": [
        "BIGBASKET", "BLINKIT", "DMART", "JIO MART", "RELIANCE FRESH",
        "GROCERY", "VEGETABLE", "FRUITS", "SUPERMARKET", "MILK",
        "MOR MARKET", "SPENCER", "BB DAILY", "FRESHCART", "FARM",
    ],
    "Transport & Fuel": [
        "UBER", "RAPIDO", "OLA", "IRCTC", "RAILWAY", "METRO", "PETROL",
        "FUEL", "IOCL", "INDIAN OIL", "HPCL", "BPCL", "SHELL",
        "PARKING", "TOLL", "NHAI", "FASTAG", "TAXI", "REDBUS", "TRAIN",
    ],
    "Entertainment": [
        "BOOKMYSHOW", "NETFLIX", "AMAZON PRIME", "PRIME VIDEO",
        "SPOTIFY", "YOUTUBE PREMIUM", "HOTSTAR", "DISNEY", "PVR",
        "CINEMA", "MOVIE", "PLAYSTATION", "STEAM", "XBOX", "GAME", "MUSIC",
    ],
    "Shopping": [
        "AMAZON", "FLIPKART", "MYNTRA", "MEESHO", "AJIO", "SNAPDEAL",
        "NYKAA", "LENSKART", "SHOP", "STORE", "APPAREL", "FOOTWEAR",
        "SHOES", "CLOTHING", "ELECTRONICS", "MOBILE", "LAPTOP",
        "FURNITURE", "WATCH", "RELIANCE RETAIL",
    ],
    "Rent": [
        "RENT", "LANDLORD", "HOUSE RENT",
    ],
    "Family & Support": [
        "MOTHER", "PARENTS", "FAMILY",
    ],
    "Partner": [],
    "Healthcare": [
        "APOLLO", "PHARMEASY", "PRACTO", "MEDICINE", "PHARMACY",
        "MEDPLUS", "NETMEDS", "1MG", "CLINIC", "DOCTOR", "DENTAL",
        "HOSPITAL", "DIAGNOSTICS", "BLOOD", "HEALTH",
    ],
    "Loans & EMIs": [
        "KISETSU", "EMI-PL", "LOAN", "NBFC", "DPLIN", "BAJAJ FINANCE", "TATA CAPITAL",
        "SPLN", "INS DEBIT",
    ],
    "Utilities & Bills": [
        "ELECTRICITY", "BESCOM", "POWER", "WATER", "GAS", "PIPED GAS",
        "LPG", "JIO", "AIRTEL", "VODAFONE", "BSNL", "POSTPAID",
        "PREPAID", "RECHARGE", "BROADBAND", "WIFI", "DTH", "TATA PLAY",
        "BBPS", "UTILITY", "BILL PAYMENT", "CITY GAS",
    ],
    "Travel": [
        "MAKEMYTRIP", "YATRA", "GOIBIBO", "CLEARTRIP", "FLIGHT",
        "AIRLINE", "AIRWAYS", "OYO", "AIRBNB", "TREEBO", "TRAVEL",
        "HOLIDAY", "TOUR", "VISA", "PASSPORT",
    ],
    "Investments": [
        "SIP", "MUTUAL FUND", "LIC", "POLICY", "PREMIUM", "ZERODHA",
        "GROWW", "INDMONEY", "UPSTOX", "ANGEL ONE", "NSE", "BSE",
        "NPS", "SSY", "FIXED DEPOSIT", "SWP",
    ],
    "Fees & Charges": [
        "SERVICE CHARGE", "MAINTENANCE", "PENALTY", "CHARGES",
        "ATM", "DEBIT CARD", "GST", "COMMISSION",
    ],
}

# Merge personal counterparty rules from user profile
_p_cats = profile.get_personal_categories()
for _cat, _kws in _p_cats.items():
    if _cat in CATEGORY_KEYWORDS and isinstance(_kws, list):
        for _kw in _kws:
            if _kw not in CATEGORY_KEYWORDS[_cat]:
                CATEGORY_KEYWORDS[_cat].append(_kw)
    elif isinstance(_kws, list):
        CATEGORY_KEYWORDS[_cat] = list(_kws)

DEFAULT_CATEGORY = "Uncategorized"

# --------------------------------------------------------------------------
# Privacy Mode (Change 25): local | minimized | cloud_ai
# --------------------------------------------------------------------------
FINANCE_PRIVACY_MODE = os.getenv("FINANCE_PRIVACY_MODE", profile.get_privacy_mode())

# Transaction classifications.
CLASSIFICATION_SPEND = "spend"
CLASSIFICATION_INCOME = "income"
CLASSIFICATION_OTHER_INCOME = "other_income"
CLASSIFICATION_INTERNAL_TRANSFER = "internal_transfer"
CLASSIFICATION_CC_PAYMENT = "cc_payment"
CLASSIFICATION_FRIEND_DEPOSIT = "friend_deposit"
CLASSIFICATION_FEE = "fee"
CLASSIFICATION_INVESTMENT = "investment"

# --------------------------------------------------------------------------
# Finance chat agent (LangGraph + Groq). Model with tool-calling support.
# The API key lives in GROQ_API_KEY (env var or .env at project root).
GROQ_MODEL = "openai/gpt-oss-120b"

ALL_CLASSIFICATIONS = [
    CLASSIFICATION_SPEND,
    CLASSIFICATION_INCOME,
    CLASSIFICATION_OTHER_INCOME,
    CLASSIFICATION_INTERNAL_TRANSFER,
    CLASSIFICATION_CC_PAYMENT,
    CLASSIFICATION_FRIEND_DEPOSIT,
    CLASSIFICATION_FEE,
    CLASSIFICATION_INVESTMENT,
]

# Classifications that never count as "spend" anywhere in the dashboard.
NON_SPEND = {
    CLASSIFICATION_INCOME,
    CLASSIFICATION_OTHER_INCOME,
    CLASSIFICATION_INTERNAL_TRANSFER,
    CLASSIFICATION_CC_PAYMENT,
    CLASSIFICATION_FRIEND_DEPOSIT,
    CLASSIFICATION_INVESTMENT,
}

# --------------------------------------------------------------------------
# Matching windows (days) for pairing transfers & CC pass-through.
# --------------------------------------------------------------------------
MATCH_WINDOW_INTERNAL_DAYS = 3   # own-account sweep out ↔ sweep in
MATCH_WINDOW_CC_DAYS = 7         # cc payment ↔ friend deposit
MATCH_AMOUNT_TOLERANCE = 1.0     # ₹ 1.00 — handles banking roundoff drift
