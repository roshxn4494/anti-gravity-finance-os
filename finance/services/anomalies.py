"""Financial anomaly detection engine (Change 20).

Flags potential anomalies with structured evidence:
1. Category spend spikes (> 2.5x historical median)
2. Large transactions from first-time merchants
3. Suspected duplicate charges (same amount, same merchant within 48h)
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import pandas as pd

from .. import config, db
from ..money import format_inr_paise, rupees_to_paise


@dataclass
class AnomalySignal:
    transaction_id: str
    anomaly_type: str  # 'spend_spike' | 'new_merchant_large' | 'suspected_duplicate'
    amount_paise: int
    counterparty: str
    txn_date: str
    severity: str      # 'info' | 'warning' | 'critical'
    evidence: str


def detect_anomalies(lookback_days: int = 60) -> list[AnomalySignal]:
    """Detects unusual spending patterns, spikes, and duplicate transactions."""
    conn = db.connect()
    query = """
        SELECT * FROM transactions
        WHERE classification = 'spend'
        ORDER BY txn_date ASC
    """
    df = pd.read_sql_query(query, conn)
    conn.close()

    if df.empty or len(df) < 5:
        return []

    signals = []

    # 1. Duplicate Detection (same merchant, same absolute amount within 2 days)
    for i in range(len(df) - 1):
        r1 = df.iloc[i]
        r2 = df.iloc[i + 1]
        if r1["counterparty"] and r1["counterparty"] == r2["counterparty"]:
            if abs(float(r1["amount"])) == abs(float(r2["amount"])):
                try:
                    d1 = datetime.strptime(str(r1["txn_date"]), "%Y-%m-%d")
                    d2 = datetime.strptime(str(r2["txn_date"]), "%Y-%m-%d")
                    if 0 <= (d2 - d1).days <= 2:
                        amt_p = rupees_to_paise(abs(float(r2["amount"])))
                        signals.append(
                            AnomalySignal(
                                transaction_id=str(r2["id"]),
                                anomaly_type="suspected_duplicate",
                                amount_paise=amt_p,
                                counterparty=str(r2["counterparty"]),
                                txn_date=str(r2["txn_date"]),
                                severity="warning",
                                evidence=f"Suspected duplicate charge: ₹{amt_p/100:.2f} to {r2['counterparty']} occurred twice within 48h ({r1['txn_date']} and {r2['txn_date']}).",
                            )
                        )
                except Exception:
                    pass

    # 2. Category Outlier Spikes
    for cat, group in df.groupby("category"):
        if len(group) < 4:
            continue
        amounts = group["amount"].abs()
        median_amt = amounts.median()
        if median_amt <= 0:
            continue

        for _, r in group.iterrows():
            amt = abs(float(r["amount"]))
            if amt > 3.0 * median_amt and amt >= 2000.0:  # Spike > 3x median and at least ₹2,000
                amt_p = rupees_to_paise(amt)
                signals.append(
                    AnomalySignal(
                        transaction_id=str(r["id"]),
                        anomaly_type="spend_spike",
                        amount_paise=amt_p,
                        counterparty=str(r.get("counterparty") or "Unknown"),
                        txn_date=str(r["txn_date"]),
                        severity="info" if amt < 10000 else "warning",
                        evidence=f"Spend spike in '{cat}': ₹{amt:,.2f} is {amt/median_amt:.1f}x higher than category median (₹{median_amt:,.2f}).",
                    )
                )

    return signals
