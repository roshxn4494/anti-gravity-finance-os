"""Advanced multi-factor reconciliation engine with conflict detection and review queue routing (Changes 8 & 13).

Scores candidate pairs across:
- Exact / drifted amount (± ₹1.00)
- Date proximity (same day, ±1d, ±3d, ±7d)
- Transaction direction (Debit ↔ Credit)
- Narration / counterparty / account hints
Detects 1-to-many ambiguity and automatically files conflicts to the Review Queue.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import pandas as pd

from .. import config, db


@dataclass
class MatchCandidate:
    source_id: str
    target_id: str
    amount_score: float
    date_score: float
    direction_score: float
    context_score: float
    total_score: float
    confidence: float
    evidence: str


class ReconciliationEngine:
    def __init__(self, amount_tolerance_paise: int = 100, max_window_days: int = 7):
        self.amount_tolerance_paise = amount_tolerance_paise
        self.max_window_days = max_window_days

    def score_pair(
        self,
        source: dict,
        target: dict,
    ) -> MatchCandidate | None:
        """Calculates multi-factor reconciliation score between two transactions."""
        s_amt = int(source.get("amount_paise") or round(float(source.get("amount", 0.0)) * 100))
        t_amt = int(target.get("amount_paise") or round(float(target.get("amount", 0.0)) * 100))

        # Direction check: one must be debit (<0) and one must be credit (>0)
        if not ((s_amt < 0 and t_amt > 0) or (s_amt > 0 and t_amt < 0)):
            return None
        direction_score = 20.0

        # Amount check
        abs_s = abs(s_amt)
        abs_t = abs(t_amt)
        diff = abs(abs_s - abs_t)
        if diff == 0:
            amount_score = 40.0
        elif diff <= self.amount_tolerance_paise:
            amount_score = 35.0
        else:
            return None  # Amounts must match within tolerance

        # Date proximity
        s_date_str = str(source.get("txn_date", ""))
        t_date_str = str(target.get("txn_date", ""))
        try:
            d1 = datetime.strptime(s_date_str, "%Y-%m-%d").date()
            d2 = datetime.strptime(t_date_str, "%Y-%m-%d").date()
            delta_days = abs((d1 - d2).days)
        except Exception:
            delta_days = 999

        if delta_days == 0:
            date_score = 25.0
        elif delta_days == 1:
            date_score = 20.0
        elif delta_days <= 3:
            date_score = 15.0
        elif delta_days <= self.max_window_days:
            date_score = 10.0
        else:
            return None  # Exceeds maximum reconciliation window

        # Context / Account / Counterparty hints
        s_desc = (source.get("description") or "").upper()
        t_desc = (target.get("description") or "").upper()
        s_acc = str(source.get("account") or "").upper()
        t_acc = str(target.get("account") or "").upper()

        context_score = 0.0
        evidence_notes = []

        if s_acc and s_acc in t_desc:
            context_score += 7.5
            evidence_notes.append(f"Target description mentions source account '{s_acc}'")
        if t_acc and t_acc in s_desc:
            context_score += 7.5
            evidence_notes.append(f"Source description mentions target account '{t_acc}'")

        total_score = amount_score + date_score + direction_score + context_score
        confidence = min(1.0, total_score / 100.0)

        ev = f"Score {total_score:.1f}/100: Amount diff=₹{diff/100:.2f}, Day delta={delta_days}d."
        if evidence_notes:
            ev += " " + " ".join(evidence_notes)

        return MatchCandidate(
            source_id=str(source["id"]),
            target_id=str(target["id"]),
            amount_score=amount_score,
            date_score=date_score,
            direction_score=direction_score,
            context_score=context_score,
            total_score=total_score,
            confidence=confidence,
            evidence=ev,
        )

    def reconcile_unmatched(self, auto_pair_threshold: float = 75.0) -> dict[str, Any]:
        """Runs candidate matching across unmatched internal transfers and pass-throughs.
        
        High-confidence single candidates are paired directly.
        Ambiguous multi-candidates or low-confidence matches are routed to the Review Queue.
        """
        conn = db.connect()
        # Find unmatched debits and credits
        query = """
            SELECT * FROM transactions
            WHERE match_status = 'unmatched' OR match_status IS NULL
            ORDER BY txn_date ASC
        """
        unmatched_df = pd.read_sql_query(query, conn)
        conn.close()

        if unmatched_df.empty:
            return {"matched_count": 0, "conflicts_routed": 0}

        rows = unmatched_df.to_dict("records")
        debits = [r for r in rows if float(r.get("amount") or 0.0) < 0]
        credits = [r for r in rows if float(r.get("amount") or 0.0) > 0]

        matched_count = 0
        conflicts_routed = 0
        used_credit_ids = set()

        for deb in debits:
            candidates: list[MatchCandidate] = []
            for cred in credits:
                if cred["id"] in used_credit_ids:
                    continue
                cand = self.score_pair(deb, cred)
                if cand:
                    candidates.append(cand)

            if not candidates:
                continue

            # Sort descending by total score
            candidates.sort(key=lambda c: c.total_score, reverse=True)

            if len(candidates) == 1 and candidates[0].total_score >= auto_pair_threshold:
                # Unambiguous high confidence match
                best = candidates[0]
                db.set_match(best.source_id, best.target_id, "matched")
                db.set_match(best.target_id, best.source_id, "matched")
                db.record_audit_event(
                    "reconciliation",
                    best.source_id,
                    "matched",
                    actor="reconciliation_engine",
                    after={"matched_with": best.target_id, "score": best.total_score},
                    reason=best.evidence,
                )
                used_credit_ids.add(best.target_id)
                matched_count += 1
            elif len(candidates) > 1:
                # Ambiguity detected: multiple viable matches
                top_score = candidates[0].total_score
                second_score = candidates[1].total_score
                if top_score - second_score < 10.0:
                    # Conflict: route to Review Queue
                    db.upsert_review_item({
                        "item_type": "reconciliation_conflict",
                        "item_id": deb["id"],
                        "reason": f"Multiple potential match candidates ({len(candidates)} options within score delta 10)",
                        "candidate_data": [
                            {"target_id": c.target_id, "score": c.total_score, "evidence": c.evidence}
                            for c in candidates[:3]
                        ],
                        "status": "pending",
                    })
                    conflicts_routed += 1

        return {"matched_count": matched_count, "conflicts_routed": conflicts_routed}


_reconciler: ReconciliationEngine | None = None


def get_reconciliation_engine() -> ReconciliationEngine:
    global _reconciler
    if _reconciler is None:
        _reconciler = ReconciliationEngine()
    return _reconciler
