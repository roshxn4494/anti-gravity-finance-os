"""Classify each transaction: income / internal transfer / pass-through / spend.

Rules are applied in order, first match wins (see config for the keyword sets):
  1. fee              — debit matching fee keywords
  2. income           — credit matching salary keywords
  3. friend_deposit   — credit from Ashwin
  4. cc_payment       — debit paying a credit-card bill (incl. Amex Ashwin uses)
  5. internal_transfer— debit/credit referencing another of your own accounts
  6. investment       — debit buying a fund/SIP (money stays yours, not spend)
  7. spend            — remaining debits, categorized by merchant
  8. other_income     — remaining credits (refunds, interest)
A saved override (by counterparty) always takes precedence.
"""
from __future__ import annotations

from collections import defaultdict

from .. import config
from . import categories


def _has_any(text: str, keywords: list[str]) -> bool:
    t_upper = (text or "").upper()
    return any(str(kw).upper() in t_upper for kw in keywords)


def _has_own_other_account(text: str, current_account: str) -> bool:
    for acct_key, acct in config.ACCOUNTS.items():
        if acct_key == current_account:
            continue
        if _has_any(text, acct["keywords"]):
            return True
    return False


def _is_self_transfer(desc: str, account: str) -> bool:
    """True when the narration moves your *own* money between your own accounts.

    UPI narrations always embed the recipient's bank name, so a bare own-bank
    keyword (SBI / State Bank / UTIB) can't be trusted on UPI — that would
    mislabel payments to friends whose bank is SBI as self-transfers. For UPI we
    rely on self-markers only: SWEEP, TO SELF / OWN ACCOUNT, or your own name
    appearing as the counterparty. The own-bank check is kept for non-UPI
    channels (NEFT/IMPS/FT) where the bank name *is* the beneficiary.
    """
    up = (desc or "").upper()
    if "SWEEP" in up:
        return True
    if "AC XFR" in up:   # Kotak 811 sub-ledger moves ("Ac xfr from gl 12048 to…")
        return True
    if "SELF" in up and _has_any(up, config.TRANSFER_KEYWORDS):
        return True
    if _has_any(up, ("OWN ACCOUNT", "OWN ACCT", "BETWEEN ACCOUNTS")):
        return True
    if _has_any(up, config.OWN_NAME_KEYWORDS):
        return True
    if "UPI/" not in up and _has_own_other_account(up, account):
        return True
    return False


def classify_txn(txn: dict, overrides: dict | None = None) -> None:
    """In-place: fill counterparty, classification, category, flags."""
    overrides = overrides or {}
    desc = (txn.get("description") or "").upper()
    cp = categories.extract_counterparty(txn.get("description"))
    txn["counterparty"] = cp
    amount = txn.get("amount", 0.0)
    account = txn.get("account", "")
    is_credit = amount > 0
    is_debit = amount < 0

    # 0. Saved manual override wins (keyed by counterparty).
    if cp:
        ov = overrides.get(f"counterparty:{cp}")
        if ov:
            txn["classification"] = ov["classification"]
            txn["category"] = ov["category"]
            return

    fee_kws = config.CATEGORY_KEYWORDS.get("Fees & Charges", [])

    # 1. Fees & charges
    if is_debit and _has_any(desc, fee_kws):
        txn["classification"] = config.CLASSIFICATION_FEE
        txn["category"] = "Fees & Charges"
        return

    # 2. Salary income
    if is_credit and _has_any(desc, config.SALARY_KEYWORDS):
        txn["classification"] = config.CLASSIFICATION_INCOME
        txn["category"] = "Salary"
        return

    # 3. Ashwin's deposits
    friend_hit = _has_any(desc, config.FRIEND_KEYWORDS) or cp in config.FRIEND_UPI
    if is_credit and friend_hit:
        txn["classification"] = config.CLASSIFICATION_FRIEND_DEPOSIT
        txn["category"] = "Ashwin"
        return

    # 4. Credit-card bill payments
    if is_debit and _has_any(desc, config.CC_PAYMENT_KEYWORDS):
        txn["classification"] = config.CLASSIFICATION_CC_PAYMENT
        txn["category"] = "Credit Card"
        return

    # 5. Internal transfers between your own accounts
    if _is_self_transfer(desc, account):
        txn["classification"] = config.CLASSIFICATION_INTERNAL_TRANSFER
        txn["category"] = "Internal Transfer"
        return

    # 6. Investments (SIPs / fund purchases) — money that stays the user's, so
    #    excluded from spend to keep the dashboard reflecting real consumption.
    if is_debit and _has_any(desc, config.INVESTMENT_KEYWORDS):
        txn["classification"] = config.CLASSIFICATION_INVESTMENT
        txn["category"] = "Investments"
        return

    # 7. Spend
    if is_debit:
        txn["classification"] = config.CLASSIFICATION_SPEND
        cat = categories.categorize(desc)
        txn["category"] = cat or config.DEFAULT_CATEGORY
        if categories.is_p2p(desc, cp):
            txn["flags"] = _add_flag(txn.get("flags"), "p2p")
        return

    # 7. Other income (refunds, interest)
    txn["classification"] = config.CLASSIFICATION_OTHER_INCOME
    cat = categories.categorize(desc)
    txn["category"] = cat or "Other Income"


def _add_flag(existing: str | float | None, flag: str) -> str:
    # DB NULLs come back from pandas as NaN — treat as "no flags yet".
    if existing is None or (isinstance(existing, float) and existing != existing):
        existing = ""
    flags = set(str(existing).split(","))
    flags.discard("")
    flags.add(flag)
    return ",".join(sorted(flags))


def detect_recurring(txns: list[dict]) -> None:
    """Flag uncategorized spends that repeat ~monthly to the same counterparty.

    Sets flags += 'recurring' so the review tab can surface them for a one-time
    manual tag (which then becomes an override that auto-fills every occurrence).
    """
    groups: dict[str, list[dict]] = defaultdict(list)
    for t in txns:
        if (t.get("classification") == config.CLASSIFICATION_SPEND
                and t.get("category") == config.DEFAULT_CATEGORY
                and t.get("counterparty")):
            groups[t["counterparty"]].append(t)

    for grp in groups.values():
        if len(grp) < config.P2P_MIN_OCCURRENCES:
            continue
        for t in grp:
            matches = _recurring_neighbors(t, grp)
            if matches >= config.P2P_MIN_OCCURRENCES - 1:
                t["flags"] = _add_flag(t.get("flags"), "recurring")


def _recurring_neighbors(txn: dict, grp: list[dict]) -> int:
    dom = int(txn["txn_date"][8:10])
    amt = abs(txn["amount"])
    count = 0
    for o in grp:
        if o is txn:
            continue
        o_dom = int(o["txn_date"][8:10])
        d = abs(dom - o_dom)
        d = min(d, 30 - d)  # handle month-end wrap
        if d > config.P2P_DAY_TOLERANCE:
            continue
        o_amt = abs(o["amount"])
        if abs(o_amt - amt) > amt * config.P2P_AMOUNT_TOLERANCE:
            continue
        count += 1
    return count
