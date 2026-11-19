"""
Static pricing catalog for dealer billing — subscription tiers and
pay-as-you-go credit packs. Lives as code, not a DB table: this codebase has
no admin CRUD or migration tooling, so a pricing change is a code change and
a deploy, same as src/data/usStates.js on the frontend.
"""

PLANS = [
    {
        "id": "solo-lot",
        "name": "Solo Lot",
        "description": "For a single dealership location.",
        "monthly_price_cents": 12900,
        "annual_price_cents": 10900,
        "features": [
            "1 lot location",
            "Unlimited rate sheet uploads",
            "50 soft pulls / month",
        ],
    },
    {
        "id": "multi-lot",
        "name": "Multi-Lot",
        "description": "For dealer groups running several locations.",
        "monthly_price_cents": 34900,
        "annual_price_cents": 29700,
        "features": [
            "Up to 5 lot locations",
            "Unlimited rate sheet uploads",
            "250 soft pulls / month",
            "Priority bank-network support",
        ],
    },
    {
        "id": "dealer-group",
        "name": "Dealer Group",
        "description": "Custom pricing for unlimited locations.",
        "monthly_price_cents": None,
        "annual_price_cents": None,
        "features": [
            "Unlimited locations",
            "Group-level billing & reporting",
            "Dedicated account manager",
        ],
    },
]

CREDIT_PACKS = [
    {
        "id": "pack-10",
        "name": "10 credits",
        "credits": 10,
        "price_cents": 4500,
        "per_unit_cents": 450,
    },
    {
        "id": "pack-50",
        "name": "50 credits",
        "credits": 50,
        "price_cents": 20000,
        "per_unit_cents": 400,
    },
    {
        "id": "pack-100",
        "name": "100 credits",
        "credits": 100,
        "price_cents": 35000,
        "per_unit_cents": 350,
    },
]


def get_plan(plan_id: str) -> dict | None:
    return next((plan for plan in PLANS if plan["id"] == plan_id), None)


def get_credit_pack(pack_id: str) -> dict | None:
    return next((pack for pack in CREDIT_PACKS if pack["id"] == pack_id), None)
