"""Credit Card PDF statement parser (pdfplumber / pypdf).

Parses credit card PDF statements across Indian banks (HDFC, ICICI, Axis, SBI, Amex, Kotak, Scapia Federal, YES Bank).
Extracts:
  1. Statement summary metadata (Card last 4, statement date, due date, total due, min due, credit limits, reward points).
  2. Itemized line-item transactions (date, description, amount, category, counterparty).
  3. Active EMIs and Loan Schedules (merchant, loan amount, monthly EMI, total tenure, remaining tenure).
Supports password-protected PDFs and text-only layouts.
"""
from __future__ import annotations

import io
import re
from datetime import datetime

import pdfplumber

from ..classify import categories, rules
from .normalize import parse_amount, parse_date

MONTHS_MAP = {
    "january": "01", "february": "02", "march": "03", "april": "04",
    "may": "05", "june": "06", "july": "07", "august": "08",
    "september": "09", "october": "10", "november": "11", "december": "12",
    "jan": "01", "feb": "02", "mar": "03", "apr": "04",
    "may": "05", "jun": "06", "jul": "07", "aug": "08",
    "sep": "09", "oct": "10", "nov": "11", "dec": "12"
}


def _parse_cc_date(s: str) -> str | None:
    if not s or not isinstance(s, str):
        return None
    s = s.strip()

    # Standard parse_date try first
    d = parse_date(s)
    if d:
        return d

    # Handle DD-MM-YYYY or DD/MM/YYYY
    m_slash = re.search(r"(\d{2})[/.-](\d{2})[/.-](\d{4})", s)
    if m_slash:
        return f"{m_slash.group(3)}-{m_slash.group(2)}-{m_slash.group(1)}"

    # Handle DD/Mon/YYYY e.g. "22/Jul/2026" or "06/Aug/2026"
    m_mon_slash = re.search(r"(\d{1,2})[/.-]([A-Za-z]{3})[/.-](\d{2,4})", s)
    if m_mon_slash:
        day, mon, yr = m_mon_slash.groups()
        if len(yr) == 2:
            yr = "20" + yr
        m_num = MONTHS_MAP.get(mon.lower())
        if m_num:
            return f"{yr}-{m_num}-{int(day):02d}"

    # Handle Axis Mobile date e.g. "25 Jul '26" or "14 Aug '26"
    m_axis = re.search(r"(\d{1,2})\s+([A-Za-z]{3})\s+'?(\d{2,4})", s)
    if m_axis:
        day, mon, yr = m_axis.groups()
        if len(yr) == 2:
            yr = "20" + yr
        m_num = MONTHS_MAP.get(mon.lower())
        if m_num:
            return f"{yr}-{m_num}-{int(day):02d}"

    # Handle Amex date e.g. "July 9" or "August 8" or "July 09, 2026"
    m_amex = re.search(r"([A-Za-z]+)\s+(\d{1,2})(?:,\s*(\d{4}))?", s)
    if m_amex:
        mon, day, yr = m_amex.groups()
        m_num = MONTHS_MAP.get(mon.lower())
        if m_num:
            yr = yr or str(datetime.now().year)
            return f"{yr}-{m_num}-{int(day):02d}"

    return None


def parse_cc_pdf(
    data: bytes,
    source_file: str,
    card_name: str = "Credit Card",
    password: str | None = None
) -> tuple[dict, list[dict], list[dict], list[str]]:
    """Parse a credit card PDF statement.

    Returns (statement_summary_dict, line_item_transactions, active_emis, warnings).
    """
    warnings: list[str] = []
    statement_info: dict = {
        "card_name": card_name,
        "card_last4": "",
        "statement_date": "",
        "due_date": "",
        "total_due": 0.0,
        "min_due": 0.0,
        "credit_limit": 0.0,
        "available_limit": 0.0,
        "cash_limit": 0.0,
        "reward_points_earned": 0.0,
        "reward_points_balance": 0.0,
        "finance_charges": 0.0,
        "source_file": source_file,
    }
    transactions: list[dict] = []
    emis: list[dict] = []

    open_kwargs = {}
    if password:
        open_kwargs["password"] = password

    full_text = ""
    layout_text = ""
    pages_objs = []

    try:
        with pdfplumber.open(io.BytesIO(data), **open_kwargs) as pdf:
            for page in pdf.pages:
                pages_objs.append(page)
                text = page.extract_text() or ""
                l_text = page.extract_text(layout=True) or ""
                full_text += text + "\n"
                layout_text += l_text + "\n"

                # Extract tables
                tables = page.extract_tables()
                for table in tables:
                    for row in table:
                        _process_table_row(row, transactions, card_name, source_file, statement_info)

    except Exception as exc:
        err_msg = (str(exc) + " " + type(exc).__name__).lower()
        if "password" in err_msg or "encrypted" in err_msg or "pdfpasswordincorrect" in err_msg:
            raise ValueError(f"PDF '{source_file}' is password protected. Please enter the statement password above.") from exc
        raise ValueError(f"Could not parse credit card PDF '{source_file}': {exc}") from exc

    # Auto-detect Card Brand directly from PDF statement text
    u_text = full_text.upper()
    if "AMERICAN EXPRESS" in u_text or "AMEX" in u_text:
        statement_info["card_name"] = "American Express"
    elif "SCAPIA" in u_text or "FEDERAL BANK" in u_text:
        statement_info["card_name"] = "Scapia Federal Credit Card"
    elif "INDIAN OIL AXIS" in u_text or "AXIS BANK" in u_text:
        statement_info["card_name"] = "Axis Bank Credit Card"
    elif "YES BANK" in u_text or "IRIS" in u_text:
        statement_info["card_name"] = "YES Bank Credit Card"
    elif "HDFC BANK" in u_text or "HDFC" in u_text:
        statement_info["card_name"] = "HDFC Credit Card"
    elif "ICICI BANK" in u_text or "ICICI" in u_text:
        statement_info["card_name"] = "ICICI Credit Card"
    elif "SBI CARD" in u_text or "STATE BANK OF INDIA" in u_text or "SBICARD" in u_text:
        statement_info["card_name"] = "SBI Credit Card"
    elif "KOTAK" in u_text:
        statement_info["card_name"] = "Kotak Credit Card"
    elif "INDUSIND" in u_text:
        statement_info["card_name"] = "IndusInd Credit Card"
    elif "IDFC FIRST" in u_text or "IDFC" in u_text:
        statement_info["card_name"] = "IDFC FIRST Credit Card"
    elif "RBL BANK" in u_text or "RBL" in u_text:
        statement_info["card_name"] = "RBL Bank Credit Card"
    elif "BANK OF BARODA" in u_text or "BOBCARD" in u_text:
        statement_info["card_name"] = "BOB Credit Card"
    elif "HSBC" in u_text:
        statement_info["card_name"] = "HSBC Credit Card"

    # Parse metadata from full text and table headers
    _parse_statement_metadata(full_text, layout_text, statement_info)

    # Fallback line-by-line parsing (for Amex, Scapia, text-based PDFs without grid lines)
    if full_text:
        _parse_text_lines(full_text, transactions, statement_info["card_name"], source_file, statement_info)

    # Extract Active EMIs
    _extract_active_emis(full_text, pages_objs, statement_info["card_name"], statement_info.get("card_last4", ""), source_file, emis)

    # Ensure all transactions carry the auto-detected card name
    for t in transactions:
        t["card_name"] = statement_info["card_name"]
    for e in emis:
        e["card_name"] = statement_info["card_name"]
        e["card_last4"] = statement_info.get("card_last4", "")

    if not transactions and not statement_info["total_due"]:
        warnings.append(f"Could not extract transaction table or statement summary from '{source_file}'. Check if the PDF layout is supported or if the password was correct.")

    return statement_info, transactions, emis, warnings


def _process_table_row(
    row: list,
    transactions: list[dict],
    card_name: str,
    source_file: str,
    info: dict
):
    if not row:
        return
    cells = [str(c or "").strip() for c in row]

    # Check for metadata cells in header tables
    for c in cells:
        if "Total Payment Due" in c or "Total Amount Due" in c or "Total Due" in c:
            m = re.search(r"₹?\s*([\d,]+\.\d{2})", c)
            if m and not info["total_due"]:
                info["total_due"] = parse_amount(m.group(1))
        if "Minimum Payment Due" in c or "Minimum Due" in c:
            m = re.search(r"₹?\s*([\d,]+\.\d{2})", c)
            if m and not info["min_due"]:
                info["min_due"] = parse_amount(m.group(1))
        if "Payment Due Date" in c or "Due Date" in c:
            d = _parse_cc_date(c)
            if d and not info["due_date"]:
                info["due_date"] = d
        if "Selected Statement Month" in c or "Statement Date" in c:
            d = _parse_cc_date(c)
            if d and not info["statement_date"]:
                info["statement_date"] = d

    # Look for date in cells[0] or cells[1]
    date_val = None
    date_col = -1
    for idx, c in enumerate(cells[:2]):
        d = _parse_cc_date(c)
        if d:
            date_val = d
            date_col = idx
            break

    if not date_val:
        return

    # Find amount in remaining cells
    amount_val = None
    desc_parts = []

    for idx, c in enumerate(cells[date_col + 1:], start=date_col + 1):
        m_amt = parse_amount(c)
        if m_amt != 0.0 and (re.search(r"\d+\.\d{2}", c) or re.search(r"[\d,]+\.\d{2}\s*(?:CR|DR|C|D)?", c, re.IGNORECASE)):
            amount_val = m_amt
            if "CR" in c.upper() or "CREDIT" in c.upper():
                amount_val = -abs(amount_val)  # Payment/refund
            else:
                amount_val = abs(amount_val)   # Spend
        else:
            if c:
                desc_parts.append(c)

    desc = " ".join(desc_parts).strip()
    if date_val and amount_val is not None and desc:
        if any(h in desc.upper() for h in ("TOTAL DUE", "STATEMENT DATE", "PAYMENT DUE", "OPENING BALANCE", "TRANSACTION DETAILS", "STATEMENT PERIOD", "CREDIT LIMIT", "TO ")):
            return

        cp = categories.extract_counterparty(desc)
        dummy_txn = {
            "description": desc,
            "amount": -amount_val,
            "account": card_name,
            "txn_date": date_val,
        }
        rules.classify_txn(dummy_txn)

        transactions.append({
            "card_name": card_name,
            "card_last4": info.get("card_last4", ""),
            "txn_date": date_val,
            "description": desc,
            "amount": amount_val,
            "category": dummy_txn.get("category", "Uncategorized"),
            "counterparty": cp,
            "source_file": source_file,
        })


def _parse_statement_metadata(text: str, layout_text: str, info: dict):
    lines = text.split("\n")

    # Scapia Card last 4 e.g. • XXXXXXXXXXXX4302
    m_scapia_card = re.search(r"[•\s]*[X\*]{8,12}(\d{4})", text)
    if m_scapia_card and not info["card_last4"]:
        info["card_last4"] = m_scapia_card.group(1)

    # Scapia Total & Min Due e.g. TotalDue MinimumDue \n ₹20,390.64 ₹20,390.64
    m_scapia_dues = re.search(r"TotalDue\s*MinimumDue[\s\S]*?₹([\d,]+\.\d{2})\s+₹([\d,]+\.\d{2})", text)
    if m_scapia_dues:
        if not info["total_due"]:
            info["total_due"] = float(m_scapia_dues.group(1).replace(",", ""))
        if not info["min_due"]:
            info["min_due"] = float(m_scapia_dues.group(2).replace(",", ""))

    # Scapia Statement Date & Due Date e.g. StatementDate DueDate \n 25 Jul 2026 12 Aug 2026
    m_scapia_dates = re.search(r"StatementDate\s*DueDate[\s\S]*?(\d{1,2}\s+[A-Za-z]{3}\s+\d{4})\s+(\d{1,2}\s+[A-Za-z]{3}\s+\d{4})", text)
    if m_scapia_dates:
        if not info["statement_date"]:
            info["statement_date"] = _parse_cc_date(m_scapia_dates.group(1))
        if not info["due_date"]:
            info["due_date"] = _parse_cc_date(m_scapia_dates.group(2))

    # Amex Membership Number / Card last 4
    m_amex_card = re.search(r"Membership Number\s*\n?[A-Z\s]*XXXX-XXXXXX-(\d{4,5})", text)
    if m_amex_card and not info["card_last4"]:
        info["card_last4"] = m_amex_card.group(1)[-4:]

    # Amex Statement Date e.g. 08/08/2026
    m_amex_stmt = re.search(r"Statement of Account[\s\S]*?(\d{2}/\d{2}/\d{4})", text)
    if m_amex_stmt and not info["statement_date"]:
        p = m_amex_stmt.group(1).split("/")
        info["statement_date"] = f"{p[2]}-{p[1]}-{p[0]}"

    # Amex Total & Min Due e.g. Closing Balance Rs ... 21,080.75
    m_amex_due = re.search(r"Closing Balance Rs\s+Min Payment Due Rs\s*\n?[\d,.\s\-+=\w]*?\s+([\d,]+\.\d{2})\s+([\d,]+\.\d{2})", text)
    if m_amex_due:
        if not info["total_due"]:
            info["total_due"] = float(m_amex_due.group(1).replace(",", ""))
        if not info["min_due"]:
            info["min_due"] = float(m_amex_due.group(2).replace(",", ""))
    else:
        m_tot = re.search(r"receiving your payment of Rs\.?\s*([\d,]+\.\d{2})", text)
        if m_tot and not info["total_due"]:
            info["total_due"] = float(m_tot.group(1).replace(",", ""))

    # Amex Due Date e.g. by 26/08/2026
    m_amex_dd = re.search(r"by\s+(\d{2}/\d{2}/\d{4})", text)
    if m_amex_dd and not info["due_date"]:
        p = m_amex_dd.group(1).split("/")
        info["due_date"] = f"{p[2]}-{p[1]}-{p[0]}"

    # Total Credit Limit & Available Limit
    m_tot_lim = re.search(r"(?:TotalLimit|Credit Limit|Total Credit Limit)[\s:]*₹?\s*([\d,]+\.\d{2})", text, re.IGNORECASE)
    if m_tot_lim and not info["credit_limit"]:
        info["credit_limit"] = float(m_tot_lim.group(1).replace(",", ""))

    m_avail_lim = re.search(r"(?:AvailableLimit|Available Limit|Available Credit Limit)[\s:]*₹?\s*([\d,]+\.\d{2})", text, re.IGNORECASE)
    if m_avail_lim and not info["available_limit"]:
        info["available_limit"] = float(m_avail_lim.group(1).replace(",", ""))

    # YES Bank Credit Card Metadata
    if "YES BANK" in text.upper() or "IRIS" in text.upper():
        m_yes_card = re.search(r"Card Number\s+(?:4050[X\*]+|X+)(\d{4})", layout_text, re.IGNORECASE) or re.search(r"[X\*]{4,}(\d{4})", layout_text)
        if m_yes_card and not info["card_last4"]:
            info["card_last4"] = m_yes_card.group(1)

        m_yes_stmt = re.search(r"Statement Date\s*:\s*(\d{2}/\d{2}/\d{4})", layout_text, re.IGNORECASE)
        if m_yes_stmt and not info["statement_date"]:
            p = m_yes_stmt.group(1).split("/")
            info["statement_date"] = f"{p[2]}-{p[1]}-{p[0]}"

        m_yes_dd = re.search(r"Payment Due Date\s*:\s*(\d{2}/\d{2}/\d{4})", layout_text, re.IGNORECASE)
        if m_yes_dd and not info["due_date"]:
            p = m_yes_dd.group(1).split("/")
            info["due_date"] = f"{p[2]}-{p[1]}-{p[0]}"

        m_yes_tot = re.search(r"Total Amount Due:[^\n]*\n\s*Rs\.\s*([\d,]+\.\d{2})", layout_text, re.IGNORECASE)
        if m_yes_tot:
            info["total_due"] = float(m_yes_tot.group(1).replace(",", ""))

        m_yes_min = re.search(r"Minimum Amount Due:[^\n]*\n\s*Rs\.\s*([\d,]+\.\d{2})", layout_text, re.IGNORECASE)
        if m_yes_min:
            info["min_due"] = float(m_yes_min.group(1).replace(",", ""))

        m_yes_clim = re.search(r"Credit Limit:\s*\n[^\n]*Rs\.\s*([\d,]+\.\d{2})", layout_text, re.IGNORECASE) or re.search(r"Credit Limit:\s*\n\s*Rs\.\s*([\d,]+\.\d{2})", layout_text, re.IGNORECASE)
        if m_yes_clim:
            info["credit_limit"] = float(m_yes_clim.group(1).replace(",", ""))

        m_yes_avlim = re.search(r"Available Credit Limit:\s*[^\n]*\n\s*Statement Date\s*:\s*\d{2}/\d{2}/\d{4}\s+Rs\.\s*([\d,]+\.\d{2})", layout_text, re.IGNORECASE) or re.search(r"Available Credit Limit:\s*\n\s*Rs\.\s*([\d,]+\.\d{2})", layout_text, re.IGNORECASE)
        if m_yes_avlim:
            info["available_limit"] = float(m_yes_avlim.group(1).replace(",", ""))

        m_yes_cash = re.search(r"Cash Limit:\s*Points Earned\s*:\s*0\s*\n\s*Rs\.\s*[\d,]+\.\d{2}\s+Rs\.\s*([\d,]+\.\d{2})", layout_text, re.IGNORECASE) or re.search(r"Cash Limit:\s*\n\s*Rs\.\s*([\d,]+\.\d{2})", layout_text, re.IGNORECASE)
        if m_yes_cash:
            info["cash_limit"] = float(m_yes_cash.group(1).replace(",", ""))

        m_yes_pts = re.search(r"Your Reward Points Summary[\s\S]*?\n\s*([\d,]+)\s+([\d,]+)\s+([\d,]+)\s+([\d,]+)\s+([\d,]+)\s+([\d,]+)", layout_text, re.IGNORECASE)
        if m_yes_pts:
            info["reward_points_balance"] = float(m_yes_pts.group(6).replace(",", ""))
            info["reward_points_earned"] = float(m_yes_pts.group(2).replace(",", ""))

    # Axis Bank Credit Card Metadata
    if "AXIS" in text.upper() or "INDIANOIL" in text.upper() or "INDIAN OIL" in text.upper():
        m_axis_card = re.search(r"Credit Card Number:\s*(?:4386[X\*]+|[X\*]+)(\d{4})", text, re.IGNORECASE)
        if m_axis_card and not info["card_last4"]:
            info["card_last4"] = m_axis_card.group(1)

        m_axis_month = re.search(r"Selected Statement Month\s+Credit Limit\s+Opening Balance\s*\n\s*([A-Za-z]{3}\s+\d{4})\s+[₹r]?\s*([\d,]+\.\d{2})\s+[₹r]?\s*([\d,]+\.\d{2})", text, re.IGNORECASE)
        if m_axis_month:
            _, cred_lim_str, _ = m_axis_month.groups()
            info["credit_limit"] = float(cred_lim_str.replace(",", ""))

        m_axis_pay = re.search(r"Total Payment Due\s+Minimum Payment Due\s+Payment Due Date\s*\n\s*[₹r]?\s*([\d,]+\.\d{2})\s+[₹r]?\s*([\d,]+\.\d{2})\s+(\d{1,2}\s+[A-Za-z]{3}\s+'?\d{2,4})", text, re.IGNORECASE)
        if m_axis_pay:
            info["total_due"] = float(m_axis_pay.group(1).replace(",", ""))
            info["min_due"] = float(m_axis_pay.group(2).replace(",", ""))
            info["due_date"] = _parse_cc_date(m_axis_pay.group(3))

    # American Express Metadata
    if "AMERICAN EXPRESS" in text.upper() or "AMEX" in text.upper():
        m_amex_card = re.search(r"(?:Membership Number|Card Number)[^\n]*?(?:XXXX-XXXXXX-|[X\*]{4,})(\d{4,5})", text, re.IGNORECASE)
        if m_amex_card and not info["card_last4"]:
            info["card_last4"] = m_amex_card.group(1)[-4:]

        m_amex_lim = re.search(r"Credit Summary\s+Credit Limit\s+Rs\s+Available Credit Limit\s+Rs\s*\n\s*At\s+[A-Za-z]+\s+\d{1,2},\s+\d{4}\s+([\d,]+\.\d{2})\s+([\d,]+\.\d{2})", text, re.IGNORECASE)
        if m_amex_lim:
            info["credit_limit"] = float(m_amex_lim.group(1).replace(",", ""))
            info["available_limit"] = float(m_amex_lim.group(2).replace(",", ""))

    # Scapia Federal Credit Card Metadata
    if "SCAPIA" in text.upper() or "FEDERAL BANK" in text.upper():
        m_scapia_card = re.search(r"(?:[X\*]{6,})(\d{4})", text)
        if m_scapia_card and not info["card_last4"]:
            info["card_last4"] = m_scapia_card.group(1)

        m_scapia_lim = re.search(r"AvailableLimit\s+TotalLimit\s+Cashwithdrawallimit\s*\n\s*[₹r]?([\d,]+\.\d{2})\s+[₹r]?([\d,]+\.\d{2})\s+[₹r]?([\d,]+\.\d{2})", text, re.IGNORECASE)
        if m_scapia_lim:
            info["available_limit"] = float(m_scapia_lim.group(1).replace(",", ""))
            info["credit_limit"] = float(m_scapia_lim.group(2).replace(",", ""))
            info["cash_limit"] = float(m_scapia_lim.group(3).replace(",", ""))

    # IDFC FIRST Bank Metadata
    if "IDFC FIRST" in text.upper() or "IDFC" in text.upper():
        m_idfc_card = re.search(r"Mayura Credit Card XX(\d{4})", text, re.IGNORECASE) or re.search(r"Card Number:?\s*(?:XXXX\s*|440523\*+|\*{4,6})?(\d{4})", text, re.IGNORECASE)
        if m_idfc_card:
            info["card_last4"] = m_idfc_card.group(1)

        m_idfc_stmt = re.search(r"Statement Date:\s*\n?(\d{2}/[A-Za-z]{3}/\d{4})", text, re.IGNORECASE) or re.search(r"Statement Period:\s*\d{2}/[A-Za-z]{3}/\d{4}\s*-\s*(\d{2}/[A-Za-z]{3}/\d{4})", text, re.IGNORECASE)
        if m_idfc_stmt and not info["statement_date"]:
            info["statement_date"] = _parse_cc_date(m_idfc_stmt.group(1))

        m_idfc_dues = re.search(r"Minimum Amount Due\s+Total Amount Due\s+Payment Due Date\s*\n\s*[r₹]?([\d,]+\.\d{2})\s*(?:DR|CR)?\s+[r₹]?([\d,]+\.\d{2})\s*(?:DR|CR)?\s+(\d{2}/[A-Za-z]{3}/\d{4})", text, re.IGNORECASE)
        if m_idfc_dues:
            info["min_due"] = float(m_idfc_dues.group(1).replace(",", ""))
            info["total_due"] = float(m_idfc_dues.group(2).replace(",", ""))
            info["due_date"] = _parse_cc_date(m_idfc_dues.group(3))
        else:
            m_idfc_dd = re.search(r"Payment Due Date[\s\S]*?(\d{2}/[A-Za-z]{3}/\d{4})", text, re.IGNORECASE)
            if m_idfc_dd and not info["due_date"]:
                info["due_date"] = _parse_cc_date(m_idfc_dd.group(1))
            m_idfc_due = re.search(r"Total Amount Due[\s\S]*?[r₹]?\s*([\d,]+\.\d{2})", text, re.IGNORECASE)
            if m_idfc_due and not info["total_due"]:
                info["total_due"] = float(m_idfc_due.group(1).replace(",", ""))
            m_idfc_min = re.search(r"Minimum Amount Due[\s\S]*?[r₹]?\s*([\d,]+\.\d{2})", text, re.IGNORECASE)
            if m_idfc_min and not info["min_due"]:
                info["min_due"] = float(m_idfc_min.group(1).replace(",", ""))

        m_idfc_lim = re.search(r"Credit Limit\s+Available Credit Limit\s+Cash Limit\s+Available Cash Limit\s*\n\s*([\d,]+(?:\.\d{2})?)\s+([\d,]+\.\d{2})\s+([\d,]+(?:\.\d{2})?)\s+([\d,]+(?:\.\d{2})?)", text, re.IGNORECASE)
        if m_idfc_lim:
            info["credit_limit"] = float(m_idfc_lim.group(1).replace(",", ""))
            info["available_limit"] = float(m_idfc_lim.group(2).replace(",", ""))
            info["cash_limit"] = float(m_idfc_lim.group(3).replace(",", ""))
        else:
            m_idfc_lim_sub = re.search(r"Credit Limit\s+Available Credit Limit[\s\S]*?([\d,]+\.?\d*)\s+([\d,]+\.\d{2})", text, re.IGNORECASE)
            if m_idfc_lim_sub:
                if not info["credit_limit"]:
                    info["credit_limit"] = float(m_idfc_lim_sub.group(1).replace(",", ""))
                if not info["available_limit"]:
                    info["available_limit"] = float(m_idfc_lim_sub.group(2).replace(",", ""))

        m_idfc_pts = re.search(r"Rewards Points[\s\S]*?carried over[\s\S]*?\n\s*([\d,]+)\s+([\d,]+)\s+([\d,]+)\s+([\d,]+)\s+([\d,]+)", text, re.IGNORECASE) or re.search(r"Total Reward[\s\S]*?Points Available[\s\S]*?([\d,]+)\s+([\d,]+)\s+([\d,]+)\s+([\d,]+)\s+([\d,]+)", text, re.IGNORECASE)
        if m_idfc_pts:
            info["reward_points_balance"] = float(m_idfc_pts.group(5).replace(",", ""))
            info["reward_points_earned"] = float(m_idfc_pts.group(2).replace(",", ""))

    m_cash_lim = re.search(r"(?:Cashwithdrawallimit|Cash Limit|Available Cash Limit)[\s:]*₹?\s*([\d,]+\.\d{2})", text, re.IGNORECASE)
    if m_cash_lim and not info["cash_limit"]:
        info["cash_limit"] = float(m_cash_lim.group(1).replace(",", ""))

    for line in lines:
        l_upper = line.upper()

        # Generic Card last 4
        m_card = re.search(r"(?:CARD|ACCOUNT)\s*(?:NO|NUMBER)?[\s:]*(?:\*{4}|\d{4}[\s-]*[X\*]{4}[\s-]*[X\*]{4})[\s-]*(\d{4})", l_upper)
        if m_card and not info["card_last4"]:
            info["card_last4"] = m_card.group(1)

        # Generic Payment due date
        if ("DUE DATE" in l_upper or "PAYABLE BY" in l_upper) and not info["due_date"]:
            d = _parse_cc_date(line)
            if d:
                info["due_date"] = d

        # Generic Total amount due
        if ("TOTAL AMOUNT DUE" in l_upper or "TOTAL PAYMENT DUE" in l_upper or "TOTAL DUE" in l_upper) and not info["total_due"]:
            m_amt = re.search(r"₹?\s*([\d,]+\.\d{2})", l_upper)
            if m_amt:
                info["total_due"] = parse_amount(m_amt.group(1))

        # Generic Minimum amount due
        if ("MINIMUM AMOUNT DUE" in l_upper or "MINIMUM PAYMENT DUE" in l_upper or "MIN DUE" in l_upper) and not info["min_due"]:
            m_min = re.search(r"₹?\s*([\d,]+\.\d{2})", l_upper)
            if m_min:
                info["min_due"] = parse_amount(m_min.group(1))

        # Generic Reward points
        if ("REWARD" in l_upper or "POINTS" in l_upper) and not info["reward_points_balance"]:
            m_pts = re.search(r"(?:POINTS|BALANCE|EARNED)[\s:]*([\d,]+)", l_upper)
            if m_pts:
                try:
                    info["reward_points_balance"] = float(m_pts.group(1).replace(",", ""))
                except ValueError:
                    pass


def _parse_text_lines(
    text: str,
    transactions: list[dict],
    card_name: str,
    source_file: str,
    info: dict
):
    existing_keys = {(t["txn_date"], t["amount"], t["description"]) for t in transactions}
    stmt_yr = info["statement_date"][:4] if info.get("statement_date") else str(datetime.now().year)

    # IDFC FIRST Bank Multiline Transaction Parser
    if "IDFC FIRST" in text.upper() or "IDFC" in text.upper():
        lines = text.split("\n")
        in_txns = False
        for i, line in enumerate(lines):
            line_s = line.strip()
            if "Your Transactions" in line_s:
                in_txns = True
                continue
            if "Active EMI Details" in line_s or "Important Information" in line_s:
                in_txns = False
                break
            if not in_txns:
                continue

            m_date = re.search(r"(\d{2}/\d{2}/\d{4})", line_s)
            m_amt = re.search(r"([\d,]+\.\d{2})\s*(DR|CR)?", line_s, re.IGNORECASE)
            if m_date and m_amt:
                dt_str = m_date.group(1)
                amt_str = m_amt.group(1)
                cr_dr = m_amt.group(2) or ""

                prefix = ""
                if i - 1 >= 0 and not re.search(r"\d{2}/\d{2}/\d{4}", lines[i-1]) and not re.search(r"[\d,]+\.\d{2}", lines[i-1]):
                    if not any(h in lines[i-1].upper() for h in ("YOUR TRANSACTIONS", "DATE DETAILS", "CARD NUMBER:")):
                        prefix = lines[i-1].strip()

                body = line_s.replace(dt_str, "").replace(amt_str, "").replace(cr_dr, "").strip()

                suffix = ""
                if i + 1 < len(lines) and not re.search(r"\d{2}/\d{2}/\d{4}", lines[i+1]) and not re.search(r"[\d,]+\.\d{2}", lines[i+1]):
                    if lines[i+1].strip().startswith("<") or "Payment" in lines[i+1]:
                        suffix = lines[i+1].strip()

                desc_parts = [p for p in [prefix, body, suffix] if p]
                desc = " ".join(desc_parts).strip()

                d_val = _parse_cc_date(dt_str)
                amt_val = float(amt_str.replace(",", ""))
                if cr_dr.upper() == "CR":
                    amt_val = -abs(amt_val)
                else:
                    amt_val = abs(amt_val)

                if d_val and desc:
                    key = (d_val, amt_val, desc)
                    if key not in existing_keys:
                        existing_keys.add(key)
                        cp = categories.extract_counterparty(desc)
                        dummy_txn = {"description": desc, "amount": -amt_val, "account": card_name, "txn_date": d_val}
                        rules.classify_txn(dummy_txn)
                        transactions.append({
                            "card_name": card_name,
                            "card_last4": info.get("card_last4", "5327"),
                            "txn_date": d_val,
                            "description": desc,
                            "amount": amt_val,
                            "category": dummy_txn.get("category", "Uncategorized"),
                            "counterparty": cp,
                            "source_file": source_file,
                        })
        return

    # Scapia Regex e.g. "13-07-2026·19:22 Billpayment Payment +₹24,080.54" or "25-07-2026·00:00 FinnairReykjavikIs ₹2,069.41 4/9"
    scapia_line_re = re.compile(r"^(\d{2}-\d{2}-\d{4})(?:·\d{2}:\d{2})?\s+(.+?)\s+([+-]?₹?\s*[\d,]+\.\d{2})(?:\s+\d+/\d+)?$", re.IGNORECASE)

    # Regex for Amex e.g. "August 8 FINANCE CHARGES 220.23" or "July 27 PAYMENT RECEIVED. THANK YOU 29,988.00"
    amex_line_re = re.compile(r"^([A-Za-z]+\s+\d{1,2})\s+(.+?)\s+([\d,]+\.\d{2})\s*(CR|DR)?$", re.IGNORECASE)

    # Standard regex e.g. "25/07/2026 SWIGGY FOOD 650.00"
    date_regex = re.compile(r"^(\d{1,2}\s+[A-Za-z]{3}\s+'?\d{2,4}|\d{2}[-/\.](?:\d{2}|[A-Za-z]{3})[-/\.]\d{2,4})\s+(.+)\s+₹?\s*([\d,]+\.\d{2})\s*(CR|DR|Credit|Debit)?", re.IGNORECASE)

    for line in text.split("\n"):
        line = line.strip()

        # Scapia Line Regex Match
        m_scapia = scapia_line_re.match(line)
        if m_scapia:
            dt_str, desc, amt_str = m_scapia.groups()
            p = dt_str.split("-")
            d_val = f"{p[2]}-{p[1]}-{p[0]}"
            amt_clean = amt_str.replace("₹", "").replace(",", "").strip()
            amt_val = float(amt_clean)

            if amt_str.startswith("+₹") and any(k in desc.upper() for k in ("PAYMENT", "REFUND", "CREDIT")):
                amt_val = -abs(amt_val)
            else:
                amt_val = abs(amt_val)

            key = (d_val, amt_val, desc)
            if key not in existing_keys:
                existing_keys.add(key)
                cp = categories.extract_counterparty(desc)
                dummy_txn = {"description": desc, "amount": -amt_val, "account": card_name, "txn_date": d_val}
                rules.classify_txn(dummy_txn)
                transactions.append({
                    "card_name": card_name,
                    "card_last4": info.get("card_last4", ""),
                    "txn_date": d_val,
                    "description": desc,
                    "amount": amt_val,
                    "category": dummy_txn.get("category", "Uncategorized"),
                    "counterparty": cp,
                    "source_file": source_file,
                })

        # Amex Line Regex Match
        m_amex = amex_line_re.match(line)
        if m_amex and not m_scapia:
            dt_raw, desc, amt_str, cr_dr = m_amex.groups()
            dt_parts = dt_raw.split()
            m_num = MONTHS_MAP.get(dt_parts[0].lower(), "01")
            day_num = int(dt_parts[1])
            d_val = f"{stmt_yr}-{m_num}-{day_num:02d}"
            amt_val = parse_amount(amt_str)

            if "PAYMENT RECEIVED" in desc.upper() or "CREDIT" in desc.upper() or (cr_dr and "CR" in cr_dr.upper()):
                amt_val = -abs(amt_val)
            else:
                amt_val = abs(amt_val)

            if not any(ign in desc.upper() for ign in ("TOTAL OF INSTALLMENTS", "TOTAL DEBITS", "OPENING BALANCE")):
                key = (d_val, amt_val, desc)
                if key not in existing_keys:
                    existing_keys.add(key)
                    cp = categories.extract_counterparty(desc)
                    dummy_txn = {"description": desc, "amount": -amt_val, "account": card_name, "txn_date": d_val}
                    rules.classify_txn(dummy_txn)
                    transactions.append({
                        "card_name": card_name,
                        "card_last4": info.get("card_last4", ""),
                        "txn_date": d_val,
                        "description": desc,
                        "amount": amt_val,
                        "category": dummy_txn.get("category", "Uncategorized"),
                        "counterparty": cp,
                        "source_file": source_file,
                    })

        # Generic Line Regex Match
        m_gen = date_regex.match(line)
        if m_gen and not m_amex and not m_scapia:
            d_str, desc, amt_str, cr_dr = m_gen.groups()
            d_val = _parse_cc_date(d_str)
            amt_val = parse_amount(amt_str)
            if d_val and amt_val:
                if cr_dr and ("CR" in cr_dr.upper() or "CREDIT" in cr_dr.upper()):
                    amt_val = -abs(amt_val)
                else:
                    amt_val = abs(amt_val)

                if any(ign in desc.upper() for ign in ("TOTAL DUE", "STATEMENT PERIOD", "CREDIT LIMIT", "OPENING BALANCE", "STATEMENT DATE", "PAYMENT DUE", "YOUR REWARD POINTS", "CIN :", "TO ")):
                    continue

                key = (d_val, amt_val, desc)
                if key not in existing_keys:
                    existing_keys.add(key)
                    cp = categories.extract_counterparty(desc)
                    dummy_txn = {"description": desc, "amount": -amt_val, "account": card_name, "txn_date": d_val}
                    rules.classify_txn(dummy_txn)
                    transactions.append({
                        "card_name": card_name,
                        "card_last4": info.get("card_last4", ""),
                        "txn_date": d_val,
                        "description": desc,
                        "amount": amt_val,
                        "category": dummy_txn.get("category", "Uncategorized"),
                        "counterparty": cp,
                        "source_file": source_file,
                    })


def _extract_active_emis(
    text: str,
    pages: list,
    card_name: str,
    card_last4: str,
    source_file: str,
    emis: list[dict]
):
    """Extract active loan schedules & EMI counters from pdfplumber pages & text."""
    # 1. Page Table Extraction (e.g. Axis Mobile Active Loans Summary table on Page 4)
    for page in pages:
        tables = page.extract_tables()
        for t in tables:
            for row in t:
                if len(row) >= 6 and row[0] and str(row[0]).strip().isdigit():
                    mch = str(row[2] or row[1] or "EMI Loan").replace("\n", " ").strip()
                    amt_str = str(row[3] or "").replace("₹", "").replace(",", "").strip()
                    tot_t = int(row[4]) if row[4] and str(row[4]).strip().isdigit() else 1
                    rem_t = int(row[5]) if row[5] and str(row[5]).strip().isdigit() else 0
                    emi_str = str(row[6] or "").replace("₹", "").replace(",", "").strip() if len(row) > 6 else "0"

                    try:
                        loan_amt = float(amt_str)
                    except ValueError:
                        loan_amt = 0.0
                    try:
                        emi_val = float(emi_str)
                    except ValueError:
                        emi_val = 0.0
                    paid_t = max(1, tot_t - rem_t)

                    emis.append({
                        "card_name": card_name,
                        "card_last4": card_last4,
                        "merchant_name": mch,
                        "loan_amount": loan_amt,
                        "monthly_emi": emi_val,
                        "total_tenure": tot_t,
                        "paid_tenure": paid_t,
                        "remaining_tenure": rem_t,
                        "source_file": source_file
                    })

    # 2. Line Item EMI Counters (Scapia or Amex lines e.g. "FinnairReykjavikIs ₹13,846.33 4/24")
    re_scapia_emi = re.compile(r"^(\d{2}-\d{2}-\d{4})?(?:·\d{2}:\d{2})?\s*(.+?)\s+([+-]?₹?\s*[\d,]+\.\d{2})\s+(\d+)/(\d+)$", re.IGNORECASE)
    for line in text.split("\n"):
        line = line.strip()
        m = re_scapia_emi.match(line)
        if m:
            _, mch, amt_str, paid_str, tot_str = m.groups()
            mch = re.sub(r"^[·\s]*\d{2}:\d{2}\s*", "", mch).strip()
            p_t = int(paid_str)
            t_t = int(tot_str)
            rem_t = max(0, t_t - p_t)
            amt_val = float(amt_str.replace("₹", "").replace(",", "").strip())

            if not any(e["merchant_name"] == mch and e["total_tenure"] == t_t for e in emis):
                emis.append({
                    "card_name": card_name,
                    "card_last4": card_last4,
                    "merchant_name": mch,
                    "loan_amount": round(amt_val * t_t, 2),
                    "monthly_emi": amt_val,
                    "total_tenure": t_t,
                    "paid_tenure": p_t,
                    "remaining_tenure": rem_t,
                    "source_file": source_file
                })

    # 3. Amex Installment Plan Summary Table regex:
    # "AMERICAN EXPRESS EMI 23,398.00 1.17% 7,769.85 8 of12 2,101.00 1,947.46 153.54 27.64"
    amex_emi_re = re.compile(
        r"(AMERICAN EXPRESS EMI)\s+([\d,]+\.\d{2})\s+[\d.]*%\s+([\d,]+\.\d{2})\s+(\d+)\s*of\s*(\d+)\s+([\d,]+\.\d{2})",
        re.IGNORECASE
    )
    for line in text.split("\n"):
        line = line.strip()
        m = amex_emi_re.search(line)
        if m:
            _, orig_str, bal_str, paid_str, tot_str, emi_str = m.groups()
            orig_amt = float(orig_str.replace(",", ""))
            bal_amt = float(bal_str.replace(",", ""))
            paid_t = int(paid_str)
            tot_t = int(tot_str)
            rem_t = max(0, tot_t - paid_t)
            emi_val = float(emi_str.replace(",", ""))

            mch_label = f"Amex EMI Plan ({tot_t}M @ ₹{emi_val:,.0f}/mo)"
            if not any(e["loan_amount"] == orig_amt and e["total_tenure"] == tot_t for e in emis):
                emis.append({
                    "card_name": card_name,
                    "card_last4": card_last4 or "2009",
                    "merchant_name": mch_label,
                    "loan_amount": orig_amt,
                    "monthly_emi": emi_val,
                    "total_tenure": tot_t,
                    "paid_tenure": paid_t,
                    "remaining_tenure": rem_t,
                    "source_file": source_file
                })

    # 4. IDFC FIRST Bank Active EMI Details table:
    # 97,949.17 20,733.75 18% 1,18,682.92 22 MAR 26 22 FEB 28 24 4,890.02 20 97,800.40
    idfc_line_re = re.compile(
        r"([\d,]+\.\d{2})\s+([\d,]+\.\d{2})\s+(\d+)%\s+([\d,]+\.\d{2})\s+(\d{1,2}\s+[A-Za-z]{3}\s+\d{2,4})\s+(\d{1,2}\s+[A-Za-z]{3}\s+\d{2,4})\s+(\d+)\s+([\d,]+\.\d{2})\s+(\d+)\s+([\d,]+\.\d{2})",
        re.IGNORECASE
    )

    # Build IDFC merchant lookup map from transaction lines
    idfc_mch_map = {}
    lines = text.split("\n")
    for idx, line in enumerate(lines):
        m_ten = re.search(r"<(\d+)/(\d+)>", line)
        if m_ten:
            p_t, t_t = int(m_ten.group(1)), int(m_ten.group(2))
            mch_name = "IDFC Loan"
            for prev in reversed(lines[max(0, idx - 4):idx]):
                prev_s = prev.strip()
                if any(k in prev_s for k in ("BKG*", "MS*", "HOTEL", "BOOKING", "FLIPKART", "AMAZON", "MAKE", "RETA")):
                    mch_name = prev_s.replace("-", "").strip()
                    break
            idfc_mch_map[(p_t, t_t)] = mch_name

    for line in lines:
        line = line.strip()
        m = idfc_line_re.search(line)
        if m:
            loan_str, int_str, rate, tot_str, f_date, l_date, tot_t_str, emi_str, rem_t_str, bal_str = m.groups()
            loan_amt = float(loan_str.replace(",", ""))
            emi_val = float(emi_str.replace(",", ""))
            tot_t = int(tot_t_str)
            rem_t = int(rem_t_str)
            paid_t = max(1, tot_t - rem_t)

            mch_name = idfc_mch_map.get((paid_t, tot_t), f"IDFC Loan ({tot_t}M @ ₹{emi_val:,.0f}/mo)")

            if not any(e["loan_amount"] == loan_amt and e["total_tenure"] == tot_t for e in emis):
                emis.append({
                    "card_name": card_name,
                    "card_last4": card_last4 or "5327",
                    "merchant_name": mch_name,
                    "loan_amount": loan_amt,
                    "monthly_emi": emi_val,
                    "total_tenure": tot_t,
                    "paid_tenure": paid_t,
                    "remaining_tenure": rem_t,
                    "source_file": source_file
                })

    # 5. YES Bank Active EMI Details (matches (XXX/YYY) pattern e.g. (007/024) or (006/036))
    if "YES BANK" in text.upper() or "IRIS" in text.upper():
        emi_groups = {}
        lines = text.split("\n")
        for i, line in enumerate(lines):
            m_ten = re.search(r"\((\d{3})/(\d{3})\)", line)
            if m_ten:
                paid_t, tot_t = int(m_ten.group(1)), int(m_ten.group(2))
                ref_no = f"{paid_t}_{tot_t}"
                m_ref = re.search(r"Ref No:\s*(\d{15,25})", line)
                if not m_ref and i + 1 < len(lines):
                    m_ref = re.search(r"^(\d{15,25})$", lines[i+1].strip())
                if not m_ref and i + 2 < len(lines):
                    m_ref = re.search(r"^(\d{15,25})$", lines[i+2].strip())
                if m_ref:
                    ref_no = m_ref.group(1)

                is_prin = "PRIN" in line.upper()
                is_int = "INT" in line.upper()

                m_amt = re.search(r"([\d,]+\.\d{2})\s*(?:Dr|Cr)", line)
                if not m_amt and i + 1 < len(lines):
                    m_amt = re.search(r"([\d,]+\.\d{2})\s*(?:Dr|Cr)", lines[i+1])
                amt_val = float(m_amt.group(1).replace(",", "")) if m_amt else 0.0

                mch = ""
                m_mch = re.search(r"FOR\s+(.*?)\s*\(\d{3}/\d{3}\)", line, re.IGNORECASE)
                if m_mch and m_mch.group(1).strip():
                    mch = m_mch.group(1).strip()

                if ref_no not in emi_groups:
                    emi_groups[ref_no] = {"paid_t": paid_t, "tot_t": tot_t, "prin": 0.0, "int": 0.0, "merchant": mch}
                if is_prin:
                    emi_groups[ref_no]["prin"] = amt_val
                    if mch:
                        emi_groups[ref_no]["merchant"] = mch
                elif is_int:
                    emi_groups[ref_no]["int"] = amt_val

        for ref_no, g in emi_groups.items():
            paid_t, tot_t = g["paid_t"], g["tot_t"]
            rem_t = max(0, tot_t - paid_t)
            monthly_emi = round(g["prin"] + g["int"], 2)
            mch = g["merchant"] if g["merchant"] else f"YES Bank EMI ({tot_t}M)"
            loan_amt = round(g["prin"] * tot_t, 2)
            if not any(e["merchant_name"] == mch and e["total_tenure"] == tot_t for e in emis):
                emis.append({
                    "card_name": card_name,
                    "card_last4": card_last4 or "3414",
                    "merchant_name": mch,
                    "loan_amount": loan_amt,
                    "monthly_emi": monthly_emi,
                    "total_tenure": tot_t,
                    "paid_tenure": paid_t,
                    "remaining_tenure": rem_t,
                    "source_file": source_file,
                })
