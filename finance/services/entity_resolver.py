"""Entity resolution service for Finance OS (Change 5).

Maps fragmented, abbreviated merchant narrations, UPI handles, and counterparty strings
to canonical entities with confidence scoring and role categorization.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from .. import db


@dataclass
class ResolvedEntity:
    id: str
    canonical_name: str
    entity_type: str  # merchant, employer, person, lender, bank, utility, investment_provider
    confidence: float
    category: str
    classification: str
    matched_alias: str
    evidence: str


# Standard pre-seeded Indian ecosystem entities
DEFAULT_ENTITIES: list[dict[str, Any]] = [
    {
        "id": "ent_swiggy",
        "canonical_name": "Swiggy",
        "entity_type": "merchant",
        "aliases": ["SWIGGY", "BUNDL", "SWIGGY INSTAMART", "SWIGGY DINE"],
        "default_category": "Food & Dining",
        "default_classification": "spend",
    },
    {
        "id": "ent_zomato",
        "canonical_name": "Zomato",
        "entity_type": "merchant",
        "aliases": ["ZOMATO", "ZOMATO LIMITED", "ZOMATO MEDIA"],
        "default_category": "Food & Dining",
        "default_classification": "spend",
    },
    {
        "id": "ent_zepto",
        "canonical_name": "Zepto",
        "entity_type": "merchant",
        "aliases": ["ZEPTO", "KIRANAKART"],
        "default_category": "Food & Dining",
        "default_classification": "spend",
    },
    {
        "id": "ent_bigbasket",
        "canonical_name": "BigBasket",
        "entity_type": "merchant",
        "aliases": ["BIGBASKET", "INNOVATIVE RETAIL", "BB DAILY", "SUPERMARKET GROCERY"],
        "default_category": "Groceries",
        "default_classification": "spend",
    },
    {
        "id": "ent_blinkit",
        "canonical_name": "Blinkit",
        "entity_type": "merchant",
        "aliases": ["BLINKIT", "GROFERS", "COMMERCE TECHNOLOGIES"],
        "default_category": "Groceries",
        "default_classification": "spend",
    },
    {
        "id": "ent_uber",
        "canonical_name": "Uber",
        "entity_type": "merchant",
        "aliases": ["UBER", "UBER INDIA", "UBER BV"],
        "default_category": "Transport & Fuel",
        "default_classification": "spend",
    },
    {
        "id": "ent_ola",
        "canonical_name": "Ola",
        "entity_type": "merchant",
        "aliases": ["OLA", "ANI TECHNOLOGIES", "OLA CABS"],
        "default_category": "Transport & Fuel",
        "default_classification": "spend",
    },
    {
        "id": "ent_amazon",
        "canonical_name": "Amazon",
        "entity_type": "merchant",
        "aliases": ["AMAZON", "AMZN", "AMAZON PAY", "AMAZON RETAIL", "AMAZON SELLER", "AMAZON.IN"],
        "default_category": "Shopping",
        "default_classification": "spend",
    },
    {
        "id": "ent_flipkart",
        "canonical_name": "Flipkart",
        "entity_type": "merchant",
        "aliases": ["FLIPKART", "FLIPKART INTERNET"],
        "default_category": "Shopping",
        "default_classification": "spend",
    },
    {
        "id": "ent_netflix",
        "canonical_name": "Netflix",
        "entity_type": "merchant",
        "aliases": ["NETFLIX", "NETFLIX ENTERTAINMENT"],
        "default_category": "Entertainment",
        "default_classification": "spend",
    },
    {
        "id": "ent_spotify",
        "canonical_name": "Spotify",
        "entity_type": "merchant",
        "aliases": ["SPOTIFY", "SPOTIFY INDIA"],
        "default_category": "Entertainment",
        "default_classification": "spend",
    },
    {
        "id": "ent_cams",
        "canonical_name": "CAMS Mutual Fund",
        "entity_type": "investment_provider",
        "aliases": ["CAMS", "CAMSONLINE", "COMPUTER AGE"],
        "default_category": "Investments",
        "default_classification": "investment",
    },
    {
        "id": "ent_zerodha",
        "canonical_name": "Zerodha",
        "entity_type": "investment_provider",
        "aliases": ["ZERODHA", "ZERODHA BROKING"],
        "default_category": "Investments",
        "default_classification": "investment",
    },
    {
        "id": "ent_groww",
        "canonical_name": "Groww",
        "entity_type": "investment_provider",
        "aliases": ["GROWW", "NEXTBILLION"],
        "default_category": "Investments",
        "default_classification": "investment",
    },
    {
        "id": "ent_kisetsu",
        "canonical_name": "Credit Saison / Kisetsu",
        "entity_type": "lender",
        "aliases": ["KISETSU", "SAISON", "CREDIT SAISON"],
        "default_category": "Loans & EMIs",
        "default_classification": "spend",
    },
    {
        "id": "ent_pharmeasy",
        "canonical_name": "PharmEasy",
        "entity_type": "merchant",
        "aliases": ["PHARMEASY", "API HOLDINGS", "THYROCARE"],
        "default_category": "Healthcare",
        "default_classification": "spend",
    },
    {
        "id": "ent_apollo",
        "canonical_name": "Apollo Pharmacy",
        "entity_type": "merchant",
        "aliases": ["APOLLO", "APOLLO PHARMACY", "APOLLO 247"],
        "default_category": "Healthcare",
        "default_classification": "spend",
    },
]


class EntityResolver:
    def __init__(self):
        self._entities: dict[str, dict[str, Any]] = {}
        self._alias_index: list[tuple[str, str]] = []  # (alias_upper, entity_id)
        self.load()

    def load(self) -> None:
        """Loads entities from DB and defaults."""
        self._entities.clear()
        self._alias_index.clear()

        # Seed defaults
        for ent in DEFAULT_ENTITIES:
            eid = ent["id"]
            self._entities[eid] = dict(ent)

        # Load from SQLite if available
        try:
            db_df = db.load_entities()
            for _, r in db_df.iterrows():
                eid = str(r["id"])
                aliases = []
                if r.get("aliases_json"):
                    try:
                        aliases = json.loads(str(r["aliases_json"]))
                    except Exception:
                        aliases = []
                self._entities[eid] = {
                    "id": eid,
                    "canonical_name": str(r["canonical_name"]),
                    "entity_type": str(r["entity_type"]),
                    "aliases": aliases,
                    "default_category": str(r.get("default_category") or "Uncategorized"),
                    "default_classification": str(r.get("default_classification") or "spend"),
                }
        except Exception:
            pass

        # Build alias index sorted by descending alias length (longest match wins)
        all_pairs = []
        for eid, ent in self._entities.items():
            aliases = ent.get("aliases", [])
            cname = ent.get("canonical_name", "")
            if cname:
                all_pairs.append((cname.upper(), eid))
            for a in aliases:
                all_pairs.append((str(a).upper(), eid))

        # Sort by longest alias first
        all_pairs.sort(key=lambda p: len(p[0]), reverse=True)
        self._alias_index = all_pairs

    def seed_db(self) -> None:
        """Persists default entities into database."""
        for ent in DEFAULT_ENTITIES:
            db.upsert_entity(ent)
        self.load()

    def resolve(self, description: str, counterparty: str | None = None) -> ResolvedEntity | None:
        """Resolves raw transaction narration or counterparty to canonical entity."""
        targets = [t for t in [counterparty, description] if t]
        if not targets:
            return None

        combined_upper = " ".join(targets).upper()

        for alias, eid in self._alias_index:
            # Word boundary regex for clean token matching
            pattern = r"(?:^|[^A-Z0-9])" + re.escape(alias) + r"(?:$|[^A-Z0-9])"
            if re.search(pattern, combined_upper):
                ent = self._entities[eid]
                return ResolvedEntity(
                    id=eid,
                    canonical_name=ent["canonical_name"],
                    entity_type=ent.get("entity_type", "merchant"),
                    confidence=0.95 if alias in (counterparty or "").upper() else 0.85,
                    category=ent.get("default_category", "Uncategorized"),
                    classification=ent.get("default_classification", "spend"),
                    matched_alias=alias,
                    evidence=f"Resolved to {ent['canonical_name']} via alias '{alias}'"
                )

        return None


# Global singleton instance
_resolver: EntityResolver | None = None


def get_entity_resolver() -> EntityResolver:
    global _resolver
    if _resolver is None:
        _resolver = EntityResolver()
    return _resolver
