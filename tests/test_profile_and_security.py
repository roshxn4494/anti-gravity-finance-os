"""Unit tests for user profile decoupling, privacy modes, and security hardening (Changes 1, 25, 26)."""
from __future__ import annotations

import os
from pathlib import Path
from finance import profile, security
from finance.security import PrivacyMode


def test_profile_loading():
    p = profile.load_profile(force_reload=True)
    assert isinstance(p, dict)
    assert "user_name" in p
    assert "privacy_mode" in p

    # Dynamic getters
    user_name = profile.get_user_name()
    assert isinstance(user_name, str)

    own_kws = profile.get_own_name_keywords()
    assert isinstance(own_kws, list) and len(own_kws) > 0

    sal_kws = profile.get_salary_keywords()
    assert isinstance(sal_kws, list) and "SALARY" in sal_kws

    pt_name = profile.get_pass_through_name()
    assert isinstance(pt_name, str)


def test_security_masking():
    # Mask card numbers / bank account numbers
    assert security.mask_account_identifier("123456789012") == "•••• 9012"
    assert security.mask_account_identifier("9788") == "•••• 9788"
    assert security.mask_account_identifier("5327") == "•••• 5327"
    assert security.mask_account_identifier("") == ""

    # Mask UPI handle
    masked_upi = security.mask_account_identifier("roshan@okaxis")
    assert "@okaxis" in masked_upi
    assert "•" in masked_upi


def test_security_html_sanitization():
    unsafe_input = "<script>alert('xss')</script><b>swiggy</b>"
    clean = security.sanitize_html(unsafe_input)
    assert "<script>" not in clean
    assert "&lt;script&gt;" in clean
    assert "&lt;b&gt;" in clean


def test_privacy_modes():
    # Test LOCAL mode
    os.environ["FINANCE_PRIVACY_MODE"] = "local"
    assert security.get_current_privacy_mode() == PrivacyMode.LOCAL
    assert security.is_cloud_ai_allowed() is False

    # Test CLOUD_AI mode
    os.environ["FINANCE_PRIVACY_MODE"] = "cloud_ai"
    assert security.get_current_privacy_mode() == PrivacyMode.CLOUD_AI
    assert security.is_cloud_ai_allowed() is True

    # Reset
    os.environ.pop("FINANCE_PRIVACY_MODE", None)
