# Anti Gravity — Finance OS
**A Local-First Autonomous Personal Financial Operating System & AI Advisory Engine**

[![Tests](https://img.shields.io/badge/Tests-82%20Passed-brightgreen)](tests/run_tests.py)
[![Privacy](https://img.shields.io/badge/Privacy-100%25%20Local%20First-blue)](docs/ARCHITECTURE.md)
[![Precision](https://img.shields.io/badge/Precision-Integer%20Paise-orange)](docs/DATA_ENGINEERING.md)

---

## 📚 Comprehensive Documentation Suite

| Document | Target Audience | Purpose & Scope |
|:---|:---|:---|
| **[System & Data Architecture Specification](docs/ARCHITECTURE.md)** | Solution & Data Architects, Tech Leads | C4 models, ER diagrams, WAL concurrency, integer-paise math, algorithmic formulations (Liquidity simulation, Points valuation graph). |
| **[Data Engineering Pipeline Manual](docs/DATA_ENGINEERING.md)** | Data Engineers, ETL Developers | IMAP harvester, multi-password PDF layout parser, multiline CSV reader, deterministic SHA-256 deduplication, classification regexes, and bilateral drift reconciliation. |
| **[Executive Presentation & User Guide](docs/USER_PRESENTATION_AND_GUIDE.md)** | End Users, Executives, Product Managers | Strategic presentation pitch deck, 10-tab user manual, award flight redemption scenarios, and monthly closing checklist. |

---

## ⚡ Core Capabilities

1. **Multi-Bank Ingestion & Auto-Categorization**:
   - Parses CSV and PDF statements across Axis Bank, State Bank of India, and Kotak Mahindra Bank.
   - Word-boundary token matching with specificity scoring prevents false positives.
   - Exact integer-paise math (`amount_paise`) eliminates binary floating-point drift.
2. **Credit Cards & Active EMI Portfolio**:
   - Automated 1-click email sync (Gmail / Yahoo SSL IMAP) with multi-password PDF decryption.
   - Consolidated shared-credit limits (e.g. Axis Bank unified across physical cards).
   - Dedicated EMI schedules tracking original loan amounts, monthly installments, and remaining tenures across 35+ active plans.
3. **🎯 Rewards & Miles Optimizer**:
   - Live points tracking across Axis Atlas, Amex, IDFC FIRST, YES Bank, and Scapia Federal.
   - Valuation matrix across hotel transfers (Accor ALL @ ₹1.80/pt, Marriott Bonvoy @ ₹0.80/pt) and airline miles (KrisFlyer, Qatar Avios, Virgin Atlantic, Air India).
   - Award flight calculator comparing award seat points requirements, taxes, net savings, and cash card earn rates.
4. **Ashwin Pass-Through Ledger & Bilateral Reconciliation**:
   - Tracks third-party pass-through expenses and incoming deposits.
   - Non-greedy reconciliation with $\pm ₹1.00$ tolerance drift matching and manual override preservation.
5. **30-Day Proactive Liquidity Radar**:
   - Day-by-day cashflow simulation combining bank balances, salary credits, CC deadlines, and auto-debits.
   - Proactive internal transfer recommendations and "what-if" expense simulation.
6. **Master Financial AI Orchestrator**:
   - Policy-driven LLM assistant with dynamic tool calling over your local SQLite ledger (15+ specialized local tools).
   - Full conversation history logging, session switching, full-text search, and markdown transcript export.

---

## 🚀 Quickstart

### Prerequisites
- Python 3.11+
- Virtual environment (`.venv`)

### Installation & Run

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure personal counterparties (optional, gitignored)
cp data/user_config.example.yaml data/user_config.yaml

# 3. Launch Dashboard
streamlit run app.py
```

The application will be accessible at: `http://localhost:8501`.

---

## 🔐 Data Storage & Privacy Model

- **100% Local Storage**: All transactional records, statement PDFs, and loan schedules are stored locally on your machine in `data/finance.db` (SQLite in WAL mode).
- **Personal Identifiers**: Personal counterparty names (landlord, family, self-transfer markers) are loaded from `data/user_config.yaml`, which is strictly gitignored.
- **AI Agent Privacy**:
  - The core dashboard (Overview, Liquidity Radar, Transactions, Loans, Credit Cards, Rewards, Reconciliation) operates **100% offline** without any network calls.
  - The conversational AI agent ("Master Financial AI" tab) communicates with configured LLM providers (Groq / NVIDIA NIM) to interpret tool query results and generate natural-language insights. Raw bank account numbers and balances are never baked into system prompts.

---

## 🧪 Testing & Validation

Run the complete automated test suite (82 assertions):

```bash
./.venv/bin/python tests/run_tests.py
```

Sample output:
```text
Classification coverage:
  ✓ every row classified
Spot checks:
  ✓ salary → income
  ✓ Swiggy → spend / Food & Dining
Matching:
  ✓ Ashwin 12,000 paired with CC payment
Dedup:
  ✓ re-import inserts 0
Rewards & Miles Optimizer:
  ✓ upsert_card_reward persists points and variant
  ✓ flight booking optimizer recommends top award seat with sufficient points
===== 82 passed, 0 failed =====
```
