"""Synthetic statements covering every classification case.

Three months (Apr–Jun 2026) for Axis, one month (Jun) for SBI and Kotak.
Each bank uses a different CSV column layout to exercise the flexible parser.
"""
from __future__ import annotations

# Axis:  Txn Date, Value Date, Description, Ref, Withdrawal, Deposit, Balance
# SBI:   Date, Value Date, Description, Chq/Ref, Withdrawal, Deposit, Closing
# Kotak: Transaction Date, Transaction Type, Narration, Debit, Credit, Balance

AXIS_HEADER = ("Txn Date,Value Date,Description,Ref No./Cheque No.,"
               "Withdrawal Amt.,Deposit Amt.,Balance")
SBI_HEADER = ("Date,Value Date,Description,Chq/Ref Number,"
              "Withdrawal Amt,Deposit Amt,Closing Balance")
KOTAK_HEADER = "Transaction Date,Transaction Type,Narration,Debit,Credit,Balance"


def _csv(header: str, rows: list[tuple]) -> str:
    lines = [header]
    for r in rows:
        lines.append(",".join(str(c) for c in r))
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------
# Axis — one month of: salary, rent (P2P recurring), spends, + June extras
# --------------------------------------------------------------------------

def axis_month(month: str, extra: bool = False) -> str:
    rows = [
        (f"01-{month}-2026", f"01-{month}-2026", "INCOMEPAY SALARY CREDIT",
         "-", "", "85000.00", "185000.00"),
        (f"05-{month}-2026", f"05-{month}-2026", "UPI/SWIGGY/Swiggy Restaurants Pvt Ltd",
         "-", "249.00", "", "184751.00"),
        (f"06-{month}-2026", f"06-{month}-2026", "UPI/BIGBASKET/Online Grocery",
         "-", "1200.00", "", "183551.00"),
        (f"08-{month}-2026", f"08-{month}-2026", "UPI/UBER India Pvt Ltd",
         "-", "340.00", "", "183211.00"),
        (f"10-{month}-2026", f"10-{month}-2026", "UPI/AMAZON PAY/Amazon Retail",
         "-", "2500.00", "", "180711.00"),
        (f"12-{month}-2026", f"12-{month}-2026", "UPI/P2P/9494012345@ybl/DR",
         "-", "15000.00", "", "165711.00"),
        (f"20-{month}-2026", f"20-{month}-2026", "UPI/ELECTRICITY BSES/Utility Bill",
         "-", "1800.00", "", "163911.00"),
    ]
    if extra:
        rows += [
            ("02-06-2026", "02-06-2026", "FT/20260702/NEFT/Axis to SBI/SELF",
             "-", "20000.00", "", "165000.00"),
            ("03-06-2026", "03-06-2026", "UPI/SELF/Axis to Kotak",
             "-", "15000.00", "", "150000.00"),
            ("15-06-2026", "15-06-2026", "ATM WITHDRAWAL",
             "-", "5000.00", "", "145000.00"),
            ("16-06-2026", "16-06-2026", "ACH-DR-KISETSU16062026 CAMS SIP",
             "-", "5592.00", "", "139408.00"),
        ]
    return _csv(AXIS_HEADER, rows)


def sbi_june() -> str:
    rows = [
        ("02-06-2026", "02-06-2026", "NEFT/AXIS BANK/TO SELF/CR", "-", "",
         "20000.00", "20000.00"),
        ("07-06-2026", "07-06-2026", "UPI/DMART/DR", "-", "850.00", "",
         "19150.00"),
        ("25-06-2026", "25-06-2026", "UPI/ZOMATO/DR", "-", "450.00", "",
         "18700.00"),
    ]
    return _csv(SBI_HEADER, rows)


def kotak_june() -> str:
    rows = [
        ("03-06-2026", "NEFT", "NEFT/AXIS/TO SELF/CR", "", "15000.00", "25000.00"),
        ("09-06-2026", "UPI", "UPI/ASHWIN KUMAR/CR", "", "12000.00", "37000.00"),
        ("10-06-2026", "CC", "KOTAK CREDIT CARD PAYMENT/CC/DR", "12000.00", "", "25000.00"),
        ("18-06-2026", "UPI", "UPI/PHARMEASY/DR", "600.00", "", "24400.00"),
        ("22-06-2026", "UPI", "UPI/REFUND/AMAZON/CR", "", "200.00", "24600.00"),
    ]
    return _csv(KOTAK_HEADER, rows)


def sbi_real_format() -> str:
    """A statement in the REAL SBI netbanking export layout: account-holder
    preamble, a 'Date,Details,Ref No/Cheque No,Debit,Credit,Balance' header,
    and narrations wrapped across two lines (quoted newlines). Used only for
    auto-detection + parsing checks, not the KPI math."""
    return (
        '"Mr. ROSHAN RAMKRISHNA RAI\nronaldoroshan@yahoo.co.in",'
        '"State Bank of India  \nTIVIM SIRCAIM",,,,\n'
        'Date,Details,Ref No/Cheque No,Debit,Credit,Balance\n'
        '12/02/2026," WDL TFR   UPI/DR/165418541736/Swiggy/ICIC/swiggystor\n'
        ' /NO REM   0097693162093 AT 05777 TIVIM SIRCAIM BRANCH",,240.00,,845.96\n'
    )


def all_files():
    """[(filename, csv_text, account)] for every sample statement."""
    files = []
    for month, extra in (("04", False), ("05", False), ("06", True)):
        files.append((f"axis_{month}_2026.csv", axis_month(month, extra), "axis"))
    files.append(("sbi_06_2026.csv", sbi_june(), "sbi"))
    files.append(("kotak_06_2026.csv", kotak_june(), "kotak"))
    return files


# Hand-computed expectations for June 2026 (see run_tests.py).
EXPECTED_JUNE_SPEND = 22989.0   # 21089 (axis) + 1300 (sbi) + 600 (kotak)
EXPECTED_JUNE_INCOME = 85000.0
RENT_COUNTERPARTY = "9494012345"
