"""All the knobs for classification live here — edit without touching code.

Rules are simple case-insensitive substring matches against the UPPERCASED
transaction narration (e.g. "UPI/SWIGGY/.../DR/249").
"""

# --------------------------------------------------------------------------
# Your accounts. 'keywords' are how a narration that refers to one of your
# other own-accounts gets recognised (used for internal-transfer detection).
# --------------------------------------------------------------------------
ACCOUNTS = {
    "axis": {
        "label": "Axis",
        "keywords": ["AXIS", "AXBK", "UTIB"],
    },
    "sbi": {
        "label": "SBI",
        "keywords": ["SBI", "SBIN", "STATE BANK"],
    },
    "kotak": {
        "label": "Kotak",
        "keywords": ["KOTAK", "KKBK"],
    },
}

# Display order of accounts in dropdowns / charts.
ACCOUNT_ORDER = ["axis", "sbi", "kotak"]

# --------------------------------------------------------------------------
# Income: salary lands as a credit into AXIS. Add your employer's narration
# text here (the company name or the text that appears on salary credits).
# --------------------------------------------------------------------------
SALARY_KEYWORDS = [
    "SALARY",
    "PAYROLL",
    "INCOMEPAY",
    "WAGES",
    "CTC",
    "NPS CREDIT",
    "TIGER ANALYTICS",   # your employer — salary credits can arrive as just the name
]

# --------------------------------------------------------------------------
# Friend (Ashwin): deposits from him are pass-through for the credit-card
# bills you pay on his behalf. Add his UPI VPAs too if known.
# --------------------------------------------------------------------------
FRIEND_KEYWORDS = [
    "ASHWIN",
    "ASHW",
    "ASHWIN KUMAR",
]
FRIEND_UPI = []  # e.g. ["ashwin@okaxis", "ashwin@ybl"]

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
# moved between your own accounts), even though the UPI text also embeds the
# other bank's name. Give names that no counterparty you pay would share.
# --------------------------------------------------------------------------
OWN_NAME_KEYWORDS = ["ROSHAN"]

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
# order matters (put more-specific categories earlier). Substring, case-folded.
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
        "RENT", "LANDLORD", "HOUSE RENT", "FLAT",
        "SRINIVAS",   # landlord (monthly room rent)
    ],
    "Family & Support": [
        "KIRAN",   # mother — monthly support sent every month
        "MOTHER", "PARENTS", "FAMILY",
    ],
    "Partner": [
        "BRUNESSA",   # partner — monthly grocery/food + personal spends
    ],
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

DEFAULT_CATEGORY = "Uncategorized"

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
# llama-3.3-70b-versatile was deprecated by Groq; qwen/qwen3.6-27b provides excellent tool calling.
GROQ_MODEL = "qwen/qwen3.6-27b"

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
MATCH_AMOUNT_TOLERANCE = 0.01    # ₹ 0.01 — transfers are exact
