"""Indian Credit Card Rewards & Loyalty Program Catalog.

Defines card variants, loyalty currencies, transfer ratios to airline/hotel partners,
portal redemption values, cash back equivalents, and standard flight award charts.
"""
from __future__ import annotations

from typing import Dict, List, Any

# Card Program Profiles
CARD_PROGRAMS: Dict[str, Dict[str, Any]] = {
    "Axis Atlas": {
        "issuer": "Axis Bank",
        "currency_name": "EDGE Miles",
        "baseline_value_inr": 1.00,  # ₹1.00 on Travel Edge flights/hotels
        "statement_credit_inr": 0.50,
        "flight_spend_earn_pct": 10.0,  # 5 EDGE Miles / ₹100 direct airline spend (= 10% value back to miles)
        "general_spend_earn_pct": 4.0,  # 2 EDGE Miles / ₹100 (= 4% to miles)
        "transfer_partners": [
            {
                "partner": "Accor Live Limitless (ALL)",
                "category": "Hotel",
                "card_pts": 1,
                "partner_pts": 2,
                "partner_pt_val_inr": 1.80,  # 1 Accor pt = €0.02 ~ ₹1.80
                "effective_inr_per_card_pt": 3.60,
                "sweet_spot": True,
                "notes": "Best value in India: 1 EDGE Mile = 2 Accor points (₹3.60 value).",
            },
            {
                "partner": "Singapore Airlines KrisFlyer",
                "category": "Airline",
                "card_pts": 1,
                "partner_pts": 2,
                "partner_pt_val_inr": 1.20,
                "effective_inr_per_card_pt": 2.40,
                "sweet_spot": True,
                "notes": "Direct redemptions to Singapore, Australia, SE Asia.",
            },
            {
                "partner": "Qatar Airways Privilege Club (Avios)",
                "category": "Airline",
                "card_pts": 1,
                "partner_pts": 2,
                "partner_pt_val_inr": 1.25,
                "effective_inr_per_card_pt": 2.50,
                "sweet_spot": True,
                "notes": "Avios can also be combined 1:1 with British Airways / Finnair.",
            },
            {
                "partner": "Air India Flying Returns",
                "category": "Airline",
                "card_pts": 1,
                "partner_pts": 2,
                "partner_pt_val_inr": 0.65,
                "effective_inr_per_card_pt": 1.30,
                "sweet_spot": False,
                "notes": "Great for domestic routes and non-stop US/UK flights.",
            },
            {
                "partner": "Marriott Bonvoy",
                "category": "Hotel",
                "card_pts": 1,
                "partner_pts": 2,
                "partner_pt_val_inr": 0.80,
                "effective_inr_per_card_pt": 1.60,
                "sweet_spot": False,
                "notes": "Global hotel network redemption.",
            },
            {
                "partner": "Turkish Miles&Smiles",
                "category": "Airline",
                "card_pts": 1,
                "partner_pts": 2,
                "partner_pt_val_inr": 1.10,
                "effective_inr_per_card_pt": 2.20,
                "sweet_spot": True,
                "notes": "Sweet spots on Star Alliance flights to US/Europe.",
            },
        ],
    },
    "Axis Magnus": {
        "issuer": "Axis Bank",
        "currency_name": "EDGE Rewards",
        "baseline_value_inr": 0.20,
        "statement_credit_inr": 0.20,
        "flight_spend_earn_pct": 4.8,
        "general_spend_earn_pct": 2.4,
        "transfer_partners": [
            {
                "partner": "Accor Live Limitless (ALL)",
                "category": "Hotel",
                "card_pts": 5,
                "partner_pts": 2,  # 5:2 ratio for non-Burgundy (or 5:4 Burgundy)
                "partner_pt_val_inr": 1.80,
                "effective_inr_per_card_pt": 0.72,
                "sweet_spot": True,
                "notes": "Transfer 5:2 to Accor ALL (₹0.72/pt).",
            },
            {
                "partner": "Singapore Airlines KrisFlyer",
                "category": "Airline",
                "card_pts": 5,
                "partner_pts": 2,
                "partner_pt_val_inr": 1.20,
                "effective_inr_per_card_pt": 0.48,
                "sweet_spot": False,
                "notes": "5:2 transfer to KrisFlyer.",
            },
            {
                "partner": "Qatar Airways (Avios)",
                "category": "Airline",
                "card_pts": 5,
                "partner_pts": 2,
                "partner_pt_val_inr": 1.25,
                "effective_inr_per_card_pt": 0.50,
                "sweet_spot": False,
                "notes": "5:2 transfer to Qatar Avios.",
            },
        ],
    },
    "Amex Platinum Travel": {
        "issuer": "American Express",
        "currency_name": "Membership Rewards (MR)",
        "baseline_value_inr": 0.25,
        "statement_credit_inr": 0.25,
        "flight_spend_earn_pct": 7.5,  # with milestone completion
        "general_spend_earn_pct": 2.0,
        "transfer_partners": [
            {
                "partner": "Marriott Bonvoy",
                "category": "Hotel",
                "card_pts": 1,
                "partner_pts": 1,
                "partner_pt_val_inr": 0.80,
                "effective_inr_per_card_pt": 0.80,
                "sweet_spot": True,
                "notes": "1:1 transfer ratio to Marriott Bonvoy. Best hotel value for Amex.",
            },
            {
                "partner": "Taj Vouchers (Gold Collection)",
                "category": "Voucher",
                "card_pts": 24000,
                "partner_pts": 10000,  # ₹10,000 voucher for 24k MR
                "partner_pt_val_inr": 1.00,
                "effective_inr_per_card_pt": 0.416,
                "sweet_spot": True,
                "notes": "Gold Collection 24k MR for ₹10,000 Taj Experiences.",
            },
            {
                "partner": "Singapore Airlines KrisFlyer",
                "category": "Airline",
                "card_pts": 2,
                "partner_pts": 1,
                "partner_pt_val_inr": 1.20,
                "effective_inr_per_card_pt": 0.60,
                "sweet_spot": False,
                "notes": "2:1 transfer to KrisFlyer.",
            },
            {
                "partner": "Qatar Airways (Avios)",
                "category": "Airline",
                "card_pts": 2,
                "partner_pts": 1,
                "partner_pt_val_inr": 1.25,
                "effective_inr_per_card_pt": 0.625,
                "sweet_spot": False,
                "notes": "2:1 transfer to Qatar Avios.",
            },
            {
                "partner": "Virgin Atlantic Flying Club",
                "category": "Airline",
                "card_pts": 2,
                "partner_pts": 1,
                "partner_pt_val_inr": 1.15,
                "effective_inr_per_card_pt": 0.575,
                "sweet_spot": True,
                "notes": "2:1 transfer. Sweet spots on London flights (Delhi/Mumbai to LHR).",
            },
        ],
    },
    "IDFC FIRST Wealth": {
        "issuer": "IDFC FIRST Bank",
        "currency_name": "IDFC Reward Points",
        "baseline_value_inr": 0.25,  # 1 pt = ₹0.25 on statement / merchant / gift cards
        "statement_credit_inr": 0.25,
        "flight_spend_earn_pct": 2.5,  # 10x points over ₹30k/mo
        "general_spend_earn_pct": 1.5,
        "transfer_partners": [
            {
                "partner": "Statement Credit / Pay with Points",
                "category": "Cashback",
                "card_pts": 1,
                "partner_pts": 1,
                "partner_pt_val_inr": 0.25,
                "effective_inr_per_card_pt": 0.25,
                "sweet_spot": True,
                "notes": "Points never expire! Offset statement dues directly at ₹0.25/pt.",
            },
            {
                "partner": "Brand Vouchers (Amazon/Flipkart)",
                "category": "Voucher",
                "card_pts": 1,
                "partner_pts": 1,
                "partner_pt_val_inr": 0.25,
                "effective_inr_per_card_pt": 0.25,
                "sweet_spot": False,
                "notes": "Redeemable for lifestyle & shopping gift vouchers.",
            },
        ],
    },
    "IDFC FIRST Mayura": {
        "issuer": "IDFC FIRST Bank",
        "currency_name": "IDFC Trip Miles",
        "baseline_value_inr": 0.25,
        "statement_credit_inr": 0.25,
        "flight_spend_earn_pct": 5.0,
        "general_spend_earn_pct": 2.5,
        "transfer_partners": [
            {
                "partner": "Air India Flying Returns",
                "category": "Airline",
                "card_pts": 1,
                "partner_pts": 1,
                "partner_pt_val_inr": 0.65,
                "effective_inr_per_card_pt": 0.65,
                "sweet_spot": True,
                "notes": "1:1 direct transfer to Air India miles.",
            },
        ],
    },
    "YES Bank Marquee": {
        "issuer": "YES Bank",
        "currency_name": "YES Rewardz",
        "baseline_value_inr": 0.25,  # ₹0.25 on YES Cart flights/hotels
        "statement_credit_inr": 0.15,
        "flight_spend_earn_pct": 4.5,
        "general_spend_earn_pct": 2.25,
        "transfer_partners": [
            {
                "partner": "YES Cart Flights & Hotels",
                "category": "Travel Portal",
                "card_pts": 1,
                "partner_pts": 1,
                "partner_pt_val_inr": 0.25,
                "effective_inr_per_card_pt": 0.25,
                "sweet_spot": True,
                "notes": "Book any flight/hotel ticket on YES Cart portal at 1 pt = ₹0.25.",
            },
            {
                "partner": "InterMiles / Club Vistara",
                "category": "Airline",
                "card_pts": 4,
                "partner_pts": 1,
                "partner_pt_val_inr": 0.80,
                "effective_inr_per_card_pt": 0.20,
                "sweet_spot": False,
                "notes": "4:1 airline miles transfer ratio.",
            },
        ],
    },
    "Scapia Federal": {
        "issuer": "Federal Bank (Scapia)",
        "currency_name": "Scapia Coins",
        "baseline_value_inr": 0.20,  # 5 coins = ₹1.00 (₹0.20/coin)
        "statement_credit_inr": 0.00,  # Scapia coins cannot be converted to statement cash, only travel
        "flight_spend_earn_pct": 4.0,  # 20% coins on eligible travel spend = 4% return
        "general_spend_earn_pct": 2.0,  # 10% coins on normal retail = 2% return
        "transfer_partners": [
            {
                "partner": "Scapia Travel App (Flights & Hotels)",
                "category": "Travel Portal",
                "card_pts": 5,
                "partner_pts": 1,
                "partner_pt_val_inr": 1.00,  # 5 coins = ₹1.00
                "effective_inr_per_card_pt": 0.20,
                "sweet_spot": True,
                "notes": "100% redemption against any flight or hotel on Scapia app with zero convenience fee.",
            },
        ],
    },
    "HDFC Infinia": {
        "issuer": "HDFC Bank",
        "currency_name": "Reward Points",
        "baseline_value_inr": 1.00,  # 1 pt = ₹1.00 on SmartBuy flights & hotels
        "statement_credit_inr": 0.30,
        "flight_spend_earn_pct": 16.5,  # 5x SmartBuy flights
        "general_spend_earn_pct": 3.3,
        "transfer_partners": [
            {
                "partner": "SmartBuy Flights & Hotels",
                "category": "Travel Portal",
                "card_pts": 1,
                "partner_pts": 1,
                "partner_pt_val_inr": 1.00,
                "effective_inr_per_card_pt": 1.00,
                "sweet_spot": True,
                "notes": "Redeem up to 70% of ticket value on SmartBuy at ₹1.00/point.",
            },
            {
                "partner": "Singapore Airlines KrisFlyer",
                "category": "Airline",
                "card_pts": 1,
                "partner_pts": 1,
                "partner_pt_val_inr": 1.20,
                "effective_inr_per_card_pt": 1.20,
                "sweet_spot": True,
                "notes": "1:1 direct airline transfer.",
            },
            {
                "partner": "Accor Live Limitless (ALL)",
                "category": "Hotel",
                "card_pts": 1,
                "partner_pts": 1,
                "partner_pt_val_inr": 1.80,
                "effective_inr_per_card_pt": 1.80,
                "sweet_spot": True,
                "notes": "1:1 transfer to Accor ALL.",
            },
        ],
    },
    "HDFC Regalia Gold": {
        "issuer": "HDFC Bank",
        "currency_name": "Reward Points",
        "baseline_value_inr": 0.50,  # 1 pt = ₹0.50 on SmartBuy flights
        "statement_credit_inr": 0.20,
        "flight_spend_earn_pct": 6.5,
        "general_spend_earn_pct": 1.33,
        "transfer_partners": [
            {
                "partner": "SmartBuy Flights",
                "category": "Travel Portal",
                "card_pts": 1,
                "partner_pts": 1,
                "partner_pt_val_inr": 0.50,
                "effective_inr_per_card_pt": 0.50,
                "sweet_spot": True,
                "notes": "Redeem on SmartBuy flight bookings at ₹0.50/point.",
            },
            {
                "partner": "Air India Flying Returns",
                "category": "Airline",
                "card_pts": 2,
                "partner_pts": 1,
                "partner_pt_val_inr": 0.65,
                "effective_inr_per_card_pt": 0.325,
                "sweet_spot": False,
                "notes": "2:1 transfer to Air India.",
            },
        ],
    },
}

# Standard Flight Route Benchmarks from India
FLIGHT_BENCHMARKS: Dict[str, Dict[str, Any]] = {
    "India ⇄ Singapore / SE Asia": {
        "destinations": ["Singapore (SIN)", "Bangkok (BKK)", "Kuala Lumpur (KUL)", "Bali (DPS)"],
        "programs": [
            {
                "airline": "Singapore Airlines KrisFlyer",
                "economy_miles": 18500,  # Saver award one-way
                "business_miles": 43000,
                "taxes_inr": 3800,
                "partner_name": "Singapore Airlines KrisFlyer",
            },
            {
                "airline": "Air India Flying Returns",
                "economy_miles": 15000,
                "business_miles": 35000,
                "taxes_inr": 3200,
                "partner_name": "Air India Flying Returns",
            },
        ],
        "typical_cash_fare_inr": {
            "Economy": 26000,
            "Business": 85000,
        },
    },
    "India ⇄ Dubai / Middle East": {
        "destinations": ["Dubai (DXB)", "Doha (DOH)", "Abu Dhabi (AUH)"],
        "programs": [
            {
                "airline": "Qatar Airways Privilege Club (Avios)",
                "economy_miles": 14000,
                "business_miles": 32000,
                "taxes_inr": 4500,
                "partner_name": "Qatar Airways Privilege Club (Avios)",
            },
            {
                "airline": "Air India Flying Returns",
                "economy_miles": 12000,
                "business_miles": 28000,
                "taxes_inr": 3600,
                "partner_name": "Air India Flying Returns",
            },
        ],
        "typical_cash_fare_inr": {
            "Economy": 24000,
            "Business": 75000,
        },
    },
    "India ⇄ London / UK / Europe": {
        "destinations": ["London Heathrow (LHR)", "Paris (CDG)", "Frankfurt (FRA)", "Amsterdam (AMS)"],
        "programs": [
            {
                "airline": "Virgin Atlantic Flying Club",
                "economy_miles": 20000,  # Delhi/Mumbai to London one-way standard
                "business_miles": 57500,  # Upper Class
                "taxes_inr": 12500,
                "partner_name": "Virgin Atlantic Flying Club",
            },
            {
                "airline": "Qatar Airways Privilege Club (Avios)",
                "economy_miles": 30000,
                "business_miles": 65000,
                "taxes_inr": 9800,
                "partner_name": "Qatar Airways Privilege Club (Avios)",
            },
            {
                "airline": "Air India Flying Returns",
                "economy_miles": 25000,
                "business_miles": 60000,
                "taxes_inr": 7500,
                "partner_name": "Air India Flying Returns",
            },
        ],
        "typical_cash_fare_inr": {
            "Economy": 58000,
            "Business": 210000,
        },
    },
    "Domestic India": {
        "destinations": ["Delhi ⇄ Mumbai", "Bengaluru ⇄ Delhi", "Mumbai ⇄ Goa", "Hyderabad ⇄ Bengaluru"],
        "programs": [
            {
                "airline": "Air India Flying Returns",
                "economy_miles": 5500,
                "business_miles": 14000,
                "taxes_inr": 950,
                "partner_name": "Air India Flying Returns",
            },
        ],
        "typical_cash_fare_inr": {
            "Economy": 5500,
            "Business": 22000,
        },
    },
    "India ⇄ US / North America": {
        "destinations": ["New York (JFK/EWR)", "San Francisco (SFO)", "Chicago (ORD)", "Toronto (YYZ)"],
        "programs": [
            {
                "airline": "Qatar Airways Privilege Club (Avios)",
                "economy_miles": 45000,
                "business_miles": 95000,
                "taxes_inr": 16000,
                "partner_name": "Qatar Airways Privilege Club (Avios)",
            },
            {
                "airline": "Singapore Airlines KrisFlyer",
                "economy_miles": 52000,
                "business_miles": 115000,
                "taxes_inr": 14500,
                "partner_name": "Singapore Airlines KrisFlyer",
            },
            {
                "airline": "Air India Flying Returns",
                "economy_miles": 45000,
                "business_miles": 95000,
                "taxes_inr": 11000,
                "partner_name": "Air India Flying Returns",
            },
        ],
        "typical_cash_fare_inr": {
            "Economy": 95000,
            "Business": 320000,
        },
    },
}
