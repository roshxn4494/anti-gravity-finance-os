"""Configuration loaded from a local, ignored profile.

Personal names, employer names, counterparties, account numbers, balances and
other user-specific financial facts must live outside source control.
Copy config/profile.example.json to data/profile.json and customize it.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROFILE_PATH = Path(os.getenv("FINANCE_PROFILE_PATH", ROOT / "data" / "profile.json"))

_DEFAULT_ACCOUNTS = {
    "axis": {"label": "Axis", "keywords": ["AXIS", "AXBK", "UTIB"]},
    "sbi": {"label": "SBI", "keywords": ["SBI", "SBIN", "STATE BANK"]},
    "kotak": {"label": "Kotak", "keywords": ["KOTAK", "KKBK"]},
}
_DEFAULT_CATEGORIES = {
    "Food & Dining": ["SWIGGY", "ZOMATO", "ZEPTO", "DOMINOS", "PIZZA", "RESTAURANT", "CAFE", "FOOD"],
    "Groceries": ["BIGBASKET", "BLINKIT", "DMART", "GROCERY", "VEGETABLE", "SUPERMARKET", "MILK"],
    "Transport & Fuel": ["UBER", "RAPIDO", "OLA", "IRCTC", "RAILWAY", "METRO", "PETROL", "FUEL", "TOLL", "FASTAG"],
    "Entertainment": ["BOOKMYSHOW", "NETFLIX", "PRIME VIDEO", "SPOTIFY", "PVR", "CINEMA", "MOVIE"],
    "Shopping": ["AMAZON", "FLIPKART", "MYNTRA", "MEESHO", "AJIO", "SHOP", "STORE", "ELECTRONICS"],
    "Rent": ["RENT", "LANDLORD", "HOUSE RENT", "FLAT"],
    "Family & Support": ["MOTHER", "PARENTS", "FAMILY"],
    "Partner": [],
    "Healthcare": ["APOLLO", "PHARMEASY", "PRACTO", "MEDICINE", "PHARMACY", "HOSPITAL", "DOCTOR"],
    "Loans & EMIs": ["EMI", "LOAN", "NBFC"],
    "Utilities & Bills": ["ELECTRICITY", "WATER", "GAS", "LPG", "AIRTEL", "VODAFONE", "BSNL", "RECHARGE", "BROADBAND", "WIFI", "DTH", "BBPS"],
    "Travel": ["MAKEMYTRIP", "YATRA", "GOIBIBO", "CLEARTRIP", "FLIGHT", "AIRLINE", "OYO", "AIRBNB", "TRAVEL"],
    "Investments": ["SIP", "MUTUAL FUND", "LIC", "POLICY", "ZERODHA", "GROWW", "UPSTOX", "NPS", "FIXED DEPOSIT", "SWP"],
    "Fees & Charges": ["SERVICE CHARGE", "MAINTENANCE", "PENALTY", "CHARGES", "ATM", "DEBIT CARD", "GST", "COMMISSION"],
}

def _load_profile() -> dict:
    if not PROFILE_PATH.exists():
        return {}
    try:
        return json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Invalid finance profile: {PROFILE_PATH}: {exc}") from exc

_PROFILE = _load_profile()

ACCOUNTS = _PROFILE.get("accounts") or _DEFAULT_ACCOUNTS
ACCOUNT_ORDER = _PROFILE.get("account_order") or list(ACCOUNTS)
SALARY_KEYWORDS = [str(x).upper() for x in _PROFILE.get("salary_keywords", ["SALARY", "PAYROLL", "WAGES"])]
FRIEND_KEYWORDS = [str(x).upper() for x in _PROFILE.get("friend_keywords", [])]
FRIEND_UPI = [str(x).upper() for x in _PROFILE.get("friend_upi", [])]
OWN_NAME_KEYWORDS = [str(x).upper() for x in _PROFILE.get("own_name_keywords", [])]
CC_PAYMENT_KEYWORDS = [str(x).upper() for x in _PROFILE.get("cc_payment_keywords", ["CREDIT CA", "CC PAYMENT", "CARD PAYMENT", "CREDITCARD", "CARD BILL", "CREDIT CARD", "UPI/CREDIT"])]
INVESTMENT_KEYWORDS = [str(x).upper() for x in _PROFILE.get("investment_keywords", ["CAMS", "MUTUAL FUND", "SIP", "NPS", "LIC", "POLICY", "ZERODHA", "GROWW", "UPSTOX", "FIXED DEPOSIT", "SWP"])]

TRANSFER_KEYWORDS = ["NEFT", "RTGS", "IMPS", "FT ", "TRANSFER", "OWN ACCOUNT", "SELF", "BETWEEN ACCOUNTS"]
P2P_MIN_OCCURRENCES = 3
P2P_AMOUNT_TOLERANCE = 0.05
P2P_DAY_TOLERANCE = 7

CATEGORY_KEYWORDS = {
    str(category): [str(k).upper() for k in keywords]
    for category, keywords in (_PROFILE.get("category_keywords") or _DEFAULT_CATEGORIES).items()
}
DEFAULT_CATEGORY = "Uncategorized"

CLASSIFICATION_SPEND = "spend"
CLASSIFICATION_INCOME = "income"
CLASSIFICATION_OTHER_INCOME = "other_income"
CLASSIFICATION_INTERNAL_TRANSFER = "internal_transfer"
CLASSIFICATION_CC_PAYMENT = "cc_payment"
CLASSIFICATION_FRIEND_DEPOSIT = "friend_deposit"
CLASSIFICATION_FEE = "fee"
CLASSIFICATION_INVESTMENT = "investment"

ALL_CLASSIFICATIONS = [
    CLASSIFICATION_SPEND, CLASSIFICATION_INCOME, CLASSIFICATION_OTHER_INCOME,
    CLASSIFICATION_INTERNAL_TRANSFER, CLASSIFICATION_CC_PAYMENT,
    CLASSIFICATION_FRIEND_DEPOSIT, CLASSIFICATION_FEE, CLASSIFICATION_INVESTMENT,
]
NON_SPEND = {
    CLASSIFICATION_INCOME, CLASSIFICATION_OTHER_INCOME, CLASSIFICATION_INTERNAL_TRANSFER,
    CLASSIFICATION_CC_PAYMENT, CLASSIFICATION_FRIEND_DEPOSIT, CLASSIFICATION_INVESTMENT,
}

GROQ_MODEL = os.getenv("GROQ_MODEL", "qwen/qwen3.6-27b")
MATCH_WINDOW_INTERNAL_DAYS = 3
MATCH_WINDOW_CC_DAYS = 7
MATCH_AMOUNT_TOLERANCE = 0.01
