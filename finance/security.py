"""Security and privacy hardening utilities for Finance OS.

Covers:
1. Account identifier masking & redaction (Change 26)
2. Untrusted text sanitization & HTML escaping (Change 26)
3. Privacy Mode management: LOCAL, MINIMIZED, CLOUD_AI (Change 25)
"""
from __future__ import annotations

import html
import re
from enum import Enum
from typing import Any

from . import profile


class PrivacyMode(str, Enum):
    LOCAL = "local"
    MINIMIZED = "minimized"
    CLOUD_AI = "cloud_ai"


def get_current_privacy_mode() -> PrivacyMode:
    mode_str = profile.get_privacy_mode()
    try:
        return PrivacyMode(mode_str)
    except ValueError:
        return PrivacyMode.MINIMIZED


def is_cloud_ai_allowed() -> bool:
    """Returns True if the current privacy mode permits cloud model inference."""
    return get_current_privacy_mode() != PrivacyMode.LOCAL


def sanitize_html(content: Any) -> str:
    """Safely escapes user or financial content before interpolation into HTML templates."""
    if content is None:
        return ""
    return html.escape(str(content), quote=True)


def mask_account_identifier(identifier: str | None, visible_digits: int = 4) -> str:
    """Masks sensitive account numbers or card numbers, displaying only trailing digits.
    
    Examples:
        '123456789012' -> '•••• 9012'
        '9788' -> '•••• 9788'
        'roshan@okaxis' -> 'r••••n@okaxis'
    """
    if not identifier:
        return ""
    s = str(identifier).strip()
    if not s:
        return ""

    # Check for UPI handle
    if "@" in s:
        handle, _, domain = s.partition("@")
        if len(handle) <= 2:
            masked_handle = handle[0] + "•" if handle else "••"
        else:
            masked_handle = handle[0] + "•" * (len(handle) - 2) + handle[-1]
        return f"{masked_handle}@{domain}"

    # Numeric account or card string
    digits = re.sub(r"\D", "", s)
    if len(digits) >= visible_digits:
        last = digits[-visible_digits:]
        return f"•••• {last}"
    
    return f"•••• {s}"


def minimize_prompt_context(text: str) -> str:
    """Redacts full numeric account strings from context before transmitting to external AI."""
    # Mask 10 to 18 digit account numbers
    redacted = re.sub(r"\b(\d{6,14})(\d{4})\b", r"•••• \2", text)
    return redacted
