"""Security and privacy helpers used by the application boundary.""" 
from __future__ import annotations

import html
import os
from enum import Enum
from typing import Any

class PrivacyMode(str, Enum):
    LOCAL = "local"
    MINIMIZED = "minimized"
    CLOUD_AI = "cloud_ai"

def privacy_mode() -> PrivacyMode:
    raw = os.getenv("FINANCE_PRIVACY_MODE", PrivacyMode.LOCAL.value).strip().lower()
    try:
        return PrivacyMode(raw)
    except ValueError:
        return PrivacyMode.LOCAL

def cloud_ai_allowed() -> bool:
    return privacy_mode() == PrivacyMode.CLOUD_AI

def escape_html(value: Any) -> str:
    """Escape untrusted values before interpolation into HTML."""
    return html.escape("" if value is None else str(value), quote=True)

def redact_account_number(value: Any) -> str:
    """Keep only the last four characters of an account/card identifier."""
    raw = "".join(ch for ch in str(value or "") if ch.isalnum())
    return f"••••{raw[-4:]}" if raw else ""

def require_local_mode_for_raw_financial_data() -> None:
    """Fail closed when a caller attempts cloud AI without explicit opt-in."""
    if not cloud_ai_allowed():
        raise PermissionError(
            "Cloud AI is disabled. Set FINANCE_PRIVACY_MODE=cloud_ai to explicitly opt in."
        )
