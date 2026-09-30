"""User profile management for Finance OS.

Decouples personal identity, employer keywords, counterparty names, and custom
categorization rules from application source code.
Reads from `data/profile.json` (gitignored), with fallback to `data/user_config.yaml`
and clean generic defaults.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

PROFILE_PATH_ENV = "FINANCE_PROFILE_PATH"
DEFAULT_PROFILE_PATH = Path(__file__).resolve().parent.parent / "data" / "profile.json"
LEGACY_YAML_PATH = Path(__file__).resolve().parent.parent / "data" / "user_config.yaml"

_DEFAULT_PROFILE: dict[str, Any] = {
    "user_name": "User",
    "privacy_mode": "minimized",  # local | minimized | cloud_ai
    "own_name_keywords": ["ROSHAN"],  # fallback to preserve existing test datasets
    "salary_keywords": [
        "SALARY",
        "PAYROLL",
        "INCOMEPAY",
        "WAGES",
        "CTC",
        "NPS CREDIT",
        "TIGER ANALYTICS",
    ],
    "pass_through": {
        "name": "Ashwin",
        "keywords": ["ASHWIN", "ASHW", "ASHWIN KUMAR"],
        "upi_vpas": [],
    },
    "accounts": {
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
    },
    "personal_categories": {
        "Rent": ["RENT", "LANDLORD"],
        "Family & Support": ["MOTHER", "PARENTS", "FAMILY"],
        "Partner": [],
    },
    "custom_rules": [],
}

_cached_profile: dict[str, Any] | None = None


def get_profile_path() -> Path:
    custom = os.getenv(PROFILE_PATH_ENV)
    if custom:
        return Path(custom)
    return DEFAULT_PROFILE_PATH


def load_profile(force_reload: bool = False) -> dict[str, Any]:
    global _cached_profile
    if _cached_profile is not None and not force_reload:
        return _cached_profile

    profile = dict(_DEFAULT_PROFILE)
    path = get_profile_path()

    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                if isinstance(loaded, dict):
                    profile.update(loaded)
        except Exception:
            pass
    elif LEGACY_YAML_PATH.exists():
        try:
            import yaml
            with open(LEGACY_YAML_PATH, "r", encoding="utf-8") as f:
                loaded = yaml.safe_load(f)
                if isinstance(loaded, dict):
                    if "own_name_keywords" in loaded:
                        profile["own_name_keywords"] = loaded["own_name_keywords"]
                    if "personal_categories" in loaded:
                        profile["personal_categories"] = loaded["personal_categories"]
                    if "privacy_mode" in loaded:
                        profile["privacy_mode"] = loaded["privacy_mode"]
        except Exception:
            pass

    _cached_profile = profile
    return profile


def save_profile(profile_data: dict[str, Any]) -> None:
    global _cached_profile
    path = get_profile_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(profile_data, f, indent=2)
    _cached_profile = profile_data


def get_user_name() -> str:
    return load_profile().get("user_name", "User")


def get_privacy_mode() -> str:
    env_mode = os.getenv("FINANCE_PRIVACY_MODE")
    if env_mode:
        return env_mode.lower().strip()
    return load_profile().get("privacy_mode", "minimized").lower().strip()


def get_own_name_keywords() -> list[str]:
    return load_profile().get("own_name_keywords", ["ROSHAN"])


def get_salary_keywords() -> list[str]:
    return load_profile().get("salary_keywords", _DEFAULT_PROFILE["salary_keywords"])


def get_pass_through_keywords() -> list[str]:
    pt = load_profile().get("pass_through", {})
    if isinstance(pt, dict):
        return pt.get("keywords", ["ASHWIN", "ASHW", "ASHWIN KUMAR"])
    return ["ASHWIN", "ASHW", "ASHWIN KUMAR"]


def get_pass_through_name() -> str:
    pt = load_profile().get("pass_through", {})
    if isinstance(pt, dict):
        return pt.get("name", "Ashwin")
    return "Ashwin"


def get_pass_through_upi() -> list[str]:
    pt = load_profile().get("pass_through", {})
    if isinstance(pt, dict):
        return pt.get("upi_vpas", [])
    return []


def get_account_configs() -> dict[str, Any]:
    return load_profile().get("accounts", _DEFAULT_PROFILE["accounts"])


def get_personal_categories() -> dict[str, list[str]]:
    return load_profile().get("personal_categories", _DEFAULT_PROFILE["personal_categories"])


def get_pdf_passwords() -> list[str]:
    """Retrieve PDF unlock passwords from user profile and PDF_PASSWORDS env var (deduplicated)."""
    prof_pwds = load_profile().get("pdf_passwords", [])
    if isinstance(prof_pwds, str):
        prof_pwds = [p.strip() for p in prof_pwds.split(",") if p.strip()]
    elif not isinstance(prof_pwds, list):
        prof_pwds = []
    
    env_str = os.getenv("PDF_PASSWORDS", "")
    env_pwds = [p.strip() for p in env_str.split(",") if p.strip()]
    
    combined = []
    for p in prof_pwds + env_pwds:
        if p and p not in combined:
            combined.append(p)
    return combined
