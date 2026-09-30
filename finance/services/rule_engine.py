"""Layered classification pipeline and database-driven rule engine (Changes 6 & 7).

Evaluates transactions against:
1. Exact manual overrides (highest priority)
2. Database-driven classification rules (sorted by priority)
3. Canonical Entity Resolver
4. Configured heuristics
5. Confidence gating (routes low confidence to Review Queue)
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from .. import config, db
from .entity_resolver import get_entity_resolver, ResolvedEntity


@dataclass
class ClassificationResult:
    classification: str
    category: str
    confidence: float
    classifier: str  # 'override' | 'db_rule' | 'entity' | 'heuristic' | 'fallback'
    rule_id: str | None
    evidence: str
    requires_review: bool = False


# Pre-seeded default DB rules
DEFAULT_DB_RULES = [
    {
        "id": "rule_salary_income",
        "name": "Salary Credit",
        "priority": 10,
        "scope": "global",
        "condition_type": "substring",
        "condition_value": "SALARY",
        "classification": config.CLASSIFICATION_INCOME,
        "category": "Salary",
        "confidence": 0.99,
        "enabled": 1,
    },
    {
        "id": "rule_rent_payment",
        "name": "Rent Debit",
        "priority": 20,
        "scope": "global",
        "condition_type": "substring",
        "condition_value": "RENT",
        "classification": config.CLASSIFICATION_SPEND,
        "category": "Rent",
        "confidence": 0.95,
    },
    {
        "id": "rule_electricity_bills",
        "name": "Electricity & Power Utility",
        "priority": 25,
        "scope": "global",
        "condition_type": "substring",
        "condition_value": "ELECTRICITY",
        "classification": config.CLASSIFICATION_SPEND,
        "category": "Utilities & Bills",
        "confidence": 0.95,
    },
    {
        "id": "rule_atm_withdrawal",
        "name": "ATM Cash Withdrawal Fee / Debit",
        "priority": 30,
        "scope": "global",
        "condition_type": "substring",
        "condition_value": "ATM",
        "classification": config.CLASSIFICATION_FEE,
        "category": "Fees & Charges",
        "confidence": 0.90,
    },
]


class RuleEngine:
    def __init__(self):
        self.resolver = get_entity_resolver()
        self._rules: list[dict[str, Any]] = []
        self.load_rules()

    def load_rules(self) -> None:
        """Loads enabled rules from database sorted by priority."""
        self._rules = []
        try:
            df = db.load_classification_rules(enabled_only=True)
            for _, r in df.iterrows():
                self._rules.append(r.to_dict())
        except Exception:
            self._rules = list(DEFAULT_DB_RULES)

    def seed_defaults(self) -> None:
        """Seeds default rules into SQLite."""
        for r in DEFAULT_DB_RULES:
            db.upsert_classification_rule(r)
        self.load_rules()

    def classify(
        self,
        description: str,
        amount: float,
        account: str,
        counterparty: str | None = None,
        overrides: dict | None = None,
    ) -> ClassificationResult:
        desc_upper = (description or "").upper()
        cp = counterparty or ""
        is_credit = amount > 0
        is_debit = amount < 0

        # 1. Manual Overrides Check
        if overrides:
            rule_key = f"counterparty:{cp.lower()}"
            if rule_key in overrides:
                ov = overrides[rule_key]
                return ClassificationResult(
                    classification=ov.get("classification", config.CLASSIFICATION_SPEND),
                    category=ov.get("category", "Uncategorized"),
                    confidence=1.0,
                    classifier="override",
                    rule_id=f"override:{cp}",
                    evidence=f"User manual override for counterparty '{cp}'",
                    requires_review=False,
                )

        # 2. Database-Driven Rules
        for r in self._rules:
            cond_type = r.get("condition_type")
            cond_val = str(r.get("condition_value") or "").upper()
            rule_id = str(r.get("id"))
            matched = False

            if cond_type == "substring":
                if cond_val in desc_upper or (cp and cond_val in cp.upper()):
                    matched = True
            elif cond_type == "regex":
                try:
                    if re.search(cond_val, desc_upper, re.IGNORECASE):
                        matched = True
                except Exception:
                    pass
            elif cond_type == "amount_range":
                try:
                    min_a, max_a = [float(x) for x in cond_val.split(":")]
                    if min_a <= abs(amount) <= max_a:
                        matched = True
                except Exception:
                    pass

            if matched:
                return ClassificationResult(
                    classification=r["classification"],
                    category=r["category"],
                    confidence=float(r.get("confidence", 0.95)),
                    classifier="db_rule",
                    rule_id=rule_id,
                    evidence=f"Matched DB rule '{r.get('name')}' ({cond_type}='{cond_val}')",
                    requires_review=False,
                )

        # 3. Entity Resolution
        resolved = self.resolver.resolve(description, counterparty=cp)
        if resolved:
            return ClassificationResult(
                classification=resolved.classification,
                category=resolved.category,
                confidence=resolved.confidence,
                classifier="entity",
                rule_id=resolved.id,
                evidence=resolved.evidence,
                requires_review=resolved.confidence < 0.6,
            )

        # 4. Standard Heuristics (preserving existing domain knowledge)
        # Salary
        if is_credit and any(k in desc_upper for k in config.SALARY_KEYWORDS):
            return ClassificationResult(
                classification=config.CLASSIFICATION_INCOME,
                category="Salary",
                confidence=0.98,
                classifier="heuristic",
                rule_id="heuristic_salary",
                evidence="Matched salary keywords in description",
            )

        # Pass-through friend deposit
        if is_credit and any(k in desc_upper for k in config.FRIEND_KEYWORDS):
            return ClassificationResult(
                classification=config.CLASSIFICATION_FRIEND_DEPOSIT,
                category="Family & Support",
                confidence=0.95,
                classifier="heuristic",
                rule_id="heuristic_friend_deposit",
                evidence=f"Matched pass-through friend keyword '{config.FRIEND_NAME}'",
            )

        # Credit card payments
        if is_debit and any(k in desc_upper for k in config.CC_PAYMENT_KEYWORDS):
            return ClassificationResult(
                classification=config.CLASSIFICATION_CC_PAYMENT,
                category="Loans & EMIs",
                confidence=0.92,
                classifier="heuristic",
                rule_id="heuristic_cc_payment",
                evidence="Matched credit card bill payment narration keywords",
            )

        # Internal transfers
        is_self = "SELF" in desc_upper or "OWN ACCOUNT" in desc_upper or any(k in desc_upper for k in config.OWN_NAME_KEYWORDS)
        if is_self:
            return ClassificationResult(
                classification=config.CLASSIFICATION_INTERNAL_TRANSFER,
                category="Transfer",
                confidence=0.90,
                classifier="heuristic",
                rule_id="heuristic_internal_transfer",
                evidence="Self-transfer indicators detected in narration",
            )

        # Category keyword match for spend
        if is_debit:
            for cat, keywords in config.CATEGORY_KEYWORDS.items():
                if any(kw in desc_upper for kw in keywords):
                    return ClassificationResult(
                        classification=config.CLASSIFICATION_SPEND,
                        category=cat,
                        confidence=0.85,
                        classifier="heuristic",
                        rule_id=f"cat_keyword_{cat}",
                        evidence=f"Matched category keyword in '{cat}'",
                    )
            # Default spend
            return ClassificationResult(
                classification=config.CLASSIFICATION_SPEND,
                category=config.DEFAULT_CATEGORY,
                confidence=0.55,
                classifier="fallback",
                rule_id=None,
                evidence="Default debit categorization without explicit match",
                requires_review=True,
            )

        # Default credit
        return ClassificationResult(
            classification=config.CLASSIFICATION_OTHER_INCOME,
            category="Other Income",
            confidence=0.60,
            classifier="fallback",
            rule_id=None,
            evidence="Default credit categorization",
            requires_review=True,
        )


_rule_engine: RuleEngine | None = None


def get_rule_engine() -> RuleEngine:
    global _rule_engine
    if _rule_engine is None:
        _rule_engine = RuleEngine()
    return _rule_engine
