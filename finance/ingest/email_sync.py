"""Automated Email Statement Ingestion Engine (Gmail & Yahoo Mail via IMAP).

Securely connects to Gmail and Yahoo Mail over SSL/IMAP using App Passwords,
discovers monthly credit card statement emails across Indian banks, extracts PDF attachments,
auto-unlocks encrypted statements using configured password profiles, and updates the finance OS.
"""

from __future__ import annotations

import email
from email.header import decode_header
import imaplib
import io
import os
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from finance import config, db
from finance.ingest import cc_pdf_parser

# Known Indian Credit Card Senders & Keywords
BANK_SENDER_DOMAINS = [
    "axisbank.com",
    "americanexpress.com",
    "aexp.com",
    "idfcfirstbank.com",
    "federalbank.co.in",
    "scapia.cards",
    "yesbank.in",
    "hdfcbank.net",
    "hdfcbank.com",
    "sbicard.com",
    "icicibank.com",
    "kotak.com",
]

CARD_KEYWORD_PATTERNS = [
    (r"indian\s*oil|axis", "Axis Bank Credit Card"),
    (r"american\s*express|amex", "American Express"),
    (r"mayura|idfc", "IDFC FIRST Credit Card"),
    (r"scapia|federal", "Scapia Federal Credit Card"),
    (r"yes_bank_elite|yes\s*bank", "YES Bank Credit Card"),
    (r"hdfc", "HDFC Bank Credit Card"),
    (r"sbi\s*card", "SBI Credit Card"),
    (r"icici", "ICICI Bank Credit Card"),
    (r"kotak", "Kotak Mahindra Credit Card"),
]

IMAP_SERVERS = {
    "gmail": {"host": "imap.gmail.com", "port": 993},
    "yahoo": {"host": "imap.mail.yahoo.com", "port": 993},
    "outlook": {"host": "outlook.office365.com", "port": 993},
}


def _decode_mime_words(s: str | bytes | None) -> str:
    if not s:
        return ""
    if isinstance(s, bytes):
        try:
            return s.decode("utf-8", errors="ignore")
        except Exception:
            return str(s)

    decoded_fragments = []
    try:
        fragments = decode_header(s)
        for fragment, encoding in fragments:
            if isinstance(fragment, bytes):
                encoding = encoding or "utf-8"
                try:
                    decoded_fragments.append(fragment.decode(encoding, errors="ignore"))
                except Exception:
                    decoded_fragments.append(fragment.decode("utf-8", errors="ignore"))
            else:
                decoded_fragments.append(str(fragment))
        return "".join(decoded_fragments)
    except Exception:
        return str(s)


def detect_card_from_meta(sender: str, subject: str, body: str = "") -> str:
    combined = f"{sender} {subject} {body}".lower()
    for pattern, card_label in CARD_KEYWORD_PATTERNS:
        if re.search(pattern, combined):
            return card_label
    return "Credit Card"


class EmailSyncClient:
    """IMAP client for fetching statements from Gmail / Yahoo Mail."""

    def __init__(
        self,
        provider: str = "gmail",
        username: Optional[str] = None,
        password: Optional[str] = None,
        custom_host: Optional[str] = None,
        custom_port: int = 993
    ):
        self.provider = provider.lower()
        self.username = username or os.getenv(f"{self.provider.upper()}_USER") or os.getenv("EMAIL_USER", "")
        self.password = password or os.getenv(f"{self.provider.upper()}_APP_PASSWORD") or os.getenv("EMAIL_APP_PASSWORD", "")
        
        # Clean whitespace from app passwords (users often copy with spaces)
        if self.password:
            self.password = self.password.replace(" ", "").strip()

        server_info = IMAP_SERVERS.get(self.provider, {"host": custom_host or "imap.gmail.com", "port": custom_port})
        self.host = custom_host or server_info["host"]
        self.port = custom_port or server_info["port"]

        self._imap: Optional[imaplib.IMAP4_SSL] = None

    def connect(self) -> Tuple[bool, str]:
        """Connect and authenticate to IMAP server."""
        if not self.username or not self.password:
            return False, f"Missing username or app password for {self.provider.capitalize()}."

        try:
            self._imap = imaplib.IMAP4_SSL(self.host, self.port)
            self._imap.login(self.username, self.password)
            return True, f"Successfully authenticated with {self.provider.capitalize()} ({self.username})."
        except imaplib.IMAP4.error as e:
            return False, f"IMAP authentication failed: {e}. Check that you generated a 16-character App Password."
        except Exception as e:
            return False, f"Connection error: {e}"

    def disconnect(self):
        if self._imap:
            try:
                self._imap.logout()
            except Exception:
                pass
            self._imap = None

    def fetch_statement_emails(
        self,
        days_back: int = 60,
        download_dir: Optional[str | Path] = None,
        folder: str = "INBOX"
    ) -> List[Dict[str, Any]]:
        """Search and extract PDF attachments from credit card statement emails."""
        if not self._imap:
            ok, msg = self.connect()
            if not ok:
                raise ConnectionError(msg)

        if download_dir is None:
            download_dir = Path("data/statements/email_downloads")
        download_dir = Path(download_dir)
        download_dir.mkdir(parents=True, exist_ok=True)

        self._imap.select(folder, readonly=True)

        since_date = (datetime.now() - timedelta(days=days_back)).strftime("%d-%b-%Y")
        
        # IMAP Search for Statement / Bank keywords
        # Using SINCE filter
        search_criteria = f'(SINCE "{since_date}")'
        status, data = self._imap.search(None, search_criteria)
        if status != "OK" or not data or not data[0]:
            return []

        mail_ids = data[0].split()
        results: List[Dict[str, Any]] = []

        # Process in reverse (most recent first)
        for m_id in reversed(mail_ids):
            try:
                status, msg_data = self._imap.fetch(m_id, "(RFC822)")
                if status != "OK" or not msg_data or not msg_data[0]:
                    continue

                raw_email = msg_data[0][1]
                msg = email.message_from_bytes(raw_email)

                sender = _decode_mime_words(msg.get("From", ""))
                subject = _decode_mime_words(msg.get("Subject", ""))
                msg_date = msg.get("Date", "")

                # Check if sender matches bank domains or subject matches statement keywords
                is_bank_sender = any(domain in sender.lower() for domain in BANK_SENDER_DOMAINS)
                is_statement_subject = bool(re.search(r"statement|e-statement|estatement|bill\s+generated|card\s+bill", subject, re.IGNORECASE))

                if not (is_bank_sender or is_statement_subject):
                    continue

                card_name = detect_card_from_meta(sender, subject)

                # Extract Attachments
                for part in msg.walk():
                    content_disp = str(part.get("Content-Disposition", ""))
                    content_type = part.get_content_type()
                    filename = part.get_filename()

                    if filename:
                        filename = _decode_mime_words(filename)

                    if ("attachment" in content_disp or content_type == "application/pdf") and filename:
                        if filename.lower().endswith(".pdf"):
                            payload = part.get_payload(decode=True)
                            if payload:
                                clean_fname = re.sub(r"[^\w\-.]", "_", filename)
                                save_name = f"{datetime.now().strftime('%Y%m')}_{card_name.replace(' ', '_')}_{clean_fname}"
                                file_path = download_dir / save_name
                                file_path.write_bytes(payload)

                                results.append({
                                    "provider": self.provider,
                                    "sender": sender,
                                    "subject": subject,
                                    "date": msg_date,
                                    "card_name": card_name,
                                    "filename": filename,
                                    "saved_path": str(file_path),
                                    "data": payload
                                })
            except Exception:
                continue

        return results


def sync_statements_from_email(
    provider: str = "gmail",
    username: Optional[str] = None,
    password: Optional[str] = None,
    pdf_passwords: Optional[List[str]] = None,
    days_back: int = 60
) -> Dict[str, Any]:
    """High-level function to sync, decrypt, parse, and save credit card statements from email."""
    client = EmailSyncClient(provider=provider, username=username, password=password)
    
    conn_ok, conn_msg = client.connect()
    if not conn_ok:
        return {
            "success": False,
            "message": conn_msg,
            "statements_saved": 0,
            "emis_saved": 0,
            "details": []
        }

    try:
        fetched_emails = client.fetch_statement_emails(days_back=days_back)
    finally:
        client.disconnect()

    if not fetched_emails:
        return {
            "success": True,
            "message": f"Connected to {provider.capitalize()} successfully. No new PDF statements found in the last {days_back} days.",
            "statements_saved": 0,
            "emis_saved": 0,
            "details": []
        }

    # Passwords to try for encrypted statements
    candidate_passwords: List[Optional[str]] = [None]
    if pdf_passwords:
        candidate_passwords.extend(pdf_passwords)
    
    # Check env for configured passwords
    env_pwds = os.getenv("PDF_PASSWORDS", "")
    if env_pwds:
        for p in env_pwds.split(","):
            p_clean = p.strip()
            if p_clean and p_clean not in candidate_passwords:
                candidate_passwords.append(p_clean)

    saved_stmts = 0
    saved_emis = 0
    details = []

    for item in fetched_emails:
        pdf_bytes = item["data"]
        file_name = item["filename"]
        suggested_card = item["card_name"]

        parsed_info = None
        parsed_txns = []
        parsed_emis = []
        parse_warning = ""

        # Try candidate passwords
        for pwd in candidate_passwords:
            try:
                info, txns, emis, warns = cc_pdf_parser.parse_cc_pdf(
                    pdf_bytes,
                    source_file=file_name,
                    card_name=suggested_card,
                    password=pwd
                )
                if info.get("total_due", 0) > 0 or info.get("statement_date") or txns or emis:
                    parsed_info = info
                    parsed_txns = txns
                    parsed_emis = emis
                    break
            except Exception as e:
                parse_warning = str(e)
                continue

        if parsed_info:
            # Save Statement & EMIs to DB
            stmt_id = db.save_cc_statement(parsed_info)
            if parsed_emis:
                db.upsert_cc_emis(parsed_emis)
                saved_emis += len(parsed_emis)
            saved_stmts += 1

            details.append({
                "card_name": parsed_info["card_name"],
                "statement_date": parsed_info["statement_date"],
                "due_date": parsed_info["due_date"],
                "total_due": parsed_info["total_due"],
                "min_due": parsed_info["min_due"],
                "emis_count": len(parsed_emis),
                "status": "✅ Parsed & Saved",
                "filename": file_name
            })
        else:
            details.append({
                "card_name": suggested_card,
                "statement_date": "-",
                "due_date": "-",
                "total_due": 0.0,
                "min_due": 0.0,
                "emis_count": 0,
                "status": f"⚠️ Encrypted or Unparseable ({parse_warning or 'Password Required'})",
                "filename": file_name
            })

    return {
        "success": True,
        "message": f"Successfully processed {len(fetched_emails)} statement attachment(s) from {provider.capitalize()}.",
        "statements_saved": saved_stmts,
        "emis_saved": saved_emis,
        "details": details
    }


def sync_all_configured_emails(
    pdf_passwords: Optional[List[str]] = None,
    days_back: int = 60
) -> Dict[str, Any]:
    """1-Click Sync across all configured email accounts (Gmail & Yahoo Mail)."""
    providers = []
    if os.getenv("GMAIL_USER") and os.getenv("GMAIL_APP_PASSWORD"):
        providers.append("gmail")
    if os.getenv("YAHOO_USER") and os.getenv("YAHOO_APP_PASSWORD"):
        providers.append("yahoo")

    if not providers:
        return {
            "success": False,
            "message": "No email accounts configured in .env. Please set GMAIL_USER/GMAIL_APP_PASSWORD or YAHOO_USER/YAHOO_APP_PASSWORD.",
            "statements_saved": 0,
            "emis_saved": 0,
            "details": []
        }

    total_saved = 0
    total_emis = 0
    all_details = []
    messages = []

    for prov in providers:
        res = sync_statements_from_email(
            provider=prov,
            pdf_passwords=pdf_passwords,
            days_back=days_back
        )
        if res["success"]:
            total_saved += res["statements_saved"]
            total_emis += res["emis_saved"]
            all_details.extend(res["details"])
            messages.append(f"{prov.capitalize()}: {res['statements_saved']} statements saved")
        else:
            messages.append(f"{prov.capitalize()} Error: {res['message']}")

    return {
        "success": True,
        "message": " | ".join(messages),
        "statements_saved": total_saved,
        "emis_saved": total_emis,
        "details": all_details
    }

