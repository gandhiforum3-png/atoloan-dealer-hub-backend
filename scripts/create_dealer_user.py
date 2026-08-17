"""
One-off CLI to create a dealer_users row for local testing.

Usage:
    python -m scripts.create_dealer_user \
        --email manager@westsideauto.com \
        --password "correct horse battery staple" \
        --name "Andrew Miller" \
        --dealership "Westside Auto Group"
"""
import argparse
import asyncio

from sqlalchemy import insert

from app.db import get_engine
from app.models.dealer_user_table import dealer_user_table, next_dealer_id
from app.services.auth_service import hash_password


async def create_dealer_user(email: str, password: str, name: str, dealership: str) -> None:
    engine = get_engine()
    async with engine.begin() as conn:
        dealer_id = await next_dealer_id(conn)
        await conn.execute(
            insert(dealer_user_table).values(
                dealer_id=dealer_id,
                email=email.lower(),
                password_hash=hash_password(password),
                name=name,
                dealership_name=dealership,
            )
        )
    print(f"Created dealer user: {dealer_id} ({email})")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--dealership", required=True)
    args = parser.parse_args()

    asyncio.run(create_dealer_user(args.email, args.password, args.name, args.dealership))


if __name__ == "__main__":
    main()
