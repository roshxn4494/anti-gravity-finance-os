# Finance Tracker

A local dashboard that reads your **Axis / SBI / Kotak** bank statements and shows
one aggregated view of your **real spending** — with salary, internal transfers,
and the Ashwin credit-card pass-through correctly filtered out.

## What it does

- **Upload** a statement (CSV or PDF) and pick which account it belongs to.
- **Classifies** every transaction automatically:
  - salary → *income*
  - sweeps between your own accounts → *internal transfer* (excluded from spend)
  - Ashwin's deposits + the credit-card bills you pay for him → *pass-through*
    (paired by amount, netted to ~zero)
  - everything else → *spend*, tagged by merchant into ~12 categories
- **Matches** transfers (sweep-out ↔ sweep-in, ±3 days) and Ashwin's pass-through
  (CC payment ↔ deposit, ±7 days). Anything unmatched shows up in
  **Reconciliation** — e.g. a CC payment with no Ashwin deposit yet.
- **Dashboard**: this-month spend / income / savings-rate KPIs, 6-month trend,
  spend by category & account.
- **Review**: any transaction can be reclassified inline. Manual tags are
  remembered per merchant/person, so future imports auto-fill.
- **Chat feedback**: every assistant answer gets a 👍/👎 — thumbs-down captures
  the question+answer into `chat_feedback` (in the DB) so failed answers can be
  reviewed in the **Feedback** tab and worked through here in the build chat.

## Run it

```bash
cd ~/finance-tracker
.venv/bin/streamlit run app.py
```

(Setup from scratch: `brew install python@3.13`, then
`.venv/bin/pip install -r requirements.txt`.)

## Getting your statements

Export a CSV (preferred) or PDF from each bank's netbanking:

| Bank | Netbanking → |
|---|---|
| Axis | Accounts → Statement → download as **CSV** |
| SBI | e-Statements → Transaction statement → download |
| Kotak | Accounts → Statements → download |

Import each file, choose the correct account in the dropdown, and press Import.

## Configure for your life — `finance/config.py`

The classifier is keyword-based and lives in one file. Edit it to match your
reality, then re-import:

| What | Where |
|---|---|
| Your employer's salary narration | `SALARY_KEYWORDS` |
| Ashwin's name / UPI IDs | `FRIEND_KEYWORDS`, `FRIEND_UPI` |
| Credit-card payment wording | `CC_PAYMENT_KEYWORDS` |
| Your own accounts | `ACCOUNTS` |
| Merchant → category map | `CATEGORY_KEYWORDS` |
| Matching windows | `MATCH_WINDOW_*` |

## How classification works (the order)

1. Fees (`ATM`, `GST`, `SERVICE CHARGE`…)
2. Salary credit → income
3. Credit from Ashwin → friend deposit
4. Debit paying a credit card → CC payment
5. Debit/credit referencing another of **your** accounts (SBI/Kotak/Axis, NEFT/FT)
   → internal transfer
6. Remaining debits → spend, categorized by merchant
7. Remaining credits (refunds, interest) → other income

A saved manual override (by merchant/person) always wins. Recurring person-to-person
payments (same person, similar amount, same-ish day each month) get flagged
`recurring` so you can tag them once (e.g. rent) and it sticks.

## Data & privacy

Everything runs locally. Transactions live in `data/finance.db` (SQLite) on your
machine. Nothing is sent anywhere.

## Tests

```bash
.venv/bin/python tests/run_tests.py
```

Covers classification, transfer/CC matching, recurring detection, KPI math and
dedup, using synthetic statements for all three banks.


## Architecture & security model

Finance OS now separates deterministic financial computation from AI interaction.

- **Personal configuration is local-only:** account-specific names, counterparties and employer keywords belong in `data/profile.json`, which is git-ignored. Copy `config/profile.example.json` to start.
- **Exact monetary arithmetic:** new domain calculations use integer minor units/Decimal rather than binary floating point.
- **Provenance and review:** the database initializes `import_runs`, `transaction_provenance`, `audit_events`, `review_queue`, `classification_rules`, and `metric_snapshots`.
- **AI is not the source of financial truth:** agent prompts contain behavioral rules only; financial facts must come from deterministic tools and current database state.
- **Cloud AI is opt-in:** set `FINANCE_PRIVACY_MODE=cloud_ai` explicitly before sending financial context to a cloud model. The default is local/blocked.
- **No unsupported prepayment claims:** the debt optimizer only uses stored loan/card data and reports missing APR/fee/foreclosure inputs instead of hard-coded savings assumptions.
- **CI:** GitHub Actions runs Ruff and pytest on pushes and pull requests.

### Local profile

Create `data/profile.json` from `config/profile.example.json` and add only the identifiers and classification rules required for your own statements. Never commit the resulting file.

### Privacy boundary

When cloud AI is enabled, only the data required by the selected agent/tool flow should be sent to the configured provider. For a strict local-only deployment, keep `FINANCE_PRIVACY_MODE=local` and do not configure a cloud API key.
